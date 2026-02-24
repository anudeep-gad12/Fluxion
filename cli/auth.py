"""ChatGPT OAuth authentication for the CLI.

Opens browser for OAuth flow, polls backend for status.
"""

import asyncio
import webbrowser
from typing import Optional

import httpx


async def login(api_url: str) -> Optional[str]:
    """Start ChatGPT OAuth login flow.

    Opens browser to the OAuth login page and polls for completion.

    Args:
        api_url: Backend API URL.

    Returns:
        Session cookie string if successful, None otherwise.
    """
    login_url = f"{api_url}/api/auth/chatgpt/login"

    # Open browser
    webbrowser.open(login_url)

    # Poll for auth completion
    async with httpx.AsyncClient(base_url=api_url, timeout=5.0) as client:
        for _ in range(60):  # 5 minutes max
            await asyncio.sleep(5)
            try:
                response = await client.get("/api/auth/status")
                if response.status_code == 200:
                    data = response.json()
                    if data.get("authenticated"):
                        # Extract session cookie
                        for cookie in response.cookies.jar:
                            if cookie.name == "demo_session":
                                return cookie.value
                        return data.get("session_id")
            except Exception:
                continue

    return None


async def check_auth(api_url: str, session_cookie: Optional[str] = None) -> bool:
    """Check if current session is authenticated.

    Args:
        api_url: Backend API URL.
        session_cookie: Session cookie to check.

    Returns:
        True if authenticated.
    """
    cookies = {}
    if session_cookie:
        cookies["demo_session"] = session_cookie

    try:
        async with httpx.AsyncClient(
            base_url=api_url, cookies=cookies, timeout=5.0
        ) as client:
            response = await client.get("/api/auth/status")
            if response.status_code == 200:
                return response.json().get("authenticated", False)
    except Exception:
        pass

    return False
