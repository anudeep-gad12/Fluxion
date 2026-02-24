"""HTTP + SSE client for the Reasoner backend.

Uses httpx for HTTP requests and httpx-sse for Server-Sent Events streaming.
"""

import json
from typing import Any, AsyncIterator, Dict, Optional

import httpx
from httpx_sse import aconnect_sse

from .config import CLIConfig


class APIClient:
    """Client for the Reasoner FastAPI backend.

    Handles agent run creation, SSE streaming, tool approval, and auth.
    """

    def __init__(self, config: CLIConfig) -> None:
        """Initialize API client.

        Args:
            config: CLI configuration with api_url, provider, etc.
        """
        self._config = config
        self._base_url = config.api_url

        headers: Dict[str, str] = {}
        if config.provider and config.provider != "default":
            headers["X-Provider"] = config.provider
        if config.model:
            headers["X-Model"] = config.model

        cookies = {}
        if config.session_cookie:
            cookies["demo_session"] = config.session_cookie

        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers=headers,
            cookies=cookies,
            timeout=30.0,
        )

    async def create_agent_run(
        self,
        query: str,
        max_steps: Optional[int] = None,
        conversation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new agent run.

        Args:
            query: User's query.
            max_steps: Maximum agent steps.
            conversation_id: Optional conversation context.

        Returns:
            Dict with run_id, stream_url, stream_token.
        """
        payload: Dict[str, Any] = {
            "query": query,
            "max_steps": max_steps or self._config.max_steps,
            "filesystem_enabled": self._config.mode == "agent",
            "working_dir": self._config.working_dir,
            "permission_policy": self._config.permission,
        }
        if conversation_id:
            payload["conversation_id"] = conversation_id

        response = await self._client.post("/api/agent/runs", json=payload)
        response.raise_for_status()
        return response.json()

    async def stream_agent_events(
        self,
        run_id: str,
        stream_token: str,
        since_seq: int = 0,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Stream SSE events for an agent run.

        Args:
            run_id: Agent run ID.
            stream_token: Auth token for the stream.
            since_seq: Resume from this sequence number.

        Yields:
            Parsed SSE event dicts with 'event' and 'data' keys.
        """
        url = f"/api/agent/runs/{run_id}/stream"
        params = {"token": stream_token, "since_seq": since_seq}

        async with aconnect_sse(
            self._client, "GET", url, params=params, timeout=httpx.Timeout(None)
        ) as event_source:
            async for sse in event_source.aiter_sse():
                try:
                    data = json.loads(sse.data) if sse.data else {}
                except json.JSONDecodeError:
                    data = {"raw": sse.data}

                yield {
                    "event": sse.event,
                    "data": data,
                }

    async def approve_tool(self, run_id: str, tool_call_id: str) -> Dict[str, Any]:
        """Approve a pending tool call.

        Args:
            run_id: Agent run ID.
            tool_call_id: Tool call to approve.

        Returns:
            Response dict.
        """
        response = await self._client.post(
            f"/api/agent/runs/{run_id}/approve/{tool_call_id}"
        )
        response.raise_for_status()
        return response.json()

    async def deny_tool(self, run_id: str, tool_call_id: str) -> Dict[str, Any]:
        """Deny a pending tool call.

        Args:
            run_id: Agent run ID.
            tool_call_id: Tool call to deny.

        Returns:
            Response dict.
        """
        response = await self._client.post(
            f"/api/agent/runs/{run_id}/deny/{tool_call_id}"
        )
        response.raise_for_status()
        return response.json()

    async def cancel_run(self, run_id: str) -> Dict[str, Any]:
        """Cancel an active agent run.

        Args:
            run_id: Agent run ID.

        Returns:
            Response dict.
        """
        response = await self._client.post(f"/api/agent/runs/{run_id}/cancel")
        response.raise_for_status()
        return response.json()

    async def health_check(self) -> bool:
        """Check if backend is reachable.

        Returns:
            True if backend responds, False otherwise.
        """
        try:
            response = await self._client.get("/api/health")
            return response.status_code == 200
        except Exception:
            return False

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()
