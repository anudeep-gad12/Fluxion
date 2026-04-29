"""Rate limiting middleware for demo mode.

Provides IP-based rate limiting for expensive endpoints without authentication.
Tracks requests in-memory with sliding time windows.

Note: For multi-worker deployment, use Redis instead of in-memory storage.
"""

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, Tuple

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from orchestrator.config import get_chat_config
from orchestrator.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class RateLimitWindow:
    """Track requests in a time window."""

    count: int = 0
    window_start: float = field(default_factory=time.time)


class InMemoryRateLimiter:
    """Simple in-memory rate limiter with sliding window.

    Note: For multi-worker deployment, use Redis instead.
    """

    def __init__(self) -> None:
        # Dict[ip_address, Dict[endpoint_key, RateLimitWindow]]
        self._windows: Dict[str, Dict[str, RateLimitWindow]] = defaultdict(dict)

    def reset(self) -> None:
        """Clear all tracked rate-limit windows.

        Used by tests and safe operational resets. Production rate limits are
        in-memory today, so clearing the process-local map is sufficient.
        """
        self._windows.clear()

    def check_rate_limit(
        self,
        ip: str,
        endpoint_key: str,
        max_requests: int,
        window_seconds: int,
    ) -> Tuple[bool, int, int]:
        """Check if request is within rate limit.

        Args:
            ip: Client IP address.
            endpoint_key: Type of endpoint (e.g., "agent", "chat").
            max_requests: Maximum requests allowed in window.
            window_seconds: Window duration in seconds.

        Returns:
            Tuple of (allowed, remaining, reset_seconds):
            - allowed: Whether request is allowed
            - remaining: Remaining quota in current window
            - reset_seconds: Seconds until window resets
        """
        now = time.time()
        windows = self._windows[ip]

        if endpoint_key not in windows:
            windows[endpoint_key] = RateLimitWindow(count=1, window_start=now)
            return True, max_requests - 1, window_seconds

        window = windows[endpoint_key]
        elapsed = now - window.window_start

        # Check if window has expired
        if elapsed >= window_seconds:
            # Reset window
            window.count = 1
            window.window_start = now
            return True, max_requests - 1, window_seconds

        # Window still active
        reset_seconds = int(window_seconds - elapsed)

        if window.count >= max_requests:
            return False, 0, reset_seconds

        window.count += 1
        return True, max_requests - window.count, reset_seconds


# Singleton instance
_rate_limiter = InMemoryRateLimiter()


def get_client_ip(request: Request) -> str:
    """Extract client IP, only trusting proxy headers in production.

    Only trusts X-Forwarded-For/X-Real-IP when running behind a known
    reverse proxy (SERVE_STATIC=true indicates Railway/production where
    the load balancer sets these headers). In development, uses the
    direct connection IP to prevent header spoofing.

    Args:
        request: FastAPI request object.

    Returns:
        Client IP address string.
    """
    import os
    is_behind_proxy = os.environ.get("SERVE_STATIC", "false").lower() == "true"

    if is_behind_proxy:
        # Trust proxy headers only in production behind load balancer
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

    # Direct connection IP (always trustworthy)
    if request.client:
        return request.client.host
    return "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce rate limits on expensive endpoints.

    Only active when demo mode is enabled in config.
    Limits POST requests to agent and chat run endpoints.
    """

    # Endpoint patterns to rate limit (path prefix -> endpoint type)
    RATE_LIMITED_ENDPOINTS = {
        "/api/agent/runs": "agent",
        "/api/runs": "chat",
        "/api/conversations/": "chat",  # POST to /conversations/{id}/runs
    }

    async def dispatch(self, request: Request, call_next):
        """Process request with rate limiting.

        Args:
            request: Incoming request.
            call_next: Next middleware/handler.

        Returns:
            Response (429 if rate limited, otherwise from handler).
        """
        config = get_chat_config()

        # Skip if demo mode disabled
        if not config.demo or not config.demo.enabled:
            return await call_next(request)

        # Only rate limit POST requests (writes)
        if request.method != "POST":
            return await call_next(request)

        # Check if this endpoint should be rate limited
        path = request.url.path
        endpoint_type = None
        for pattern, etype in self.RATE_LIMITED_ENDPOINTS.items():
            if path.startswith(pattern):
                endpoint_type = etype
                break

        if not endpoint_type:
            return await call_next(request)

        # Get client IP
        client_ip = get_client_ip(request)

        # Check whitelist
        if client_ip in config.demo.whitelist_ips:
            return await call_next(request)

        # Determine limits based on endpoint type
        rate_config = config.demo.rate_limit
        if endpoint_type == "agent":
            max_requests = rate_config.max_agent_runs_per_hour
        else:
            max_requests = rate_config.max_chat_runs_per_hour

        window_seconds = rate_config.window_seconds

        # Check rate limit
        allowed, remaining, reset_seconds = _rate_limiter.check_rate_limit(
            ip=client_ip,
            endpoint_key=endpoint_type,
            max_requests=max_requests,
            window_seconds=window_seconds,
        )

        if not allowed:
            logger.warning(
                "Rate limit exceeded",
                extra={
                    "client_ip": client_ip,
                    "endpoint_type": endpoint_type,
                    "path": path,
                    "max_requests": max_requests,
                    "window_seconds": window_seconds,
                },
            )
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limit_exceeded",
                    "message": f"Too many requests. You can make {max_requests} {endpoint_type} runs per hour.",
                    "retry_after_seconds": reset_seconds,
                },
                headers={
                    "Retry-After": str(reset_seconds),
                    "X-RateLimit-Limit": str(max_requests),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_seconds),
                },
            )

        # Request allowed - add rate limit headers to response
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(max_requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_seconds)

        return response
