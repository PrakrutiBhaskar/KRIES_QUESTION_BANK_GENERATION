"""
Rate limiting.

Three layers, all configured in config.py / .env (see the RATE_LIMIT_* keys):

  1. A middleware that throttles every request. Each request is counted
     against a "global" bucket (per signed-in user, or per IP when anonymous)
     and, for the sensitive endpoints, a stricter bucket as well:

         POST /auth/login            per IP
         POST /auth/signup           per IP
         POST /auth/forgot-password,
         POST /auth/reset-password   per IP
         POST /generate,
         POST /practice/sessions,
         POST /papers/blueprint      per user   (these can call the LLM)
         POST /export/{id}           per user

  2. A failed-login lockout (services/auth.py): too many wrong passwords for
     the same (IP, email) locks that pair out for a while, even if the next
     password is right.

  3. Every limit answers with HTTP 429, the usual {"error", "detail"} body and
     a Retry-After header.

The counters live in this process's memory. That is right for a single
uvicorn worker (local development, one Render instance). With several
workers or instances each keeps its own counts, so the effective limit is
multiplied; move the store to Redis before scaling out.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Callable

from .config import Rule, parse_rule, settings
from .errors import error_response
from .security import decode_access_token


class SlidingWindowLimiter:
    """Exact sliding-window log: remembers the timestamp of each recent hit."""

    _SWEEP_EVERY = 500  # operations between purges of idle keys

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._lock = threading.Lock()
        self._hits: dict[str, deque[float]] = {}
        self._windows: dict[str, float] = {}
        self._ops = 0

    def _prune(self, key: str, rule: Rule, now: float) -> deque[float]:
        q = self._hits.setdefault(key, deque())
        self._windows[key] = rule.window
        cutoff = now - rule.window
        while q and q[0] <= cutoff:
            q.popleft()
        return q

    def _sweep(self, now: float) -> None:
        self._ops += 1
        if self._ops % self._SWEEP_EVERY:
            return
        for key in [
            k for k, q in self._hits.items() if not q or q[-1] <= now - self._windows[k]
        ]:
            del self._hits[key]
            del self._windows[key]

    def retry_after(self, key: str, rule: Rule) -> float:
        """Seconds until `key` may act again (0 = allowed now). Records nothing."""
        with self._lock:
            now = self._clock()
            self._sweep(now)
            q = self._prune(key, rule, now)
            return max(q[0] + rule.window - now, 0.001) if len(q) >= rule.limit else 0.0

    def record(self, key: str, rule: Rule) -> None:
        with self._lock:
            now = self._clock()
            self._prune(key, rule, now).append(now)

    def hit(self, key: str, rule: Rule) -> float:
        """Count one action. Returns 0 if allowed, else seconds to wait.

        Rejected attempts are not counted, so a client that keeps hammering
        doesn't extend its own penalty.
        """
        with self._lock:
            now = self._clock()
            self._sweep(now)
            q = self._prune(key, rule, now)
            if len(q) >= rule.limit:
                return max(q[0] + rule.window - now, 0.001)
            q.append(now)
            return 0.0

    def clear(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)
            self._windows.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
            self._windows.clear()


# One shared instance for the whole process.
limiter = SlidingWindowLimiter()


# --- identifying the caller --------------------------------------------------


def client_ip(scope: dict) -> str:
    if settings.trust_proxy_headers:
        for name, value in scope.get("headers", []):
            if name == b"x-forwarded-for":
                first = value.decode("latin-1").split(",")[0].strip()
                if first:
                    return first
    client = scope.get("client")
    return client[0] if client else "unknown"


def _bearer_user(scope: dict) -> str | None:
    for name, value in scope.get("headers", []):
        if name == b"authorization":
            scheme, _, token = value.decode("latin-1").partition(" ")
            if scheme.lower() == "bearer" and token:
                user_id = decode_access_token(token.strip())
                return str(user_id) if user_id else None
    return None


# --- which limits apply to a request -----------------------------------------


def _rules_for(method: str, path: str) -> list[tuple[str, str, str]]:
    """[(bucket name, "<n>/<seconds>", "ip" | "user")], strictest first."""
    prefix = settings.api_prefix.rstrip("/")
    rel = path[len(prefix):] if path.startswith(prefix) else None
    rel = rel.rstrip("/") if rel is not None else None

    rules: list[tuple[str, str, str]] = []
    if method == "POST" and rel is not None:
        if rel == "/auth/login":
            rules.append(("login", settings.rate_limit_login, "ip"))
        elif rel == "/auth/signup":
            rules.append(("signup", settings.rate_limit_signup, "ip"))
        elif rel in ("/auth/forgot-password", "/auth/reset-password"):
            rules.append(("password-reset", settings.rate_limit_password_reset, "ip"))
        elif rel in ("/generate", "/practice/sessions", "/papers/blueprint"):
            rules.append(("generate", settings.rate_limit_generate, "user"))
        elif rel.startswith("/export/") and not rel.startswith("/export/files/"):
            rules.append(("export", settings.rate_limit_export, "user"))
    if path != "/health":
        rules.append(("global", settings.rate_limit_default, "user"))
    return rules


class RateLimitMiddleware:
    """Pure ASGI middleware (no BaseHTTPMiddleware overhead or quirks)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http"
            or scope["method"] == "OPTIONS"  # CORS preflight
            or not settings.rate_limit_enabled
        ):
            await self.app(scope, receive, send)
            return

        ip = client_ip(scope)
        user = _bearer_user(scope)
        for name, spec, kind in _rules_for(scope["method"], scope["path"]):
            identity = f"u:{user}" if kind == "user" and user else f"ip:{ip}"
            wait = limiter.hit(f"{name}:{identity}", parse_rule(spec))
            if wait:
                from .errors import TooManyRequestsError

                exc = TooManyRequestsError(wait)
                response = error_response(
                    exc.status_code, exc.error, exc.detail, exc.headers
                )
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)
