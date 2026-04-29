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
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from orchestrator.config import ChatConfig, get_chat_config
from orchestrator.context.budget import ContextBudget
from orchestrator.context.history_builder import HistoryBuilder
from orchestrator.logging_config import get_logger, set_component
from orchestrator.reasoning_controls import (
    ReasoningSettings,
    apply_reasoning_settings,
    infer_provider_family,
)

logger = get_logger(__name__)
from orchestrator.providers import create_provider, LLMProvider
from orchestrator.storage.db import get_db
from orchestrator.storage.repositories.conversation_repo import ConversationRepo
from orchestrator.storage.repositories.trace_repo import TraceRepo
from orchestrator.thinking import ThinkingOrchestrator, StreamParser
from orchestrator.utils.tokens import get_token_counter


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

    Supports reasoning via ThinkingOrchestrator:
    - direct: Uses model's native reasoning (fastest, works with gpt-oss models)
    """

    def __init__(
        self,
        config: Optional[ChatConfig] = None,
        provider: Optional[LLMProvider] = None,
        model_name: Optional[str] = None,
    ):
        """Initialize the chat engine.

        Args:
            config: Chat configuration. If None, loads from chat_config.yaml.
            provider: Optional pre-configured LLM provider override.
                     If None, creates one from config.
            model_name: Optional model name override. If set, used in place
                       of config.model.name for API calls.
        """
        self.config = config or get_chat_config()
        # Use provider's default model if set (e.g. local MLX server)
        self._model_name_override = (
            getattr(provider, "_default_model", None) or model_name
            if provider is not None else model_name
        )

        # Use provided provider or create from config
        if provider is not None:
            self._provider = provider
        else:
            # Initialize LLM provider (uses provider config for endpoint selection, retries, etc.)
            # If provider_chain is enabled, creates ProviderChain with failover support
            self._provider = create_provider(
                self.config.provider,
                chain_config=self.config.provider_chain,
            )

        # Initialize thinking orchestrator (default to "direct", actual strategy chosen per-request via mode_mapping)
        self.thinking_orchestrator = ThinkingOrchestrator(default_strategy="direct")

    async def chat(
        self,
        conversation_id: str,
        message: str,
        run_id: Optional[str] = None,
        event_callback: Optional[Callable[[dict], None]] = None,
        thinking_strategy: Optional[str] = None,
        thinking_params: Optional[dict] = None,
        reasoning_effort: Optional[str] = None,  # "low", "medium", "high" for native reasoning
        reasoning_settings: Optional[ReasoningSettings] = None,
        session_id: Optional[str] = None,  # Session ID for demo mode isolation
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
            session_id: Optional session ID for demo mode user isolation.

        Returns:
            ChatResult with the response.
        """
        set_component("chat_engine")

        # Get the thinking strategy (validates name, allows future extensibility)
        params = dict(thinking_params or {})

        strategy = self.thinking_orchestrator.get_strategy(thinking_strategy, **params)
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

        # Build messages with token-aware history
        messages, context_budget = self._build_messages(prior_runs, message)

        # Log if debug
        if self.config.tracing.log_level == "debug":
            logger.debug(
                "ChatEngine starting",
                extra={"message_count": len(messages), "endpoint": self.config.endpoint},
            )

        # Create trace record (status: running)
        model_config_snapshot = self.config.model.model_dump()
        if reasoning_settings is not None:
            model_config_snapshot["reasoning_settings"] = reasoning_settings.model_dump()
        await trace_repo.create_conversation_trace(
            run_id=run_id,
            conversation_id=conversation_id,
            profile_name="chat",
            mode="chat",
            model_config=model_config_snapshot,
            user_message=message,
            system_prompt=self.config.system_prompt,
            session_id=session_id,
        )

        # Emit event
        if event_callback:
            event_callback(
                {
                    "type": "CHAT_STARTED",
                    "run_id": run_id,
                    "conversation_id": conversation_id,
                }
            )

        try:
            # Track model call count for step_number in trace events
            model_call_count = 0

            # For stateful mode: query previous response_id and track current run's last response_id
            previous_response_id = None
            last_response_id_from_run = None  # Track the last response_id we receive

            if self.config.provider.state_mode == "stateful_opt_in":
                previous_response_id = await trace_repo.get_latest_response_id(conversation_id)
                if previous_response_id:
                    logger.debug(
                        "Stateful mode enabled",
                        extra={"previous_response_id": previous_response_id},
                    )

            # Create model_call wrapper that strategies will use
            async def model_call_wrapper(
                msgs: list[dict],
                temperature: Optional[float] = None,
                max_tokens: Optional[int] = None,
                stop: Optional[list[str]] = None,  # Stop sequences for thinking control
                **kwargs,
            ) -> tuple:
                """Model call function passed to thinking strategies.

                Returns:
                    Tuple of (response_text, usage_dict, native_reasoning).
                """
                nonlocal model_call_count
                model_call_count += 1
                call_start_time = time.time()

                # Override temperature if specified (for self-consistency sampling)
                temp_override = (
                    temperature if temperature is not None else self.config.model.temperature
                )
                max_tokens_override = (
                    max_tokens if max_tokens is not None else self.config.model.max_tokens
                )

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
                            },
                            actor="system",
                            event_status="pending",
                            step_number=model_call_count,
                        )
                    except Exception as trace_err:
                        logger.warning(
                            "Failed to record llm_request trace", extra={"error": str(trace_err)}
                        )

                try:
                    # Create stream parser to route thinking vs answer tokens
                    stream_parser = StreamParser()
                    debug_streaming = self.config.tracing.log_level == "debug"

                    # Log which call is creating the parser
                    if debug_streaming:
                        # Get a snippet of the last user message to identify the call
                        last_user = (
                            [m for m in msgs if m.get("role") == "user"][-1]["content"][:50]
                            if any(m.get("role") == "user" for m in msgs)
                            else "no-user-msg"
                        )
                        sys.stderr.write(
                            f"[ChatEngine] Creating NEW StreamParser for model_call, last_user_msg={repr(last_user)}...\n"
                        )
                        sys.stderr.flush()

                    # Token callback for streaming - routes to THINKING_TOKEN or TOKEN
                    def on_token(token: str):
                        if not event_callback:
                            return

                        # Feed token to parser to detect thinking vs answer sections
                        thinking_token, answer_token = stream_parser.feed(
                            token, debug=debug_streaming
                        )

                        # Emit thinking token if in thinking section
                        if thinking_token:
                            if debug_streaming:
                                sys.stderr.write(
                                    f"[ChatEngine] Emitting THINKING_TOKEN: {repr(thinking_token[:30])}...\n"
                                )
                                sys.stderr.flush()
                            event_callback(
                                {
                                    "type": "THINKING_TOKEN",
                                    "run_id": run_id,
                                    "content": thinking_token,
                                }
                            )

                        # Emit answer token if in answer section
                        if answer_token:
                            if debug_streaming:
                                sys.stderr.write(
                                    f"[ChatEngine] Emitting TOKEN: {repr(answer_token[:30])}...\n"
                                )
                                sys.stderr.flush()
                            event_callback(
                                {
                                    "type": "TOKEN",
                                    "run_id": run_id,
                                    "content": answer_token,
                                }
                            )

                    # Separate callback for native reasoning (gpt-oss via LM Studio)
                    # This bypasses StreamParser entirely for native reasoning content
                    def on_reasoning(reasoning: str):
                        if not event_callback:
                            return
                        if debug_streaming:
                            sys.stderr.write(
                                f"[ChatEngine] Emitting THINKING_TOKEN (native): {repr(reasoning[:30])}...\n"
                            )
                            sys.stderr.flush()
                        event_callback(
                            {
                                "type": "THINKING_TOKEN",
                                "run_id": run_id,
                                "content": reasoning,
                            }
                        )

                    (
                        response_text,
                        usage,
                        native_reasoning,
                        response_id,
                    ) = await self._call_model_streaming(
                        msgs,
                        on_token,
                        stop=stop,
                        reasoning_effort=reasoning_effort,
                        reasoning_settings=reasoning_settings,
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
                        event_callback(
                            {
                                "type": "THINKING_TOKEN",
                                "run_id": run_id,
                                "content": thinking_remaining,
                            }
                        )
                    if answer_remaining and event_callback:
                        event_callback(
                            {
                                "type": "TOKEN",
                                "run_id": run_id,
                                "content": answer_remaining,
                            }
                        )

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
                            logger.warning(
                                "Failed to record llm_response trace",
                                extra={"error": str(trace_err)},
                            )

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
                            logger.warning(
                                "Failed to record error trace", extra={"error": str(trace_err)}
                            )

                    # Emit error event so UI knows to stop waiting
                    if event_callback:
                        event_callback(
                            {
                                "type": "STREAM_ERROR",
                                "run_id": run_id,
                                "error": str(e),
                            }
                        )
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
                "completion_tokens": thinking_result.thinking_tokens
                + thinking_result.answer_tokens,
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

            # Generate and store turn summary for cross-turn context
            try:
                from orchestrator.context.turn_summary import TurnSummarizer

                summarizer = TurnSummarizer(get_token_counter())
                turn_summary = summarizer.summarize_chat_run(message, thinking_result.final_answer)
                await trace_repo.update_run(run_id, turn_summary=turn_summary.to_context_string())
            except Exception as ts_err:
                logger.warning(
                    "Failed to store turn summary",
                    extra={"run_id": run_id, "error": str(ts_err)},
                )

            # Update thinking summary if enabled
            if self.config.thinking.tracing.save_user_summary and thinking_result.thinking_summary:
                await trace_repo.update_thinking_summary(
                    run_id=run_id,
                    thinking_summary=thinking_result.thinking_summary,
                )

            # Emit completion event with context usage
            _chat_ctx = {
                "total_tokens_used": context_budget.total_used,
                "history_tokens": context_budget.history_tokens,
                "max_tokens": context_budget.max_tokens,
                "utilization_pct": round(context_budget.utilization_pct, 1),
            }
            if event_callback:
                event_callback(
                    {
                        "type": "CHAT_COMPLETED",
                        "run_id": run_id,
                        "response": thinking_result.final_answer,
                        "thinking_summary": thinking_result.thinking_summary,
                        "strategy": strategy.name,
                        "context_usage": _chat_ctx,
                    }
                )

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
                event_callback(
                    {
                        "type": "CHAT_FAILED",
                        "run_id": run_id,
                        "error": error_msg,
                    }
                )

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
    ) -> tuple[list[dict], ContextBudget]:
        """Build message list for model call from conversation history.

        Uses HistoryBuilder for token-aware history loading. Prefers compact
        turn_summary over raw final_answer when available.

        Args:
            prior_runs: Previous conversation runs from runs table.
            current_message: Current user message.

        Returns:
            Tuple of (messages list, ContextBudget accounting).
        """
        token_counter = get_token_counter()

        # Resolve context budget from model registry (falls back to config)
        from orchestrator.context.budget import context_params_for_model
        try:
            cfg_max = int(self.config.context.max_tokens)
        except (TypeError, ValueError):
            cfg_max = 100000
        try:
            cfg_reserve = int(self.config.context.reserve_for_response)
        except (TypeError, ValueError):
            cfg_reserve = 4096

        max_context, reserve = context_params_for_model(
            model_name=self._model_name_override,
            config_max_tokens=cfg_max,
            config_reserve=cfg_reserve,
        )

        builder = HistoryBuilder(
            token_counter=token_counter,
            max_context_tokens=max_context,
            reserve_for_response=reserve,
        )

        messages, budget = builder.build_history_messages(
            prior_runs=prior_runs,
            system_prompt=self.config.system_prompt,
            current_query=current_message,
        )

        logger.info(
            "Chat context budget allocated",
            extra={
                "history_tokens": budget.history_tokens,
                "utilization_pct": round(budget.utilization_pct, 1),
                "history_pairs": (len(messages) - 2) // 2,
            },
        )

        return messages, budget

    async def _call_model_streaming(
        self,
        messages: list[dict],
        token_callback: Optional[Callable[[str], None]] = None,
        stop: Optional[list[str]] = None,
        reasoning_effort: Optional[str] = None,  # Per-request override
        reasoning_settings: Optional[ReasoningSettings] = None,
        reasoning_callback: Optional[
            Callable[[str], None]
        ] = None,  # Separate callback for native reasoning
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
        settings = reasoning_settings or ReasoningSettings(
            max_output_tokens=self.config.model.max_tokens,
            reasoning_effort=reasoning_effort or self.config.model.reasoning_effort,
        )
        if reasoning_effort is not None:
            settings = settings.model_copy(update={"reasoning_effort": reasoning_effort})

        provider_family = infer_provider_family(
            provider_obj=self._provider,
            base_url=getattr(self._provider, "_base_url", None),
        )
        provider_kwargs = apply_reasoning_settings(
            settings,
            provider_family=provider_family,
            supports_reasoning=bool(
                getattr(self._provider, "_supports_reasoning", None)
                if getattr(self._provider, "_supports_reasoning", None) is not None
                else True
            ),
        )
        effective_max_tokens = provider_kwargs.pop("max_tokens", self.config.model.max_tokens)
        effort = provider_kwargs.pop("reasoning_effort", None)

        response = await self._provider.complete_streaming(
            messages=messages,
            model=self._model_name_override or self.config.model.name,
            on_token=token_callback or (lambda _: None),
            on_reasoning=reasoning_callback,
            instructions=self.config.system_prompt,
            max_tokens=effective_max_tokens,
            temperature=self.config.model.temperature,
            reasoning_effort=effort,
            previous_response_id=previous_response_id,
            # Pass optional params
            seed=self.config.model.seed,
            top_p=self.config.model.top_p,
            frequency_penalty=self.config.model.frequency_penalty,
            presence_penalty=self.config.model.presence_penalty,
            **provider_kwargs,
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

        # Log endpoint used
        logger.debug("Streaming completed", extra={"endpoint": response.endpoint_used})

        return response_text, usage, response.reasoning, response.response_id

    async def close(self):
        """Close the provider."""
        if self._provider:
            await self._provider.close()
