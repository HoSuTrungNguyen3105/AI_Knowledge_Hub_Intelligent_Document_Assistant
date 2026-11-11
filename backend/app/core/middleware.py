import math
import time
from threading import Lock

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import Settings


class RateLimiter:
    """Bounded, process-local fixed windows. Deployment must use a single worker."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._buckets: dict[tuple[str, str], tuple[int, float]] = {}
        self._lock = Lock()
        self._next_cleanup = 0.0
        self._max_buckets = 20_000

    def check(self, client_ip: str, *, auth: bool, now: float | None = None) -> int | None:
        now = time.monotonic() if now is None else now
        window = self.settings.rate_limit_window_seconds
        limits = [("api", self.settings.api_rate_limit)]
        if auth:
            limits.append(("auth", self.settings.auth_rate_limit))
        with self._lock:
            if now >= self._next_cleanup:
                self._buckets = {
                    key: entry for key, entry in self._buckets.items() if entry[1] > now
                }
                self._next_cleanup = now + window
            for category, limit in limits:
                key = (client_ip, category)
                count, reset_at = self._buckets.get(key, (0, now + window))
                if reset_at <= now:
                    count, reset_at = 0, now + window
                if count >= limit:
                    return max(1, math.ceil(reset_at - now))
                if key not in self._buckets and len(self._buckets) >= self._max_buckets:
                    return window
                self._buckets[key] = count + 1, reset_at
        return None


class SecurityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, settings: Settings, limiter: RateLimiter):
        super().__init__(app)
        self.settings = settings
        self.limiter = limiter

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/api/v1"):
            # Read only the ASGI peer, never client-supplied forwarding headers.
            # Uvicorn is started with --no-proxy-headers for the same reason.
            if request.method != "OPTIONS":
                retry_after = self.limiter.check(
                    request.client.host if request.client else "unknown",
                    auth=request.url.path.startswith("/api/v1/auth/") and request.method == "POST",
                )
                if retry_after is not None:
                    detail = "Too many requests"
                    if request.url.path.startswith("/api/v1/ai"):
                        detail = {"code": "request_rate_limited", "message": "Too many requests."}
                    return JSONResponse(
                        {"detail": detail},
                        status_code=429,
                        headers={"Retry-After": str(retry_after), "Cache-Control": "no-store"},
                    )
            if request.method not in {"GET", "HEAD", "OPTIONS"}:
                origin = request.headers.get("origin")
                has_cookies = bool(request.headers.get("cookie"))
                if (origin is not None and origin not in self.settings.cors_origins) or (
                    has_cookies and origin is None
                ):
                    detail = "Untrusted or missing request origin"
                    if request.url.path.startswith("/api/v1/ai"):
                        detail = {
                            "code": "invalid_origin",
                            "message": "Untrusted or missing request origin.",
                        }
                    return JSONResponse(
                        {"detail": detail},
                        status_code=403,
                        headers={"Cache-Control": "no-store"},
                    )
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        if request.url.path.startswith(("/api/v1/auth", "/api/v1/dashboard", "/api/v1/ai")):
            response.headers["Cache-Control"] = "no-store"
        return response
