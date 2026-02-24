"""ChatGPT OAuth authentication for the CLI.

Opens browser for OAuth flow, polls backend for completion.
Uses a CLI-generated session ID passed via query param so
tokens get linked to the CLI's session, not the browser's.
"""

import secrets
import webbrowser
from typing import Optional

import httpx


async def login(api_url: str) -> Optional[str]:
    """Start ChatGPT OAuth login flow.

    Generates a session ID, opens the browser with it, then polls
    the status endpoint until authentication completes.

    Args:
        api_url: Backend API URL.

    Returns:
        Session ID string if successful, None otherwise.
    """
    # Generate a session ID for the CLI to use
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
