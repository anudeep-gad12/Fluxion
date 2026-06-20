"""Web content extraction tool using Parallel.ai Extract API.

This tool extracts and summarizes content from web pages.
It is IDEMPOTENT - safe to retry on crash.
"""

import asyncio
import random
import time
from typing import Any, Dict, List, Optional

import httpx

from orchestrator.logging_config import get_logger

from .base import ToolExecutionError, ToolResult, ToolSchema

logger = get_logger(__name__)


class WebExtractTool:
    """Content extraction using Parallel.ai API.

    Attributes:
        name: "web_extract"
        is_idempotent: True
    """

    def __init__(
        self,
        base_url: str = "https://api.parallel.ai/v1beta",
        api_key: Optional[str] = None,
        max_urls: int = 3,
        timeout_ms: int = 30000,
        max_retries: int = 3,
        base_delay: float = 1.0,
    ) -> None:
        """Initialize web extract tool.

        Args:
            base_url: Parallel.ai API base URL.
            api_key: API key for authentication.
            max_urls: Maximum URLs per request.
            timeout_ms: Request timeout in milliseconds.
            max_retries: Maximum retry attempts.
            base_delay: Base delay for exponential backoff.
        """
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._max_urls = max_urls
        self._timeout = timeout_ms / 1000.0
        self._max_retries = max_retries
        self._base_delay = base_delay

        headers = {
            "Content-Type": "application/json",
            "parallel-beta": "search-extract-2025-10-10",  # Required for extract API
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
        return "web_extract"

    @property
    def schema(self) -> ToolSchema:
        """OpenAI function schema."""
        return ToolSchema(
            name="web_extract",
            description="Extract and summarize content from web pages. Use after web_search to get full content from URLs.",
            parameters={
                "type": "object",
                "properties": {
                    "urls": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "URLs to extract content from (max 3)",
                        "maxItems": 3,
                    },
                },
                "required": ["urls"],
            },
            is_idempotent=True,
        )

    async def execute(self, urls: List[str], **kwargs: Any) -> ToolResult:
        """Execute content extraction.

        Args:
            urls: List of URLs to extract content from.
            **kwargs: Additional arguments (ignored).

        Returns:
            ToolResult with extracted content.
        """
        start_time = time.perf_counter()

        # Validate and limit URLs
        if not urls:
            return ToolResult(
                success=False,
                result_summary="No URLs provided",
                error_message="urls list is empty",
                duration_ms=0,
            )

        urls = urls[: self._max_urls]

        try:
            response_data = await self._request_with_retry(urls=urls)

            duration_ms = int((time.perf_counter() - start_time) * 1000)

            # Parse results - API returns "results" with extracted content
            results = response_data.get("results", [])
            errors = response_data.get("errors", [])

            # Results are successful extractions, errors are failures
            successful = results
            failed = errors

            # 1-line summary for DB
            result_summary = f"Extracted {len(successful)}/{len(urls)} URLs successfully"
            failure_items = [
                {
                    "url": item.get("url", "") if isinstance(item, dict) else "",
                    "error": (
                        item.get("error")
                        or item.get("message")
                        or item.get("status")
                        or str(item)
                    ) if isinstance(item, dict) else str(item),
                    "status": item.get("status") if isinstance(item, dict) else None,
                }
                for item in failed
            ]
            if failure_items:
                failed_preview = ", ".join(
                    (
                        f"{failure['url'] or 'unknown'}"
                        + (f" {failure['status']}" if failure.get("status") else "")
                    )[:80]
                    for failure in failure_items[:3]
                )
                result_summary += f"; failed: {failed_preview}"

            # Full data for in-memory use - combine excerpts into content
            result_data = {
                "extractions": [
                    {
                        "url": r.get("url", ""),
                        "title": r.get("title", ""),
                        "content": r.get("full_content") or "\n\n".join(r.get("excerpts", [])),
                        "success": True,
                    }
                    for r in results
                ],
                "failures": failure_items,
            }

            return ToolResult(
                success=len(successful) > 0,  # Partial success is OK
                result_summary=result_summary,
                result_data=result_data,
                duration_ms=duration_ms,
                metadata={
                    "successful_count": len(successful),
                    "failed_count": len(failed),
                },
            )

        except asyncio.TimeoutError:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            return ToolResult(
                success=False,
                result_summary=f"Extraction timed out for {len(urls)} URLs",
                error_message="Request timed out",
                duration_ms=duration_ms,
            )
        except ToolExecutionError as e:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            return ToolResult(
                success=False,
                result_summary=f"Extraction failed for {len(urls)} URLs",
                error_message=str(e),
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            logger.error(
                "Web extract failed", extra={"urls": urls[:3], "error": str(e)}
            )
            return ToolResult(
                success=False,
                result_summary=f"Extraction failed for {len(urls)} URLs",
                error_message=str(e),
                duration_ms=duration_ms,
            )

    async def _request_with_retry(self, urls: List[str]) -> Dict[str, Any]:
        """Make extract request with exponential backoff.

        Args:
            urls: URLs to extract.

        Returns:
            API response data.

        Raises:
            ToolExecutionError: If all retries fail.
        """
        last_error: Optional[str] = None

        for attempt in range(1, self._max_retries + 1):
            try:
                response = await self._client.post(
                    f"{self._base_url}/extract",
                    json={"urls": urls},
                )

                if response.status_code == 200:
                    return response.json()

                if response.status_code in (429, 500, 502, 503, 504):
                    last_error = f"HTTP {response.status_code}"
                    logger.warning(
                        "Retryable extract error",
                        extra={"status": response.status_code, "attempt": attempt},
                    )
                else:
                    response.raise_for_status()

            except httpx.TimeoutException:
                last_error = "Timeout"
                logger.warning("Extract timeout", extra={"attempt": attempt})
            except httpx.ConnectError as e:
                last_error = f"Connection error: {e}"
                logger.warning(
                    "Extract connection error",
                    extra={"attempt": attempt, "error": str(e)},
                )
            except httpx.HTTPStatusError as e:
                # Non-retryable HTTP error
                raise ToolExecutionError(f"HTTP error: {e.response.status_code}")

            # Backoff before retry
            if attempt < self._max_retries:
                delay = self._base_delay * (2 ** (attempt - 1))
                jitter = delay * random.uniform(0.1, 0.3)
                await asyncio.sleep(delay + jitter)

        raise ToolExecutionError(
            f"Extract failed after {self._max_retries} attempts: {last_error}"
        )

    async def health_check(self) -> bool:
        """Check if Parallel.ai API is reachable.

        Returns:
            True if healthy, False otherwise.
        """
        try:
            # Try a simple extract to verify API is working
            response = await self._client.post(
                f"{self._base_url}/extract",
                json={"urls": ["https://example.com"]},
                timeout=5.0,
            )
            return response.status_code == 200
        except Exception:
            return False

    async def close(self) -> None:
        """Close HTTP client."""
        await self._client.aclose()
