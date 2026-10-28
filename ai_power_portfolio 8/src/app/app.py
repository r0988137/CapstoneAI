"""
Weeks 11-12 - web front-end + dashboard (Gradio).

Two tabs:
  1. "Get my portfolio"  - the questionnaire form; shows profile, AI explanation,
                          portfolio, market news and the scenario forecast.
  2. "Dashboard"        - market data overview + price chart, saved questionnaires.

Run it:
  Colab / notebook:  from src.app.app import launch; launch()
  Terminal:          python -m src.app.app
"""
import sqlite3

from src.app import views
from src.config.settings import SCHEMA_SQL_PATH, WAREHOUSE_DB_PATH
from src.questionnaire.schema import MAX_HORIZON_YEARS
from src.workflow.run_workflow import DISCLAIMER, run_full_workflow


def get_conn() -> sqlite3.Connection:
    """Opens the warehouse, creating the tables first if init_db was never run."""
    WAREHOUSE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(WAREHOUSE_DB_PATH)
    has_tables = conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'fact_user_profile'").fetchone()
    if not has_tables:
        conn.executescript(SCHEMA_SQL_PATH.read_text())
        conn.commit()
    return conn


def run_questionnaire(name, amount, years, risk, loss, goal, monthly, include_news):
    """Form handler. Returns (cards, profile_md, rationale_md, donut, holdings, table, forecast_fig, forecast_md, news_md)."""
    try:
        answers = views.answers_from_form(amount, years, risk, loss, goal, monthly)
    except ValueError as e:
        return "", f"**Please check your answers:** {e}", "", None, None, None, None, "", ""

    conn = get_conn()
    try:
        result = run_full_workflow(conn, (name or "web-user").strip() or "web-user", answers,
                                   include_news=bool(include_news))
    finally:
        conn.close()
    return (
        views.summary_cards_html(result),
        views.profile_markdown(result),
        views.rationale_markdown(result),
        views.allocation_figure(result["allocation"]),
        views.holdings_figure(result["allocation"]),
        views.allocation_table(result["allocation"]),
        views.forecast_figure(result["forecast"]["rows"]),
        views.forecast_markdown(result),
        views.news_markdown(result["news"]),
    )


# name, amount, years, risk, loss, goal, monthly, news
EXAMPLES = [
    ["Cautious saver", 5000, 2, 1, 1, "preservation", 100, False],
    ["Balanced investor", 20000, 10, 3, 3, "combination", 300, False],
    ["Long-term growth", 10000, 25, 5, 5, "growth", 500, False],
]

CSS = """
.apc-grid {display:grid; grid-template-columns: 2fr 1fr 1fr; gap:14px; margin:4px 0 10px}
.apc-card {border:1px solid var(--border-color-primary); border-radius:14px; padding:16px 18px; background:var(--background-fill-secondary)}
.apc-label {font-size:12px; letter-spacing:.06em; text-transform:uppercase; opacity:.7}
.apc-big {font-size:30px; font-weight:700; line-height:1.2; margin:4px 0}
.apc-small {font-size:13px; opacity:.75}
.apc-meter {height:8px; border-radius:6px; background:rgba(128,128,128,.25); margin:8px 0 4px; overflow:hidden}
.apc-meter div {height:100%; border-radius:6px}
.apc-hero h1 {margin-bottom:2px}
@media (max-width: 700px) {.apc-grid {grid-template-columns: 1fr}}
"""


def refresh_dashboard(selected_tickers):
    conn = get_conn()
    try:
        return (
            views.warehouse_status(conn),
            views.market_overview(conn),
            views.price_figure(conn, selected_tickers or None),
            views.saved_profiles(conn),
            views.profile_mix_figure(conn),
        )
    finally:
        conn.close()


