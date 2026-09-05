from __future__ import annotations

import os

import httpx


def search_live_web(query: str) -> list[str]:
    hits: list[str] = []
    hits.extend(_tavily(query))
    hits.extend(_newsapi(query))
    return [hit for hit in hits if hit]


def _tavily(query: str) -> list[str]:
    key = os.getenv("TAVILY_API_KEY", "")
    if not key:
        return []
    try:
        from tavily import TavilyClient

        payload = TavilyClient(api_key=key).search(query, max_results=3)
        rows = payload.get("results") if isinstance(payload, dict) else []
        return [str(row.get("content") or row.get("snippet") or "") for row in rows or []]
    except Exception:
        return []


def _newsapi(query: str) -> list[str]:
    key = os.getenv("NEWSAPI_API_KEY", "")
    if not key:
        return []
    try:
        response = httpx.get(
            "https://newsapi.org/v2/everything",
            params={"q": query, "pageSize": 3, "language": "en"},
            headers={"X-Api-Key": key},
            timeout=10,
        )
        response.raise_for_status()
        articles = response.json().get("articles") or []
        return [str(article.get("title") or article.get("description") or "") for article in articles]
    except Exception:
        return []
