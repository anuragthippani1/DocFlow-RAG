import time
from collections import defaultdict, deque
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.config import get_settings
from app.logging_utils import get_logger

logger = get_logger(__name__)

API_KEY_HEADER = "X-API-Key"
PUBLIC_PATHS = {"/health", "/docs", "/openapi.json", "/redoc"}
PROTECTED_PREFIXES = ("/upload", "/query", "/documents", "/cache", "/status", "/metrics")


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _requires_api_key(path: str) -> bool:
    if path in PUBLIC_PATHS:
        return False
    return any(path.startswith(prefix) for prefix in PROTECTED_PREFIXES)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, limit_per_minute: int):
        super().__init__(app)
        self.limit_per_minute = max(1, limit_per_minute)
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.method == "OPTIONS":
            return await call_next(request)

        now = time.time()
        key = _client_key(request)
        window = self._hits[key]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= self.limit_per_minute:
            logger.warning("Rate limit exceeded for %s on %s", key, request.url.path)
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Try again shortly."},
            )
        window.append(now)
        return await call_next(request)


class APIKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        settings = get_settings()
        if not settings.api_key or not _requires_api_key(request.url.path):
            return await call_next(request)

        provided = request.headers.get(API_KEY_HEADER, "")
        if provided != settings.api_key:
            logger.warning("Unauthorized request to %s", request.url.path)
            return JSONResponse(status_code=401, content={"detail": "Invalid or missing API key."})
        return await call_next(request)
