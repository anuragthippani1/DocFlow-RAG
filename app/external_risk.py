import asyncio
from typing import Any

import httpx

from app.config import get_settings
from app.logging_utils import get_logger


logger = get_logger(__name__)


async def _fetch_signal(
    client: httpx.AsyncClient, label: str, url: str, question: str
) -> dict[str, Any]:
    try:
        response = await client.get(url, params={"q": question})
        response.raise_for_status()
        payload = response.json()
        return {"source": label, "status": "ok", "data": payload}
    except Exception as e:
        logger.warning("External risk source failed: %s: %s", label, e)
        return {"source": label, "status": "error", "error": str(e)}


async def fetch_external_risk_context(question: str) -> dict[str, Any]:
    """
    Optional external signal hook.

    Configure WEATHER_API_URL, NEWS_API_URL, or SHIPPING_API_URL to enrich the
    external-risk agent. If none are configured, the system degrades cleanly.
    """
    settings = get_settings()
    sources = {
        "weather": settings.weather_api_url,
        "news": settings.news_api_url,
        "shipping": settings.shipping_api_url,
    }
    active_sources = {name: url for name, url in sources.items() if url}
    if not active_sources:
        return {"enabled": False, "signals": []}

    timeout = httpx.Timeout(settings.external_risk_timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout) as client:
        signals = await asyncio.gather(
            *[
                _fetch_signal(client, label, url, question)
                for label, url in active_sources.items()
            ]
        )

    return {"enabled": True, "signals": signals}