def build_app():
    import gradio as gr
    import inspect

    conn = get_conn()
    tickers = views.available_tickers(conn)
    conn.close()

    # Gradio 6 takes theme/css in launch(); Gradio 5 takes them in Blocks(). Support both.
    theme = gr.themes.Soft(primary_hue="emerald", neutral_hue="slate")
    block_kwargs = {"title": "AI Power Portfolio"}
    if "theme" not in inspect.signature(gr.Blocks.launch).parameters:
        block_kwargs.update(theme=theme, css=CSS)

    with gr.Blocks(**block_kwargs) as demo:
        gr.Markdown("# AI Power Portfolio\nAnswer six questions and get a suggested portfolio of ETFs, "
                    "the reasoning behind it, market context and a forecast. *Educational prototype, not financial advice.*",
                    elem_classes="apc-hero")

        with gr.Tab("Get my portfolio"):
            with gr.Row():
                with gr.Column(scale=1, min_width=320):
                    name = gr.Textbox(label="Your name (or any ID)", value="demo-user")
                    amount = gr.Number(label="Initial investment ($)", value=10000, minimum=1)
                    years = gr.Slider(1, MAX_HORIZON_YEARS, value=10, step=1, label="Time horizon (years)")
                    monthly = gr.Number(label="Monthly contribution ($, 0 if none)", value=200, minimum=0)
                    risk = gr.Dropdown(views.RISK_CHOICES, value=3, label="How much risk are you comfortable with?")
                    loss = gr.Dropdown(views.LOSS_CHOICES, value=3,
                                       label="If your portfolio dropped 10-20%, you would...")
                    goal = gr.Dropdown(views.GOAL_CHOICES, value="growth", label="Main goal")
                    news = gr.Checkbox(value=True, label="Include market news (a bit slower)")
                    go = gr.Button("Get my portfolio", variant="primary", size="lg")
                    gr.Markdown("**Or try an example:**")
                    with gr.Row():
                        for example in EXAMPLES:
                            btn = gr.Button(example[0], size="sm")
                            btn.click(lambda ex=example: ex, None, [name, amount, years, risk, loss, goal, monthly, news])
                with gr.Column(scale=2):
                    cards = gr.HTML()
                    with gr.Tab("Profile"):
                        profile_md = gr.Markdown("*Fill in the form and press **Get my portfolio**.*")
                    with gr.Tab("Portfolio"):
                        with gr.Row():
                            donut = gr.Plot(label="By asset type")
                            holdings = gr.Plot(label="By ETF / asset")
                        table = gr.Dataframe(label="Allocation", interactive=False, wrap=True,
                                             column_widths=["11%", "39%", "20%", "15%", "15%"])
                        rationale_md = gr.Markdown()
                    with gr.Tab("Forecast"):
                        forecast_fig = gr.Plot(label="Forecast")
                        forecast_md = gr.Markdown()
                    with gr.Tab("Market context"):
                        news_md = gr.Markdown()
            gr.Markdown(f"*{DISCLAIMER}*")
            go.click(run_questionnaire, [name, amount, years, risk, loss, goal, monthly, news],
                     [cards, profile_md, rationale_md, donut, holdings, table, forecast_fig, forecast_md, news_md])

        with gr.Tab("Dashboard") as dash_tab:
            status = gr.Markdown()
            picked = gr.Dropdown(tickers, value=tickers, multiselect=True, label="Assets in chart")
            refresh = gr.Button("Refresh")
            overview = gr.Dataframe(label="Market overview", interactive=False)
            price_fig = gr.Plot()
            gr.Markdown("### Questionnaires saved so far")
            with gr.Row():
                profiles = gr.Dataframe(label="Latest questionnaires", interactive=False)
                mix = gr.Plot()
            outputs = [status, overview, price_fig, profiles, mix]
            refresh.click(refresh_dashboard, picked, outputs)
            picked.change(refresh_dashboard, picked, outputs)
            dash_tab.select(refresh_dashboard, picked, outputs)

        with gr.Tab("Assets"):
            gr.Markdown("### The investment universe\nEvery ETF and asset the advisor can recommend, "
                        "with the long-run planning assumptions used in the forecast.")
            gr.Dataframe(value=views.asset_catalog_table(), interactive=False, wrap=True,
                         column_widths=["8%", "24%", "13%", "8%", "9%", "38%"])
        demo.load(refresh_dashboard, picked, outputs)
    demo._apc_theme, demo._apc_css = theme, CSS
    return demo


def launch(share: bool = True, **kwargs):
    """share=True gives a public link, which is what Colab needs to show the app."""
    import inspect
    demo = build_app()
    if "theme" in inspect.signature(demo.launch).parameters:   # Gradio 6+
        kwargs.setdefault("theme", demo._apc_theme)
        kwargs.setdefault("css", demo._apc_css)
    demo.launch(share=share, **kwargs)


if __name__ == "__main__":
    launch(share=False)
