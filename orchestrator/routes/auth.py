"""ChatGPT OAuth authentication routes.

Implements the OAuth 2.0 PKCE flow for authenticating with ChatGPT.

Endpoints:
1. GET  /api/auth/chatgpt/login    - Initiate OAuth, redirect to OpenAI
2. GET  /api/auth/chatgpt/callback - OAuth callback (code exchange)
3. GET  /api/auth/chatgpt/status   - Check current auth status
4. POST /api/auth/chatgpt/logout   - Clear stored tokens
5. POST /api/auth/chatgpt/refresh  - Force token refresh

The callback URL is auto-derived from the request origin, so it works
on both localhost (development) and deployed environments (Railway).
A fallback server on port 1455 is kept for backward compatibility with
the Codex CLI's registered redirect_uri.
"""

import asyncio
import base64
import hashlib
import json
import secrets
import time
from typing import Optional
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
from fastapi import APIRouter, HTTPException, Request

from orchestrator.config import get_chat_config
from orchestrator.logging_config import get_logger
from orchestrator.storage.db import get_db

logger = get_logger(__name__)

router = APIRouter(prefix="/api/auth/chatgpt", tags=["auth"])

# Codex CLI's hardcoded callback port (the only one whitelisted by OpenAI)
CALLBACK_PORT = 1455
CALLBACK_URI = f"http://localhost:{CALLBACK_PORT}/auth/callback"

# In-memory PKCE state storage (state -> {code_verifier, created_at})
_pending_auth: dict[str, dict] = {}

# Reference to the running callback server (set by start/stop helpers)
_callback_server: Optional[asyncio.AbstractServer] = None


# =========================================================================
# Crypto / JWT helpers
# =========================================================================


def _generate_pkce_pair() -> tuple[str, str]:
    """Generate PKCE code_verifier and code_challenge."""
    code_verifier = secrets.token_urlsafe(64)[:128]
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return code_verifier, code_challenge


def _extract_account_id_from_jwt(access_token: str) -> Optional[str]:
    """Extract chatgpt_account_id from the JWT access token."""
    try:
        parts = access_token.split(".")
        if len(parts) < 2:
            return None
        payload_b64 = parts[1]
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        auth_claim = payload.get("https://api.openai.com/auth", {})
        if isinstance(auth_claim, dict):
            return auth_claim.get("chatgpt_account_id")
        return None
    except Exception as e:
        logger.warning(
            "Failed to extract account_id from JWT",
            extra={"error": str(e)},
        )
        return None


# =========================================================================
# Token storage helpers
# =========================================================================


def _get_session_id(request: Request) -> Optional[str]:
    """Extract session ID from request state."""
    return getattr(request.state, "session_id", None)


