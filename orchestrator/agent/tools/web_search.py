"""Web search tool using Parallel.ai Search API.

This tool searches the web and returns relevant results with snippets.
It is IDEMPOTENT - safe to retry on crash.
"""

import asyncio
import random
import time
from typing import Any, Dict, Optional

import httpx

from orchestrator.logging_config import get_logger

from .base import ToolExecutionError, ToolResult, ToolSchema

logger = get_logger(__name__)


class WebSearchTool:
    """Web search using Parallel.ai API.

    Attributes:
        name: "web_search"
        is_idempotent: True
    """

    def __init__(
        self,
        base_url: str = "https://api.parallel.ai/v1beta",
        api_key: Optional[str] = None,
        max_results: int = 10,
        timeout_ms: int = 15000,
        max_retries: int = 3,
        base_delay: float = 1.0,
    ) -> None:
        """Initialize web search tool.

        Args:
            base_url: Parallel.ai API base URL.
            api_key: API key for authentication.
            max_results: Maximum search results to return.
            timeout_ms: Request timeout in milliseconds.
            max_retries: Maximum retry attempts.
            base_delay: Base delay for exponential backoff.
        """
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._max_results = max_results
        self._timeout = timeout_ms / 1000.0
        self._max_retries = max_retries
        self._base_delay = base_delay

        headers = {
            "Content-Type": "application/json",
            "parallel-beta": "search-extract-2025-10-10",  # Required for search API
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        self._client = httpx.AsyncClient(
            timeout=self._timeout,
            headers=headers,
        )

    @property
    def name(self) -> str:
        """Tool name."""
        return "web_search"

    @property
    def schema(self) -> ToolSchema:
        """OpenAI function schema."""
        return ToolSchema(
            name="web_search",
            description="Search the web for information. Returns relevant URLs with titles and snippets.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query",
                    },
                    "num_results": {
                        "type": "integer",
                        "description": "Number of results (max 10)",
                        "default": 10,
                        "maximum": 10,
                    },
                },
                "required": ["query"],
            },
            is_idempotent=True,
        )

    async def execute(
        self, query: str, num_results: int = 10, **kwargs: Any
    ) -> ToolResult:
        """Execute web search.

        Args:
            query: Search query string.
            num_results: Number of results to return (max 10).
            **kwargs: Additional arguments (ignored).

        Returns:
            ToolResult with search results.
        """
        start_time = time.perf_counter()
        num_results = min(num_results, self._max_results)

        try:
            response_data = await self._request_with_retry(
                query=query,
                num_results=num_results,
            )

            duration_ms = int((time.perf_counter() - start_time) * 1000)

            # Parse results
            results = response_data.get("results", [])

            # Create 1-line summary for DB
            query_preview = query[:50] + "..." if len(query) > 50 else query
            result_summary = f"Found {len(results)} results for '{query_preview}'"

            # Full data for in-memory use
            result_data = {
                "query": query,
                "results": [
                    {
                        "url": r.get("url", ""),
                        "title": r.get("title", ""),
                        "snippet": r.get("snippet", ""),
                    }
                    for r in results
                ],
            }

            return ToolResult(
                success=True,
                result_summary=result_summary,
                result_data=result_data,
                duration_ms=duration_ms,
            )

        except asyncio.TimeoutError:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            query_preview = query[:50] + "..." if len(query) > 50 else query
            return ToolResult(
                success=False,
                result_summary=f"Search timed out for '{query_preview}'",
                error_message="Request timed out",
                duration_ms=duration_ms,
            )
        except ToolExecutionError as e:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            query_preview = query[:50] + "..." if len(query) > 50 else query
            return ToolResult(
                success=False,
                result_summary=f"Search failed for '{query_preview}'",
                error_message=str(e),
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            query_preview = query[:50] + "..." if len(query) > 50 else query
            logger.error("Web search failed", extra={"query": query, "error": str(e)})
            return ToolResult(
                success=False,
                result_summary=f"Search failed for '{query_preview}'",
                error_message=str(e),
                duration_ms=duration_ms,
            )

    async def _request_with_retry(
        self, query: str, num_results: int
    ) -> Dict[str, Any]:
        """Make search request with exponential backoff.

        Args:
            query: Search query.
            num_results: Number of results.

        Returns:
            API response data.

        Raises:
            ToolExecutionError: If all retries fail.
        """
        last_error: Optional[str] = None

        for attempt in range(1, self._max_retries + 1):
            try:
                # Parallel.ai API requires 'objective' or 'search_queries', not 'query'
                response = await self._client.post(
                    f"{self._base_url}/search",
                    json={
                        "objective": query,
                        "max_results": num_results,
                    },
                )

                if response.status_code == 200:
                    return response.json()

                if response.status_code in (429, 500, 502, 503, 504):
                    last_error = f"HTTP {response.status_code}"
                    logger.warning(
                        "Retryable search error",
                        extra={"status": response.status_code, "attempt": attempt},
                    )
                else:
                    body = response.text[:500]
                    raise ToolExecutionError(
                        f"HTTP {response.status_code}: {body or response.reason_phrase}"
                    )

            except httpx.TimeoutException:
                last_error = "Timeout"
                logger.warning("Search timeout", extra={"attempt": attempt})
            except httpx.ConnectError as e:
                last_error = f"Connection error: {e}"
                logger.warning(
                    "Search connection error",
                    extra={"attempt": attempt, "error": str(e)},
                )
            except httpx.HTTPStatusError as e:
                body = e.response.text[:500]
                raise ToolExecutionError(
                    f"HTTP {e.response.status_code}: {body or e.response.reason_phrase}"
                )

            # Backoff before retry
            if attempt < self._max_retries:
                delay = self._base_delay * (2 ** (attempt - 1))
                jitter = delay * random.uniform(0.1, 0.3)
                await asyncio.sleep(delay + jitter)

        raise ToolExecutionError(
            f"Search failed after {self._max_retries} attempts: {last_error}"
        )

    async def health_check(self) -> bool:
        """Check if Parallel.ai API is reachable.

        Returns:
            True if healthy, False otherwise.
        """
        try:
            # Try a simple search to verify API is working
            response = await self._client.post(
                f"{self._base_url}/search",
                json={"objective": "test", "max_results": 1},
                timeout=5.0,
            )
            return response.status_code == 200
        except Exception:
            return False

    async def close(self) -> None:
        """Close HTTP client."""
        await self._client.aclose()
