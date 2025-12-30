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

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

import httpx

from orchestrator.config import ChatConfig, get_chat_config
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
        self._client: Optional[httpx.AsyncClient] = None

        # Initialize thinking orchestrator with default from config
        default_strategy = self.config.thinking.default_strategy
        self.thinking_orchestrator = ThinkingOrchestrator(default_strategy=default_strategy)

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=120.0)
        return self._client

    async def chat(
        self,
        conversation_id: str,
        message: str,
        run_id: Optional[str] = None,
        event_callback: Optional[Callable[[dict], None]] = None,
        thinking_strategy: Optional[str] = None,
        thinking_params: Optional[dict] = None,
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

        Returns:
            ChatResult with the response.
        """
        # Get the thinking strategy (validates name, allows future extensibility)
        strategy = self.thinking_orchestrator.get_strategy(
            thinking_strategy, **(thinking_params or {})
        )
        run_id = run_id or str(uuid.uuid4())[:8]
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
        
        # Load conversation history
        prior_traces = await trace_repo.list_traces(conversation_id)
        
        # Build messages
        messages = self._build_messages(prior_traces, message)
        
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
            # Create model_call wrapper that strategies will use
            async def model_call_wrapper(
                msgs: list[dict],
                temperature: Optional[float] = None,
                **kwargs,
            ) -> tuple[str, dict]:
                """Model call function passed to thinking strategies."""
                # Override temperature if specified (for self-consistency sampling)
                temp_override = temperature if temperature is not None else self.config.model.temperature

                # Create stream parser to route thinking vs answer tokens
                stream_parser = StreamParser()

                # Token callback for streaming - routes to THINKING_TOKEN or TOKEN
                def on_token(token: str):
                    if not event_callback:
                        return

                    # Feed token to parser to detect thinking vs answer sections
                    thinking_token, answer_token = stream_parser.feed(token)

                    # Emit thinking token if in thinking section
                    if thinking_token:
                        event_callback({
                            "type": "THINKING_TOKEN",
                            "run_id": run_id,
                            "content": thinking_token,
                        })

                    # Emit answer token if in answer section
                    if answer_token:
                        event_callback({
                            "type": "TOKEN",
                            "run_id": run_id,
                            "content": answer_token,
                        })

                # Save original temperature and restore after
                original_temp = self.config.model.temperature
                self.config.model.temperature = temp_override

                try:
                    response_text, usage = await self._call_model_streaming(msgs, on_token)
                    return response_text, usage or {}
                finally:
                    self.config.model.temperature = original_temp

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
        prior_traces: list[dict],
        current_message: str,
    ) -> list[dict]:
        """Build message list for model call.
        
        Args:
            prior_traces: Previous conversation traces.
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
        sorted_traces = sorted(prior_traces, key=lambda t: t.get("created_at", ""))
        
        # Apply sliding window if needed
        if len(sorted_traces) > max_messages:
            sorted_traces = sorted_traces[-max_messages:]
        
        for trace in sorted_traces:
            user_msg = trace.get("user_message")
            assistant_msg = trace.get("final_answer")
            
            if user_msg:
                messages.append({"role": "user", "content": user_msg})
            if assistant_msg:
                messages.append({"role": "assistant", "content": assistant_msg})
        
        # Add current message
        messages.append({"role": "user", "content": current_message})
        
        return messages

    async def _call_model(self, messages: list[dict]) -> tuple[str, Optional[dict]]:
        """Call the model API.
        
        Args:
            messages: List of message dicts.
            
        Returns:
            Tuple of (response_text, usage_stats).
        """
        client = await self._get_client()
        
        # Build request payload
        payload = {
            "messages": messages,
            "temperature": self.config.model.temperature,
            "max_tokens": self.config.model.max_tokens,
            "stream": False,
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
        if data.get("choices"):
            response_text = data["choices"][0].get("message", {}).get("content", "")
        
        # Extract usage
        usage = data.get("usage")
        
        return response_text, usage

    async def _call_model_streaming(
        self,
        messages: list[dict],
        token_callback: Optional[Callable[[str], None]] = None,
    ) -> tuple[str, Optional[dict]]:
        """Call the model API with streaming, sending tokens via callback.
        
        Args:
            messages: List of message dicts.
            token_callback: Called with each token chunk.
            
        Returns:
            Tuple of (response_text, usage_stats).
        """
        import json
        
        client = await self._get_client()
        
        # Build request payload with streaming enabled
        payload = {
            "messages": messages,
            "temperature": self.config.model.temperature,
            "max_tokens": self.config.model.max_tokens,
            "stream": True,
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
        
        # Make streaming request
        endpoint = self.config.endpoint.rstrip("/")
        full_content = []
        
        async with client.stream(
            "POST",
            f"{endpoint}/v1/chat/completions",
            json=payload,
        ) as response:
            response.raise_for_status()
            
            async for line in response.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue
                
                data_str = line[6:]  # Remove "data: " prefix
                if data_str == "[DONE]":
                    break
                
                try:
                    data = json.loads(data_str)
                    delta = data.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    
                    if content:
                        full_content.append(content)
                        if token_callback:
                            token_callback(content)
                            
                except json.JSONDecodeError:
                    continue
        
        response_text = "".join(full_content)

        # Count tokens properly using tiktoken
        token_counter = get_token_counter()
        prompt_tokens = token_counter.count_message_dicts(messages)
        completion_tokens = token_counter.count_tokens(response_text)

        usage = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        }

        return response_text, usage

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

