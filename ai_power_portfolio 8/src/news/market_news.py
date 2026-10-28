"""
Week 9 - news and market context for the recommended assets.

News comes from yfinance (Ticker.news, no API key needed). Each asset's
headlines are summarized by the LLM for relevance to the user's portfolio;
with no key/network the headlines are shown with a plain note instead.
Everything here is failure-tolerant: a ticker whose news can't be fetched is
reported as "unavailable" and the rest still work.
"""
import sqlite3
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from typing import List, Optional

from src.ai.llm import generate_text
from src.portfolio.allocation import CASH_TICKER, get_recommendation
from src.questionnaire.store import get_profile

NEWS_TIMEOUT_SECONDS = 12   # give up on a slow news request instead of freezing the app

SYSTEM_PROMPT = (
    "You summarize market news for a student-built educational investing prototype. "
    "Be neutral and factual, never predict prices, never say to buy or sell. "
    "Write 2 to 3 sentences, no bullet points."
)


def normalize_news_item(item: dict) -> Optional[dict]:
    """
    yfinance has changed its news format over versions: newer releases nest everything under
    item['content'], older ones are flat. Returns {title, publisher, link, published} or None.
    """
    content = item.get("content") if isinstance(item.get("content"), dict) else item
    title = content.get("title")
    if not title:
        return None
    provider = content.get("provider")
    publisher = (provider.get("displayName") if isinstance(provider, dict) else None) or content.get("publisher")
    canonical = content.get("canonicalUrl")
    link = (canonical.get("url") if isinstance(canonical, dict) else None) or content.get("link")
    published = content.get("pubDate") or content.get("providerPublishTime")
    return {"title": title, "publisher": publisher or "", "link": link or "", "published": str(published or "")}


def fetch_news(ticker: str, limit: int = 5) -> List[dict]:
    """Latest headlines for a ticker; empty list if unavailable."""
    try:
        import yfinance as yf
        raw = yf.Ticker(ticker).news or []
    except Exception as e:
        print(f"[news] could not fetch news for {ticker}: {e}")
        return []
    items = [normalize_news_item(r) for r in raw if isinstance(r, dict)]
    return [i for i in items if i][:limit]


def summarize_relevance(ticker: str, asset_name: str, allocation_pct: float, profile_name: str,
                        headlines: List[dict]) -> dict:
    """Returns {summary, source} where source is 'llm', 'headlines-only', or 'unavailable'."""
    if not headlines:
        return {"summary": f"No recent news could be retrieved for {ticker}.", "source": "unavailable"}

    titles = "\n".join(f"- {h['title']} ({h['publisher']})" for h in headlines)
    prompt = (
        f"The user is a {profile_name} investor whose portfolio holds {allocation_pct:.0f}% in "
        f"{asset_name} ({ticker}).\nRecent headlines:\n{titles}\n\n"
        f"Summarize what these headlines suggest and why they might matter for someone holding this asset."
    )
    text = generate_text(prompt, system=SYSTEM_PROMPT, max_tokens=250)
    if text:
        return {"summary": text, "source": "llm"}
    return {
        "summary": f"Recent headlines for {asset_name} ({ticker}) are listed below. "
                   f"(AI summary unavailable - no API key configured.)",
        "source": "headlines-only",
    }


def get_market_context(conn: sqlite3.Connection, user_profile_key: int, top_n: int = 4,
                       headlines_per_asset: int = 3) -> List[dict]:
    """
    News + relevance summary for the user's largest non-cash holdings.
    Returns [{ticker, asset_name, allocation_pct, headlines, summary, source}].
    """
    profile = get_profile(conn, user_profile_key)
    holdings = [(t, pct) for t, _cls, pct in get_recommendation(conn, user_profile_key) if t != CASH_TICKER]
    names = dict(conn.execute("SELECT ticker, asset_name FROM dim_asset").fetchall())

    top = holdings[:top_n]
    # Fetch all tickers at the same time; a slow or hanging request only costs NEWS_TIMEOUT_SECONDS.
    pool = ThreadPoolExecutor(max_workers=max(1, len(top)))
    futures = [pool.submit(fetch_news, t, headlines_per_asset) for t, _ in top]
    pool.shutdown(wait=False)

    context = []
    for (ticker, pct), future in zip(top, futures):
        try:
            headlines = future.result(timeout=NEWS_TIMEOUT_SECONDS)
        except FutureTimeout:
            print(f"[news] {ticker}: timed out after {NEWS_TIMEOUT_SECONDS}s")
            headlines = []
        except Exception as e:
            print(f"[news] {ticker}: failed ({e})")
            headlines = []
        summary = summarize_relevance(ticker, names.get(ticker) or ticker, pct, profile["profile_name"], headlines)
        context.append({
            "ticker": ticker,
            "asset_name": names.get(ticker) or ticker,
            "allocation_pct": pct,
            "headlines": headlines,
            **summary,
        })
    return context
