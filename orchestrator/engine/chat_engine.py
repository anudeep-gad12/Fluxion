"""Chat engine with pluggable thinking strategies.

This module provides a chat interface that:
1. Loads conversation history
2. Builds messages with system prompt
3. Optionally applies thinking strategies (direct, vote, CoT, etc.)
4. Calls the model
5. Stores trace including thinking steps
6. Returns result

All settings come from chat_config.yaml.
"""

import asyncio
import logging
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

import httpx

from orchestrator.config import ChatConfig, get_chat_config
from orchestrator.providers import create_provider, LLMProvider
from orchestrator.storage.db import get_db
from orchestrator.storage.repositories.conversation_repo import ConversationRepo
from orchestrator.storage.repositories.trace_repo import TraceRepo
from orchestrator.thinking import ThinkingOrchestrator, StreamParser
from orchestrator.utils.tokens import get_token_counter

logger = logging.getLogger(__name__)


@dataclass
class ChatResult:
    """Result of a chat call."""
    run_id: str
    conversation_id: str
    message: str
    response: str
    status: str  # "succeeded" or "failed"
    error: Optional[str] = None
    timing_ms: int = 0
    token_usage: Optional[dict] = None
    thinking_summary: str = ""  # Cleaned thinking for UI display


class ChatEngine:
    """Chat engine with pluggable thinking strategies.

    Supports different reasoning approaches via ThinkingOrchestrator:
    - direct: No explicit thinking, just generate answer (fastest)
    - cot: Chain-of-Thought with <think>/<answer> tags (+17% on reasoning)
    - auto: Auto-detect complexity and route to appropriate strategy
    - self_consistency: Multiple paths + voting (coming soon)
    - self_reflection: Critique and revise loop (coming soon)
    - chain_of_draft: Minimal drafts per step (coming soon)
    """

    def __init__(self, config: Optional[ChatConfig] = None):
        """Initialize the chat engine.

        Args:
            config: Chat configuration. If None, loads from chat_config.yaml.
        """
        self.config = config or get_chat_config()

        # Initialize LLM provider (uses provider config for endpoint selection, retries, etc.)
        self._provider = create_provider(self.config.provider)

        # Legacy client for methods that need direct HTTP access (logprobs, etc.)
        self._client: Optional[httpx.AsyncClient] = None

        # Initialize thinking orchestrator (default to "direct", actual strategy chosen per-request via mode_mapping)
        self.thinking_orchestrator = ThinkingOrchestrator(default_strategy="direct")

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client for legacy methods.

        Note: Prefer using self._provider for new code.
        """
        if self._client is None:
            # Use provider's base_url and auth for legacy client
            headers = {"Content-Type": "application/json"}
            if self.config.provider.api_key:
                headers["Authorization"] = f"Bearer {self.config.provider.api_key}"
            self._client = httpx.AsyncClient(
                timeout=self.config.provider.timeout,
                headers=headers,
            )
        return self._client

    async def chat(
        self,
        conversation_id: str,
        message: str,
        run_id: Optional[str] = None,
        event_callback: Optional[Callable[[dict], None]] = None,
        thinking_strategy: Optional[str] = None,
        thinking_params: Optional[dict] = None,
        reasoning_effort: Optional[str] = None,  # "low", "medium", "high" for native reasoning
    ) -> ChatResult:
        """Send a message and get a response.

        Args:
            conversation_id: ID of the conversation.
            message: User's message.
            run_id: Optional run ID. Generated if not provided.
            event_callback: Optional callback for streaming events.
            thinking_strategy: Optional thinking strategy name (e.g., "direct", "vote").
                              If None, uses the orchestrator's default.
            thinking_params: Optional parameters for the thinking strategy.
            reasoning_effort: Optional reasoning effort for native reasoning models.
                             Overrides config value if provided. Values: "low", "medium", "high".

        Returns:
            ChatResult with the response.
        """
        # Get the thinking strategy (validates name, allows future extensibility)
        # Inject config-based params for specific strategies
        params = dict(thinking_params or {})

        # CoT strategy params
        if thinking_strategy == "cot":
            cot_config = self.config.thinking.cot
            if "thinking_budget" not in params:
                params["thinking_budget"] = cot_config.thinking_budget
            if "answer_budget" not in params:
                params["answer_budget"] = cot_config.answer_budget

        strategy = self.thinking_orchestrator.get_strategy(
            thinking_strategy, **params
        )
        run_id = run_id or str(uuid.uuid4())
        start_time = time.time()
        
        # Get database and repos
        db = await get_db()
        conv_repo = ConversationRepo(db)
        trace_repo = TraceRepo(db)
        
        # Verify conversation exists
        conversation = await conv_repo.get(conversation_id)
        if not conversation:
            return ChatResult(
                run_id=run_id,
                conversation_id=conversation_id,
                message=message,
                response="",
                status="failed",
                error=f"Conversation not found: {conversation_id}",
            )
        
        # Load conversation history from runs table
        prior_runs = await trace_repo.list_runs_for_conversation(conversation_id)
        
        # Build messages
        messages = self._build_messages(prior_runs, message)
        
        # Log if debug
        if self.config.tracing.log_level == "debug":
            print(f"[ChatEngine] Messages: {len(messages)}, Endpoint: {self.config.endpoint}")
        
        # Create trace record (status: running)
        await trace_repo.create_conversation_trace(
            run_id=run_id,
            conversation_id=conversation_id,
            profile_name="chat",
            mode="chat",
            model_config=self.config.model.model_dump(),
            user_message=message,
            system_prompt=self.config.system_prompt,
        )
        
        # Emit event
        if event_callback:
            event_callback({
                "type": "CHAT_STARTED",
                "run_id": run_id,
                "conversation_id": conversation_id,
            })
        
        try:
            # Track model call count for step_number in trace events
            model_call_count = 0

            # For stateful mode: query previous response_id and track current run's last response_id
            previous_response_id = None
            last_response_id_from_run = None  # Track the last response_id we receive

            if self.config.provider.state_mode == "stateful_opt_in":
                previous_response_id = await trace_repo.get_latest_response_id(conversation_id)
                if self.config.tracing.log_level == "debug" and previous_response_id:
                    logger.debug(f"[ChatEngine] Stateful mode: using previous_response_id={previous_response_id}")

            # Create model_call wrapper that strategies will use
            async def model_call_wrapper(
                msgs: list[dict],
                temperature: Optional[float] = None,
                max_tokens: Optional[int] = None,
                logprobs: bool = False,
                stop: Optional[list[str]] = None,  # Stop sequences for thinking control
                **kwargs,
            ) -> tuple:
                """Model call function passed to thinking strategies.

                Returns:
                    If logprobs=False: (response_text, usage_dict)
                    If logprobs=True: (response_text, usage_dict, logprobs_list)
                """
                nonlocal model_call_count
                model_call_count += 1
                call_start_time = time.time()

                # Override temperature if specified (for self-consistency sampling)
                temp_override = temperature if temperature is not None else self.config.model.temperature
                max_tokens_override = max_tokens if max_tokens is not None else self.config.model.max_tokens

                # Save original values and restore after
                original_temp = self.config.model.temperature
                original_max_tokens = self.config.model.max_tokens
                self.config.model.temperature = temp_override
                self.config.model.max_tokens = max_tokens_override

                # Record llm_request trace event
                request_event_id = None
                if self.config.tracing.log_model_calls:
                    try:
                        request_event_id = await trace_repo.add_trace_event(
                            run_id=run_id,
                            event_type="llm_request",
                            content={
                                "model": self.config.model.name,
                                "messages_count": len(msgs),
                                "temperature": temp_override,
                                "max_tokens": max_tokens_override,
                                "logprobs": logprobs,
                            },
                            actor="system",
                            event_status="pending",
                            step_number=model_call_count,
                        )
                    except Exception as trace_err:
                        logger.warning(f"Failed to record llm_request trace: {trace_err}")

                try:
                    if logprobs:
                        # Use non-streaming call with logprobs for CAR
                        response_text, usage, logprobs_data = await self._call_model_with_logprobs(msgs)

                        # Record llm_response trace event for logprobs call
                        if self.config.tracing.log_model_calls and request_event_id:
                            call_duration_ms = int((time.time() - call_start_time) * 1000)
                            try:
                                await trace_repo.add_trace_event(
                                    run_id=run_id,
                                    event_type="llm_response",
                                    content={
                                        "response_length": len(response_text),
                                        "usage": usage or {},
                                        "has_logprobs": logprobs_data is not None,
                                    },
                                    actor="model",
                                    event_status="success",
                                    parent_event_id=request_event_id,
                                    step_number=model_call_count,
                                    duration_ms=call_duration_ms,
                                    token_count=(usage or {}).get("total_tokens"),
                                )
                                # Update request event to success
                                await trace_repo.update_trace_event(
                                    request_event_id,
                                    event_status="success",
                                    duration_ms=call_duration_ms,
                                )
                            except Exception as trace_err:
                                logger.warning(f"Failed to record llm_response trace: {trace_err}")

                        return response_text, usage or {}, logprobs_data
                    else:
                        # Create stream parser to route thinking vs answer tokens
                        stream_parser = StreamParser()
                        debug_streaming = self.config.tracing.log_level == "debug"

                        # Log which call is creating the parser
                        if debug_streaming:
                            # Get a snippet of the last user message to identify the call
                            last_user = [m for m in msgs if m.get("role") == "user"][-1]["content"][:50] if any(m.get("role") == "user" for m in msgs) else "no-user-msg"
                            sys.stderr.write(f"[ChatEngine] Creating NEW StreamParser for model_call, last_user_msg={repr(last_user)}...\n")
                            sys.stderr.flush()

                        # Token callback for streaming - routes to THINKING_TOKEN or TOKEN
                        def on_token(token: str):
                            if not event_callback:
                                return

                            # Feed token to parser to detect thinking vs answer sections
                            thinking_token, answer_token = stream_parser.feed(token, debug=debug_streaming)

                            # Emit thinking token if in thinking section
                            if thinking_token:
                                if debug_streaming:
                                    sys.stderr.write(f"[ChatEngine] Emitting THINKING_TOKEN: {repr(thinking_token[:30])}...\n")
                                    sys.stderr.flush()
                                event_callback({
                                    "type": "THINKING_TOKEN",
                                    "run_id": run_id,
                                    "content": thinking_token,
                                })

                            # Emit answer token if in answer section
                            if answer_token:
                                if debug_streaming:
                                    sys.stderr.write(f"[ChatEngine] Emitting TOKEN: {repr(answer_token[:30])}...\n")
                                    sys.stderr.flush()
                                event_callback({
                                    "type": "TOKEN",
                                    "run_id": run_id,
                                    "content": answer_token,
                                })

                        # Separate callback for native reasoning (gpt-oss via LM Studio)
                        # This bypasses StreamParser entirely for native reasoning content
                        def on_reasoning(reasoning: str):
                            if not event_callback:
                                return
                            if debug_streaming:
                                sys.stderr.write(f"[ChatEngine] Emitting THINKING_TOKEN (native): {repr(reasoning[:30])}...\n")
                                sys.stderr.flush()
                            event_callback({
                                "type": "THINKING_TOKEN",
                                "run_id": run_id,
                                "content": reasoning,
                            })

                        response_text, usage, native_reasoning, response_id = await self._call_model_streaming(
                            msgs, on_token, stop=stop, reasoning_effort=reasoning_effort,
                            reasoning_callback=on_reasoning,
                            previous_response_id=previous_response_id,
                        )

                        # Track response_id for stateful mode
                        nonlocal last_response_id_from_run
                        if response_id:
                            last_response_id_from_run = response_id

                        # Flush remaining buffer content from StreamParser
                        # This ensures the last ~10 chars (BUFFER_SIZE) are not lost
                        thinking_remaining, answer_remaining = stream_parser.flush()
                        if thinking_remaining and event_callback:
                            event_callback({
                                "type": "THINKING_TOKEN",
                                "run_id": run_id,
                                "content": thinking_remaining,
                            })
                        if answer_remaining and event_callback:
                            event_callback({
                                "type": "TOKEN",
                                "run_id": run_id,
                                "content": answer_remaining,
                            })

                        # Record llm_response trace event for streaming call
                        if self.config.tracing.log_model_calls and request_event_id:
                            call_duration_ms = int((time.time() - call_start_time) * 1000)
                            try:
                                await trace_repo.add_trace_event(
                                    run_id=run_id,
                                    event_type="llm_response",
                                    content={
                                        "response_length": len(response_text),
                                        "usage": usage or {},
                                        "has_reasoning": bool(native_reasoning),
                                    },
                                    actor="model",
                                    event_status="success",
                                    parent_event_id=request_event_id,
                                    step_number=model_call_count,
                                    duration_ms=call_duration_ms,
                                    token_count=(usage or {}).get("total_tokens"),
                                )
                                # Update request event to success
                                await trace_repo.update_trace_event(
                                    request_event_id,
                                    event_status="success",
                                    duration_ms=call_duration_ms,
                                )
                            except Exception as trace_err:
                                logger.warning(f"Failed to record llm_response trace: {trace_err}")

                        # Return response with reasoning (third value for native reasoning support)
                        return response_text, usage or {}, native_reasoning
                except Exception as e:
                    # Record error trace event
                    if self.config.tracing.log_model_calls and request_event_id:
                        call_duration_ms = int((time.time() - call_start_time) * 1000)
                        try:
                            await trace_repo.add_trace_event(
                                run_id=run_id,
                                event_type="error",
                                content={"error_type": type(e).__name__},
                                actor="system",
                                event_status="error",
                                parent_event_id=request_event_id,
                                step_number=model_call_count,
                                duration_ms=call_duration_ms,
                                error_message=str(e),
                            )
                            # Update request event to error
                            await trace_repo.update_trace_event(
                                request_event_id,
                                event_status="error",
                                duration_ms=call_duration_ms,
                                error_message=str(e),
                            )
                        except Exception as trace_err:
                            logger.warning(f"Failed to record error trace: {trace_err}")

                    # Emit error event so UI knows to stop waiting
                    if event_callback:
                        event_callback({
                            "type": "STREAM_ERROR",
                            "run_id": run_id,
                            "error": str(e),
                        })
                    raise
                finally:
                    self.config.model.temperature = original_temp
                    self.config.model.max_tokens = original_max_tokens

            # Execute the thinking strategy
            thinking_result = await strategy.think(
                messages=messages,
                model_call=model_call_wrapper,
                event_callback=event_callback,
            )

            timing_ms = int((time.time() - start_time) * 1000)

            # Store thinking steps if tracing is enabled
            if self.config.tracing.log_model_calls and self.config.thinking.tracing.save_internal:
                for step in thinking_result.steps:
                    await trace_repo.add_thinking_step(run_id=run_id, step=step)

            # Update run with final answer and thinking summary
            usage_stats = {
                "prompt_tokens": thinking_result.metadata.get("usage", {}).get("prompt_tokens", 0),
                "completion_tokens": thinking_result.thinking_tokens + thinking_result.answer_tokens,
                "total_tokens": thinking_result.total_tokens,
                "thinking_tokens": thinking_result.thinking_tokens,
                "answer_tokens": thinking_result.answer_tokens,
                "timing_ms": timing_ms,
            }

            await trace_repo.update_conversation_trace(
                run_id=run_id,
                final_answer=thinking_result.final_answer,
                status="succeeded",
                usage_stats=usage_stats,
                last_response_id=last_response_id_from_run,  # Store for stateful mode
            )

            # Update thinking summary if enabled
            if self.config.thinking.tracing.save_user_summary and thinking_result.thinking_summary:
                await trace_repo.update_thinking_summary(
                    run_id=run_id,
                    thinking_summary=thinking_result.thinking_summary,
                )

            # Emit completion event
            if event_callback:
                event_callback({
                    "type": "CHAT_COMPLETED",
                    "run_id": run_id,
                    "response": thinking_result.final_answer,
                    "thinking_summary": thinking_result.thinking_summary,
                    "strategy": strategy.name,
                })

            return ChatResult(
                run_id=run_id,
                conversation_id=conversation_id,
                message=message,
                response=thinking_result.final_answer,
                status="succeeded",
                timing_ms=timing_ms,
                token_usage=usage_stats,
                thinking_summary=thinking_result.thinking_summary,
            )
            
        except Exception as e:
            timing_ms = int((time.time() - start_time) * 1000)
            error_msg = str(e)
            
            # Update trace with error
            await trace_repo.update_conversation_trace(
                run_id=run_id,
                status="failed",
                error_message=error_msg,
                usage_stats={"timing_ms": timing_ms},
            )
            
            # Emit error event
            if event_callback:
                event_callback({
                    "type": "CHAT_FAILED",
                    "run_id": run_id,
                    "error": error_msg,
                })
            
            return ChatResult(
                run_id=run_id,
                conversation_id=conversation_id,
                message=message,
                response="",
                status="failed",
                error=error_msg,
                timing_ms=timing_ms,
            )

    def _build_messages(
        self,
        prior_runs: list[dict],
        current_message: str,
    ) -> list[dict]:
        """Build message list for model call from conversation history.

        Messages are built from the runs table (user_message + final_answer pairs),
        NOT from trace_events. This ensures stateless operation where each request
        contains the full conversation context.

        Args:
            prior_runs: Previous conversation runs from runs table.
            current_message: Current user message.

        Returns:
            List of message dicts for the API.
        """
        messages = []

        # System message
        messages.append({
            "role": "system",
            "content": self.config.system_prompt,
        })

        # Add conversation history (respecting max_messages limit)
        max_messages = self.config.context.max_messages

        # Sort by created_at ascending (oldest first)
        sorted_runs = sorted(prior_runs, key=lambda r: r.get("created_at", ""))

        # Apply sliding window if needed
        if len(sorted_runs) > max_messages:
            sorted_runs = sorted_runs[-max_messages:]

        for run in sorted_runs:
            user_msg = run.get("user_message")
            assistant_msg = run.get("final_answer")

            if user_msg:
                messages.append({"role": "user", "content": user_msg})
            if assistant_msg:
                messages.append({"role": "assistant", "content": assistant_msg})

        # Add current message
        messages.append({"role": "user", "content": current_message})

        return messages

    async def _call_model(self, messages: list[dict]) -> tuple[str, Optional[dict]]:
        """Call the model API (non-streaming).

        Uses the LLM provider abstraction.

        Args:
            messages: List of message dicts.

        Returns:
            Tuple of (response_text, usage_stats).
        """
        response = await self._provider.complete(
            messages=messages,
            model=self.config.model.name,
            instructions=self.config.system_prompt,
            max_tokens=self.config.model.max_tokens,
            temperature=self.config.model.temperature,
            reasoning_effort=self.config.model.reasoning_effort,
            stream=False,
            seed=self.config.model.seed,
            top_p=self.config.model.top_p,
            frequency_penalty=self.config.model.frequency_penalty,
            presence_penalty=self.config.model.presence_penalty,
        )

        return response.text, response.usage or None

    async def _call_model_with_logprobs(
        self, messages: list[dict]
    ) -> tuple[str, Optional[dict], Optional[list]]:
        """Call the model API with logprobs enabled.
        
        Args:
            messages: List of message dicts.
            
        Returns:
            Tuple of (response_text, usage_stats, logprobs_list).
        """
        client = await self._get_client()
        
        # Build request payload with logprobs enabled
        payload = {
            "model": self.config.model.name,
            "messages": messages,
            "temperature": self.config.model.temperature,
            "max_tokens": self.config.model.max_tokens,
            "stream": False,
            "logprobs": True,  # Enable logprobs
            "top_logprobs": 1,  # Get top 1 logprob per token
        }
        
        # Add optional parameters
        if self.config.model.seed is not None:
            payload["seed"] = self.config.model.seed
        if self.config.model.top_p is not None:
            payload["top_p"] = self.config.model.top_p
        if self.config.model.frequency_penalty is not None:
            payload["frequency_penalty"] = self.config.model.frequency_penalty
        if self.config.model.presence_penalty is not None:
            payload["presence_penalty"] = self.config.model.presence_penalty
        
        # Make request
        endpoint = self.config.endpoint.rstrip("/")
        response = await client.post(
            f"{endpoint}/v1/chat/completions",
            json=payload,
        )
        response.raise_for_status()
        
        data = response.json()
        
        # Extract response
        response_text = ""
        logprobs_data = None

        if data.get("choices"):
            choice = data["choices"][0]
            response_text = choice.get("message", {}).get("content", "")

            # Extract logprobs if available
            logprobs_raw = choice.get("logprobs")

            # Debug logging to see what Ollama returns
            if self.config.tracing.log_level == "debug":
                print(f"[ChatEngine] Raw logprobs from Ollama: {logprobs_raw}")

            # Normalize logprobs from various formats
            logprobs_data = self._normalize_logprobs(logprobs_raw)

        # Extract usage
        usage = data.get("usage")

        return response_text, usage, logprobs_data

    def _normalize_logprobs(self, logprobs_raw) -> list:
        """Normalize logprobs from various formats (OpenAI/Ollama).

        Args:
            logprobs_raw: Raw logprobs from API response.

        Returns:
            List of dicts with 'logprob' key, or empty list if unavailable.
        """
        if not logprobs_raw:
            return []

        # OpenAI format: {"content": [{"token": "...", "logprob": -0.5}, ...]}
        if isinstance(logprobs_raw, dict):
            content = logprobs_raw.get("content", [])
            if content:
                return content

        # Direct list format (some Ollama versions)
        if isinstance(logprobs_raw, list):
            normalized = []
            for item in logprobs_raw:
                if isinstance(item, dict) and "logprob" in item:
                    normalized.append(item)
                elif isinstance(item, (int, float)):
                    normalized.append({"logprob": item})
            return normalized

        return []

    async def _call_model_streaming(
        self,
        messages: list[dict],
        token_callback: Optional[Callable[[str], None]] = None,
        stop: Optional[list[str]] = None,
        reasoning_effort: Optional[str] = None,  # Per-request override
        reasoning_callback: Optional[Callable[[str], None]] = None,  # Separate callback for native reasoning
        previous_response_id: Optional[str] = None,  # For stateful mode
    ) -> tuple[str, Optional[dict], Optional[str], Optional[str]]:
        """Call the model API with streaming, sending tokens via callback.

        Uses the LLM provider abstraction which supports:
        - Dual endpoints (/v1/responses and /v1/chat/completions)
        - Automatic fallback on 404/405
        - Exponential backoff with jitter
        - Native reasoning (gpt-oss) via reasoning_effort
        - Stateful mode via previous_response_id

        Args:
            messages: List of message dicts.
            token_callback: Called with each content token chunk.
            stop: Optional stop sequences.
            reasoning_effort: Optional per-request reasoning effort override.
            reasoning_callback: Called with each native reasoning chunk (gpt-oss).
            previous_response_id: Optional response ID from previous call for stateful mode.

        Returns:
            Tuple of (response_text, usage_stats, reasoning_text, response_id).
        """
        # Resolve reasoning effort (per-request override takes precedence)
        effort = reasoning_effort or self.config.model.reasoning_effort

        # Use provider for streaming
        response = await self._provider.complete_streaming(
            messages=messages,
            model=self.config.model.name,
            on_token=token_callback or (lambda _: None),
            on_reasoning=reasoning_callback,
            instructions=self.config.system_prompt,
            max_tokens=self.config.model.max_tokens,
            temperature=self.config.model.temperature,
            reasoning_effort=effort,
            previous_response_id=previous_response_id,
            # Pass optional params
            seed=self.config.model.seed,
            top_p=self.config.model.top_p,
            frequency_penalty=self.config.model.frequency_penalty,
            presence_penalty=self.config.model.presence_penalty,
        )

        # Get response text from provider's normalized response
        response_text = response.text

        # Use provider's usage if available, otherwise count locally
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.get("prompt_tokens", 0),
                "completion_tokens": response.usage.get("completion_tokens", 0),
                "total_tokens": response.usage.get("total_tokens", 0),
            }
        else:
            # Count tokens locally as fallback
            token_counter = get_token_counter()
            prompt_tokens = token_counter.count_message_dicts(messages)
            completion_tokens = token_counter.count_tokens(response_text)
            usage = {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            }

        # Log endpoint used if debug
        if self.config.tracing.log_level == "debug":
            logger.debug(f"[ChatEngine] Streaming via {response.endpoint_used}")

        return response_text, usage, response.reasoning, response.response_id

    async def close(self):
        """Close the HTTP client and provider."""
        if self._client:
            await self._client.aclose()
            self._client = None
        if self._provider:
            await self._provider.close()

