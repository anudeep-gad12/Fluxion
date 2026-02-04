"""Session middleware for demo mode user isolation.

Mints session cookies for anonymous users and sets request.state attributes
for session-scoped data access.

Note: This provides identity without authentication - users are identified
by their cookie but not authenticated. For production multi-tenant use,
consider signed cookies or proper auth.
"""

import secrets
import uuid
from typing import Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from orchestrator.config import get_chat_config
from orchestrator.logging_config import get_logger

logger = get_logger(__name__)

COOKIE_NAME = "demo_session"
COOKIE_MAX_AGE = 30 * 24 * 60 * 60  # 30 days in seconds


def _is_secure_context() -> bool:
    """Check if we're in a secure context (production with HTTPS)."""
    import os

    # In production, SERVE_STATIC=true indicates Railway/production deployment
    return os.environ.get("SERVE_STATIC", "false").lower() == "true"


class SessionMiddleware(BaseHTTPMiddleware):
    """Middleware for session-based user isolation in demo mode.

    Sets request.state attributes:
    - session_id: UUID identifying the user's session
    - is_owner: True if user authenticated as owner

    Only active when demo mode is enabled. When disabled, all requests
    get is_owner=True (full access).
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        """Process request with session handling.

        Args:
            request: Incoming request.
            call_next: Next middleware/handler.

        Returns:
            Response with session cookie set/refreshed.
        """
        config = get_chat_config()

        # Skip session handling if demo mode disabled
        if not config.demo or not config.demo.enabled:
            request.state.session_id = None
            request.state.is_owner = True  # No demo mode = full access
            return await call_next(request)

        # Check owner authentication
        is_owner = self._check_owner(request, config.demo.owner_secret)

        # Get or create session ID
        session_id = self._get_session_id(request)
        new_session = False
        if not session_id:
            session_id = str(uuid.uuid4())
            new_session = True
            logger.debug(
                "Minted new session",
                extra={"session_id": session_id, "is_owner": is_owner},
            )

        # Set request state for downstream handlers
        request.state.session_id = session_id
        request.state.is_owner = is_owner

        # Process request
        response = await call_next(request)

        # Set/refresh session cookie (always refresh to extend TTL)
        self._set_session_cookie(response, session_id)

        return response

    def _check_owner(self, request: Request, owner_secret: str) -> bool:
        """Check if request is from the owner.

        Owner can authenticate via:
        1. ?owner=<secret> query parameter
        2. X-Owner-Token: <secret> header

        Uses constant-time comparison to prevent timing attacks.

        Args:
            request: Incoming request.
            owner_secret: Expected owner secret from config.

        Returns:
            True if owner authenticated, False otherwise.
        """
        if not owner_secret:
            return False

        # Check query parameter
        query_token = request.query_params.get("owner")
        if query_token and secrets.compare_digest(query_token, owner_secret):
            logger.debug("Owner authenticated via query param")
            return True

        # Check header
        header_token = request.headers.get("X-Owner-Token")
        if header_token and secrets.compare_digest(header_token, owner_secret):
            logger.debug("Owner authenticated via header")
            return True

        return False

    def _get_session_id(self, request: Request) -> Optional[str]:
        """Get existing session ID from cookie.

        Args:
            request: Incoming request.

        Returns:
            Session ID if cookie exists, None otherwise.
        """
        return request.cookies.get(COOKIE_NAME)

    def _set_session_cookie(self, response: Response, session_id: str) -> None:
        """Set session cookie on response.

        Args:
            response: Outgoing response.
            session_id: Session ID to set.
        """
        response.set_cookie(
            key=COOKIE_NAME,
            value=session_id,
            max_age=COOKIE_MAX_AGE,
            httponly=True,
            samesite="lax",
            secure=_is_secure_context(),
        )
