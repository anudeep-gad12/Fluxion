"""ChatGPT OAuth authentication for the CLI.

Opens browser for OAuth flow, polls backend for completion.
Uses a CLI-generated session ID passed via query param so
tokens get linked to the CLI's session, not the browser's.

Backup/restore: After login, refresh tokens are saved to
~/.config/reasoner/chatgpt_auth.json so they survive DB wipes.
"""

import json
import secrets
import webbrowser
from pathlib import Path
from typing import Optional

import httpx

_AUTH_BACKUP_PATH = Path.home() / ".config" / "reasoner" / "chatgpt_auth.json"


async def login(api_url: str, existing_session: Optional[str] = None) -> Optional[str]:
    """Start or resume ChatGPT OAuth login flow.

    If existing_session is provided and still valid, returns it
    immediately without re-authenticating.

    Args:
        api_url: Backend API URL.
        existing_session: Existing CLI session ID to reuse if valid.

    Returns:
        Session ID string if successful, None otherwise.
    """
    # Check if existing session is still valid
    if existing_session:
        auth = await check_auth(api_url, existing_session)
        if auth.get("authenticated"):
            return existing_session

    # Generate a new session ID for the CLI to use
    session_id = secrets.token_urlsafe(32)

    # Open browser with CLI session so tokens get stored under our ID
    login_url = f"{api_url}/api/auth/chatgpt/login?cli_session={session_id}"
    webbrowser.open(login_url)

    # Poll for auth completion (check every 3s for up to 5 minutes)
    async with httpx.AsyncClient(base_url=api_url, timeout=5.0) as client:
        for _ in range(100):
            import asyncio
            await asyncio.sleep(3)
            try:
                response = await client.get(
                    "/api/auth/chatgpt/status",
                    params={"cli_session": session_id},
                )
                if response.status_code == 200:
                    data = response.json()
                    if data.get("authenticated"):
                        return session_id
            except Exception:
                continue

    return None


async def check_auth(api_url: str, session_id: Optional[str] = None) -> dict:
    """Check if current session is authenticated with ChatGPT.

    Args:
        api_url: Backend API URL.
        session_id: CLI session ID to check.

    Returns:
        Status dict with 'authenticated' bool and optional details.
    """
    if not session_id:
        return {"authenticated": False}

    try:
        async with httpx.AsyncClient(base_url=api_url, timeout=5.0) as client:
            response = await client.get(
                "/api/auth/chatgpt/status",
                params={"cli_session": session_id},
            )
            if response.status_code == 200:
                return response.json()
    except Exception:
        pass

    return {"authenticated": False}


async def backup_tokens(api_url: str, session_id: str) -> None:
    """Export and save refresh token to local config dir.

    Called after successful login so tokens survive DB wipes.

    Args:
        api_url: Backend API URL.
        session_id: CLI session ID.
    """
    try:
        async with httpx.AsyncClient(base_url=api_url, timeout=5.0) as client:
            resp = await client.get(
                "/api/auth/chatgpt/export",
                params={"cli_session": session_id},
            )
            if resp.status_code == 200:
                _AUTH_BACKUP_PATH.parent.mkdir(parents=True, exist_ok=True)
                _AUTH_BACKUP_PATH.write_text(json.dumps(resp.json()))
    except Exception:
        pass


async def try_restore(api_url: str, session_id: str) -> bool:
    """Try restoring tokens from local backup file.

    Called on startup when the DB has no valid tokens.

    Args:
        api_url: Backend API URL.
        session_id: CLI session ID to restore for.

    Returns:
        True if tokens were restored successfully.
    """
    if not _AUTH_BACKUP_PATH.exists():
        return False

    try:
        data = json.loads(_AUTH_BACKUP_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return False

    # Only restore if the backup matches this session
    if data.get("session_id") != session_id:
        return False

    refresh_token = data.get("refresh_token")
    if not refresh_token:
        return False

    try:
        async with httpx.AsyncClient(base_url=api_url, timeout=10.0) as client:
            resp = await client.post(
                "/api/auth/chatgpt/restore",
                json={
                    "session_id": session_id,
                    "refresh_token": refresh_token,
                },
            )
            return resp.status_code == 200
    except Exception:
        return False
