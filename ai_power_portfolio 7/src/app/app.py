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
    """Form handler. Returns (profile_md, rationale_md, pie, table, forecast_fig, forecast_md, news_md)."""
    try:
        answers = views.answers_from_form(amount, years, risk, loss, goal, monthly)
    except ValueError as e:
        return f"**Please check your answers:** {e}", "", None, None, None, "", ""

    conn = get_conn()
    try:
        result = run_full_workflow(conn, (name or "web-user").strip() or "web-user", answers,
                                   include_news=bool(include_news))
    finally:
        conn.close()
    return (
        views.profile_markdown(result),
        views.rationale_markdown(result),
        views.allocation_figure(result["allocation"]),
        views.allocation_table(result["allocation"]),
        views.forecast_figure(result["forecast"]["rows"]),
        views.forecast_markdown(result),
        views.news_markdown(result["news"]),
    )


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

    conn = get_conn()
    tickers = views.available_tickers(conn)
    conn.close()

    with gr.Blocks(title="AI Power Portfolio") as demo:
        gr.Markdown("# AI Power Portfolio\nAnswer a few questions and get a suggested portfolio, "
                    "market context and a forecast. *Educational prototype.*")

        with gr.Tab("Get my portfolio"):
            with gr.Row():
                with gr.Column(scale=1):
                    name = gr.Textbox(label="Your name (or any ID)", value="demo-user")
                    amount = gr.Number(label="Initial investment ($)", value=10000, minimum=1)
                    years = gr.Slider(1, MAX_HORIZON_YEARS, value=10, step=1, label="Time horizon (years)")
                    monthly = gr.Number(label="Monthly contribution ($, 0 if none)", value=200, minimum=0)
                    risk = gr.Dropdown(views.RISK_CHOICES, value=3, label="How much risk are you comfortable with?")
                    loss = gr.Dropdown(views.LOSS_CHOICES, value=3,
                                       label="If your portfolio dropped 10-20%, you would...")
                    goal = gr.Dropdown(views.GOAL_CHOICES, value="growth", label="Main goal")
                    news = gr.Checkbox(value=True, label="Include market news (a bit slower)")
                    go = gr.Button("Get my portfolio", variant="primary")
                with gr.Column(scale=2):
                    profile_md = gr.Markdown()
                    rationale_md = gr.Markdown()
                    with gr.Row():
                        pie = gr.Plot(label="Portfolio")
                        table = gr.Dataframe(label="Allocation", interactive=False)
                    forecast_fig = gr.Plot(label="Forecast")
                    forecast_md = gr.Markdown()
                    gr.Markdown("### Market context")
                    news_md = gr.Markdown()
            gr.Markdown(f"*{DISCLAIMER}*")
            go.click(run_questionnaire, [name, amount, years, risk, loss, goal, monthly, news],
                     [profile_md, rationale_md, pie, table, forecast_fig, forecast_md, news_md])

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
        demo.load(refresh_dashboard, picked, outputs)
    return demo


def launch(share: bool = True, **kwargs):
    """share=True gives a public link, which is what Colab needs to show the app."""
    build_app().launch(share=share, **kwargs)


if __name__ == "__main__":
    launch(share=False)
