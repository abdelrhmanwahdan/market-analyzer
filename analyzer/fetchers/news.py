"""News fetcher — Alpha Vantage (sentiment) + NewsAPI (headlines). Both free tiers."""

import logging
from datetime import datetime, timezone

import requests

from config import ALPHA_VANTAGE_API_KEY, NEWS_API_KEY

log = logging.getLogger(__name__)
TIMEOUT = 15


def _get(url: str, params: dict) -> dict | None:
    try:
        r = requests.get(url, params=params, timeout=TIMEOUT)
        if r.status_code == 200:
            return r.json()
        log.warning("News API %s → %s", url, r.status_code)
    except Exception as e:
        log.warning("News request failed: %s", e)
    return None


def _fetch_alpha_vantage_news() -> list[dict]:
    """Alpha Vantage news & sentiment — 25 calls/day free."""
    if not ALPHA_VANTAGE_API_KEY:
        return []

    topics = "financial_markets,economy_macro,earnings,ipo"
    data = _get("https://www.alphavantage.co/query", {
        "function": "NEWS_SENTIMENT",
        "topics": topics,
        "sort": "LATEST",
        "limit": 20,
        "apikey": ALPHA_VANTAGE_API_KEY,
    })

    if not data or "feed" not in data:
        return []

    articles = []
    for item in data["feed"][:15]:
        sentiment = item.get("overall_sentiment_label", "Neutral")
        score = float(item.get("overall_sentiment_score", 0))
        articles.append({
            "source": item.get("source"),
            "title": item.get("title"),
            "url": item.get("url"),
            "published": item.get("time_published"),
            "sentiment": sentiment,
            "sentiment_score": score,
            "topics": [t.get("topic") for t in item.get("topics", [])],
            "tickers": [t.get("ticker") for t in item.get("ticker_sentiment", [])[:5]],
        })
    return articles


def _fetch_newsapi_headlines() -> list[dict]:
    """NewsAPI business headlines — 100 calls/day free."""
    if not NEWS_API_KEY:
        return []

    articles = []

    # Financial headlines
    data = _get("https://newsapi.org/v2/everything", {
        "q": "(stock market OR gold price OR bitcoin OR crypto OR Egyptian economy OR EGX)",
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": 10,
        "apiKey": NEWS_API_KEY,
    })
    if data and "articles" in data:
        for a in data["articles"][:10]:
            articles.append({
                "source": a.get("source", {}).get("name"),
                "title": a.get("title"),
                "description": a.get("description"),
                "published": a.get("publishedAt"),
                "url": a.get("url"),
            })

    # Top business headlines
    top = _get("https://newsapi.org/v2/top-headlines", {
        "category": "business",
        "country": "us",
        "pageSize": 5,
        "apiKey": NEWS_API_KEY,
    })
    if top and "articles" in top:
        for a in top["articles"][:5]:
            articles.append({
                "source": a.get("source", {}).get("name"),
                "title": a.get("title"),
                "description": a.get("description"),
                "published": a.get("publishedAt"),
                "url": a.get("url"),
            })

    return articles


def fetch() -> dict | None:
    """Aggregate news from all available free sources."""
    av_news = _fetch_alpha_vantage_news()
    newsapi = _fetch_newsapi_headlines()

    # Compute simple sentiment aggregate from Alpha Vantage
    if av_news:
        scores = [a["sentiment_score"] for a in av_news]
        avg_score = sum(scores) / len(scores)
        if avg_score > 0.15:
            overall_sentiment = "Bullish"
        elif avg_score < -0.15:
            overall_sentiment = "Bearish"
        else:
            overall_sentiment = "Neutral"
    else:
        overall_sentiment = "Unknown"

    return {
        "market": "news",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "overall_sentiment": overall_sentiment,
        "alpha_vantage_articles": av_news,
        "newsapi_articles": newsapi,
        "note": "Claude Code should also web-search for latest news during analysis",
    }