async def _store_tokens(
    session_id: str,
    access_token: str,
    refresh_token: str,
    account_id: str,
    expires_in: int,
) -> None:
    """Store OAuth tokens in the database."""
    db = await get_db()
    expires_at = int(time.time()) + expires_in
    await db.conn.execute(
        """
        INSERT OR REPLACE INTO chatgpt_tokens
            (session_id, access_token, refresh_token, account_id, expires_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (session_id, access_token, refresh_token, account_id, expires_at),
    )
    await db.conn.commit()


async def _get_tokens(session_id: str) -> Optional[dict]:
    """Get stored tokens for a session."""
    db = await get_db()
    cursor = await db.conn.execute(
        "SELECT access_token, refresh_token, account_id, expires_at "
        "FROM chatgpt_tokens WHERE session_id = ?",
        (session_id,),
    )
    row = await cursor.fetchone()
    if not row:
        return None
    return {
        "access_token": row["access_token"],
        "refresh_token": row["refresh_token"],
        "account_id": row["account_id"],
        "expires_at": row["expires_at"],
    }


async def _delete_tokens(session_id: str) -> None:
    """Delete stored tokens for a session."""
    db = await get_db()
    await db.conn.execute(
        "DELETE FROM chatgpt_tokens WHERE session_id = ?",
        (session_id,),
    )
    await db.conn.commit()


async def _refresh_access_token(session_id: str, refresh_token: str) -> Optional[dict]:
    """Refresh the access token using the refresh token."""
    config = get_chat_config()
    chatgpt_config = config.chatgpt
    if not chatgpt_config:
        return None

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                chatgpt_config.token_url,
                data={
                    "grant_type": "refresh_token",
                    "client_id": chatgpt_config.client_id,
                    "refresh_token": refresh_token,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if response.status_code != 200:
                logger.warning(
                    "Token refresh failed",
                    extra={"status": response.status_code},
                )
                return None

            token_data = response.json()
            new_access = token_data.get("access_token")
            new_refresh = token_data.get("refresh_token", refresh_token)
            expires_in = token_data.get("expires_in", 3600)
            account_id = _extract_account_id_from_jwt(new_access) or ""

            await _store_tokens(
                session_id=session_id,
                access_token=new_access,
                refresh_token=new_refresh,
                account_id=account_id,
                expires_in=expires_in,
            )
            logger.info(
                "Token refreshed successfully",
                extra={"session_id": session_id[:8]},
            )
            return {
                "access_token": new_access,
                "refresh_token": new_refresh,
                "account_id": account_id,
                "expires_at": int(time.time()) + expires_in,
            }
    except Exception as e:
        logger.error("Token refresh error", extra={"error": str(e)})
        return None


async def get_valid_tokens(session_id: str) -> Optional[dict]:
    """Get valid tokens for a session, auto-refreshing if needed."""
    tokens = await _get_tokens(session_id)
    if not tokens:
        return None

    if tokens["expires_at"] < int(time.time()) + 300:
        logger.info(
            "Token expired or expiring soon, refreshing",
            extra={"session_id": session_id[:8]},
        )
        tokens = await _refresh_access_token(session_id, tokens["refresh_token"])
        if not tokens:
            await _delete_tokens(session_id)
            return None

    return tokens


# =========================================================================
# OAuth callback handling + fallback server on port 1455
# =========================================================================

_SUCCESS_HTML_BODY = """\
<!DOCTYPE html>
<html>
<head>
<title>Login Successful</title>
<style>
body{background:#09090b;color:#a1a1aa;font-family:monospace;
display:flex;align-items:center;justify-content:center;
height:100vh;margin:0}
</style>
</head>
<body>
<p>Login successful. This window will close.</p>
<script>
if(window.opener){
  window.opener.postMessage({type:'chatgpt-auth-success'},'*');
}
setTimeout(()=>window.close(),1000);
</script>
</body>
</html>"""

_ERROR_HTML_BODY_TEMPLATE = """\
<!DOCTYPE html>
<html>
<head><title>Login Failed</title>
<style>
body{{background:#09090b;color:#f87171;font-family:monospace;
display:flex;align-items:center;justify-content:center;
height:100vh;margin:0}}
</style>
</head>
<body><p>{message}</p></body>
</html>"""


def _wrap_http(html_body: str, status: int = 200) -> str:
    """Wrap HTML body with raw HTTP response headers (for port 1455)."""
    reason = {200: "OK", 400: "Bad Request", 502: "Bad Gateway"}.get(
        status, "Error"
    )
    return (
        f"HTTP/1.1 {status} {reason}\r\n"
        f"Content-Type: text/html; charset=utf-8\r\n"
        f"Connection: close\r\n"
        f"\r\n"
        f"{html_body}"
    )


async def _handle_callback_connection(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
) -> None:
    """Handle a single HTTP connection on the callback port (fallback)."""
    try:
        # Read the HTTP request line
        request_line = await asyncio.wait_for(reader.readline(), timeout=5.0)
        request_str = request_line.decode("utf-8", errors="replace")

        # Parse GET /auth/callback?code=...&state=... HTTP/1.1
        parts = request_str.strip().split(" ")
        if len(parts) < 2 or not parts[1].startswith("/auth/callback"):
            writer.write(
                _wrap_http(
                    _ERROR_HTML_BODY_TEMPLATE.format(message="Not found"), 400
                ).encode()
            )
            await writer.drain()
            writer.close()
            return

        # Parse query string
        parsed = urlparse(parts[1])
        qs = parse_qs(parsed.query)
        code = qs.get("code", [None])[0]
        state = qs.get("state", [None])[0]

        if not code or not state:
            writer.write(
                _wrap_http(
                    _ERROR_HTML_BODY_TEMPLATE.format(
                        message="Missing code or state parameter."
                    ),
                    400,
                ).encode()
            )
            await writer.drain()
            writer.close()
            return

        # Process the OAuth callback
        html_body, status = await _process_oauth_callback(code, state)
        writer.write(_wrap_http(html_body, status).encode())
        await writer.drain()
    except Exception as e:
        logger.error("Callback handler error", extra={"error": str(e)})
        try:
            writer.write(
                _wrap_http(
                    _ERROR_HTML_BODY_TEMPLATE.format(message="Internal error."),
                    500,
                ).encode()
            )
            await writer.drain()
        except Exception:
            pass
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


async def _process_oauth_callback(
    code: str, state: str
) -> tuple[str, int]:
    """Exchange auth code for tokens.

    Returns:
        (html_body, http_status_code) tuple.
    """
    config = get_chat_config()
    chatgpt_config = config.chatgpt
    if not chatgpt_config:
        return (
            _ERROR_HTML_BODY_TEMPLATE.format(
                message="ChatGPT not configured."
            ),
            500,
        )

    # Validate state
    pending = _pending_auth.pop(state, None)
    if not pending:
        return (
            _ERROR_HTML_BODY_TEMPLATE.format(
                message="Invalid or expired OAuth state."
            ),
            400,
        )

    code_verifier = pending["code_verifier"]
    redirect_uri = pending.get("redirect_uri", CALLBACK_URI)

    # Exchange code for tokens
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                chatgpt_config.token_url,
                data={
                    "grant_type": "authorization_code",
                    "client_id": chatgpt_config.client_id,
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "code_verifier": code_verifier,
                },
                headers={
                    "Content-Type": "application/x-www-form-urlencoded"
                },
            )

            if response.status_code != 200:
                logger.error(
                    "Token exchange failed",
                    extra={
                        "status": response.status_code,
                        "body": response.text[:500],
                    },
                )
                return (
                    _ERROR_HTML_BODY_TEMPLATE.format(
                        message="Token exchange failed. Try again.",
                    ),
                    502,
                )

            token_data = response.json()
    except httpx.HTTPError as e:
        logger.error(
            "Token exchange HTTP error", extra={"error": str(e)}
        )
        return (
            _ERROR_HTML_BODY_TEMPLATE.format(
                message="Failed to connect to OpenAI."
            ),
            502,
        )

    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token", "")
    expires_in = token_data.get("expires_in", 3600)

    if not access_token:
        return (
            _ERROR_HTML_BODY_TEMPLATE.format(
                message="No access token in response."
            ),
            502,
        )

    account_id = _extract_account_id_from_jwt(access_token) or ""

    # Session ID was stored when /login was called
    session_id = pending.get("session_id", secrets.token_urlsafe(32))

    await _store_tokens(
        session_id=session_id,
        access_token=access_token,
        refresh_token=refresh_token,
        account_id=account_id,
        expires_in=expires_in,
    )

    logger.info(
        "ChatGPT OAuth login successful",
        extra={
            "session_id": session_id[:8],
            "has_account_id": bool(account_id),
        },
    )

    return _SUCCESS_HTML_BODY, 200


async def start_callback_server() -> None:
    """Start the OAuth callback server on port 1455.

    This port is the only redirect_uri whitelisted by OpenAI for the
    Codex CLI client_id. Without it, local OAuth login won't work.
    Uses SO_REUSEADDR to reclaim the port from stale processes.
    """
    import socket

    global _callback_server
    try:
        # Create socket with SO_REUSEADDR to reclaim from stale processes
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", CALLBACK_PORT))
        sock.setblocking(False)

        _callback_server = await asyncio.start_server(
            _handle_callback_connection,
            sock=sock,
        )
        logger.info(
            f"OAuth callback server on port {CALLBACK_PORT}"
        )
    except OSError as e:
        logger.warning(
            f"OAuth callback server on port {CALLBACK_PORT} unavailable "
            f"({e}). Local ChatGPT login will not work — kill the process "
            f"on port {CALLBACK_PORT} and restart."
        )
        _callback_server = None


async def stop_callback_server() -> None:
    """Stop the OAuth callback server."""
    global _callback_server
    if _callback_server:
        _callback_server.close()
        await _callback_server.wait_closed()
        _callback_server = None
        logger.info("OAuth callback server stopped")


# =========================================================================
# FastAPI endpoints (on the main app)
# =========================================================================


def _get_callback_url(request: Request) -> str:
    """Derive OAuth callback URL.

    Priority:
    1. ChatGPT config callback_url (set via CHATGPT_CALLBACK_URL env var)
    2. Localhost requests → always use the Codex CLI whitelisted URI
       (http://localhost:1455/auth/callback) since that's the only
       redirect_uri registered with OpenAI for this client_id
    3. Non-localhost (Railway etc.) → derive from request origin
    """
    config = get_chat_config()
    chatgpt_config = config.chatgpt
    if chatgpt_config and chatgpt_config.callback_url:
        return chatgpt_config.callback_url

    # For localhost requests, always use the Codex CLI whitelisted URI
    host = request.headers.get("host", "localhost:9000")
    if "localhost" in host or "127.0.0.1" in host:
        return CALLBACK_URI

    # Non-localhost: derive from request headers (Railway sets x-forwarded-proto)
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    return f"{scheme}://{host}/api/auth/chatgpt/callback"


@router.get("/login")
async def chatgpt_login(request: Request, cli_session: Optional[str] = None):
    """Initiate ChatGPT OAuth PKCE flow.

    Redirects the user to OpenAI's auth page. The callback is handled
    by the /callback route on this same FastAPI app.

    Args:
        cli_session: Optional session ID from CLI client. When the CLI
            opens the browser for OAuth, it passes its session ID so
            tokens get linked to the CLI's session, not the browser's.
    """
    config = get_chat_config()
    chatgpt_config = config.chatgpt
    if not chatgpt_config or not chatgpt_config.enabled:
        raise HTTPException(
            status_code=404, detail="ChatGPT OAuth not enabled"
        )

    # Derive callback URL from request (works on localhost & Railway)
    callback_url = _get_callback_url(request)

    # Generate PKCE pair
    code_verifier, code_challenge = _generate_pkce_pair()

    # Generate state for CSRF protection
    state = secrets.token_urlsafe(32)

    # CLI passes its session ID explicitly; otherwise use cookie-based session
    session_id = cli_session or _get_session_id(request) or secrets.token_urlsafe(32)

    # Store PKCE state (including redirect_uri for token exchange)
    _pending_auth[state] = {
        "code_verifier": code_verifier,
        "session_id": session_id,
        "redirect_uri": callback_url,
        "created_at": time.time(),
    }

    # Clean up expired states (older than 10 minutes)
    now = time.time()
    expired = [
        s for s, v in _pending_auth.items() if now - v["created_at"] > 600
    ]
    for s in expired:
        _pending_auth.pop(s, None)

    logger.info(
        "ChatGPT OAuth login initiated",
        extra={"callback_url": callback_url},
    )

    # Build OAuth authorization URL (matching Codex CLI parameters)
    params = {
        "response_type": "code",
        "client_id": chatgpt_config.client_id,
        "redirect_uri": callback_url,
        "scope": "openid profile email offline_access",
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
        "id_token_add_organizations": "true",
        "codex_cli_simplified_flow": "true",
    }

    auth_url = f"{chatgpt_config.auth_url}?{urlencode(params)}"

    from fastapi.responses import RedirectResponse

    return RedirectResponse(url=auth_url)


@router.get("/callback")
async def chatgpt_callback(
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    error_description: Optional[str] = None,
):
    """Handle OAuth callback from OpenAI.

    OpenAI redirects here after the user authenticates. This route
    exchanges the authorization code for tokens and shows a result page.
    """
    from fastapi.responses import HTMLResponse

    # Handle OAuth errors (user denied, etc.)
    if error:
        msg = error_description or error
        logger.warning("OAuth callback error", extra={"error": msg})
        html = _ERROR_HTML_BODY_TEMPLATE.format(message=msg)
        return HTMLResponse(content=html, status_code=400)

    if not code or not state:
        html = _ERROR_HTML_BODY_TEMPLATE.format(
            message="Missing code or state parameter."
        )
        return HTMLResponse(content=html, status_code=400)

    html_body, status = await _process_oauth_callback(code, state)
    return HTMLResponse(content=html_body, status_code=status)


@router.get("/status")
async def chatgpt_status(request: Request, cli_session: Optional[str] = None):
    """Check current ChatGPT authentication status."""
    config = get_chat_config()
    chatgpt_config = config.chatgpt
    if not chatgpt_config or not chatgpt_config.enabled:
        return {"enabled": False, "authenticated": False}

    session_id = cli_session or _get_session_id(request)
    if not session_id:
        return {"enabled": True, "authenticated": False}

    tokens = await get_valid_tokens(session_id)
    if not tokens:
        return {"enabled": True, "authenticated": False}

    return {
        "enabled": True,
        "authenticated": True,
        "account_id": (tokens["account_id"][:8] + "..." if tokens["account_id"] else None),
        "expires_at": tokens["expires_at"],
        "model": chatgpt_config.default_model,
        "available_models": chatgpt_config.available_models,
    }


@router.post("/logout")
async def chatgpt_logout(request: Request):
    """Clear stored ChatGPT tokens."""
    session_id = _get_session_id(request)
    if session_id:
        await _delete_tokens(session_id)
        logger.info("ChatGPT logout", extra={"session_id": session_id[:8]})
    return {"status": "logged_out"}


@router.post("/refresh")
async def chatgpt_force_refresh(request: Request):
    """Force refresh the ChatGPT access token."""
    session_id = _get_session_id(request)
    if not session_id:
        raise HTTPException(status_code=401, detail="No session")

    tokens = await _get_tokens(session_id)
    if not tokens:
        raise HTTPException(status_code=401, detail="Not authenticated")

    refreshed = await _refresh_access_token(session_id, tokens["refresh_token"])
    if not refreshed:
        await _delete_tokens(session_id)
        raise HTTPException(
            status_code=401,
            detail="Token refresh failed. Please re-login.",
        )

    return {
        "status": "refreshed",
        "expires_at": refreshed["expires_at"],
    }
