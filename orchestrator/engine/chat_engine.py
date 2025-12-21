"""Simple chat engine - no reasoning, just conversation.

This module provides a straightforward chat interface that:
1. Loads conversation history
2. Builds messages with system prompt
3. Calls the model
4. Stores trace
5. Returns result

All settings come from chat_config.yaml.
"""

import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional

import httpx

from orchestrator.config import ChatConfig, get_chat_config
from orchestrator.storage.db import get_db
from orchestrator.storage.repositories.conversation_repo import ConversationRepo
from orchestrator.storage.repositories.trace_repo import TraceRepo


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


class ChatEngine:
    """Simple chat engine - direct model calls with full tracing.
    
    No routing, no reasoning stages, no thinking. Just clean conversation.
    """

    def __init__(self, config: Optional[ChatConfig] = None):
        """Initialize the chat engine.
        
        Args:
            config: Chat configuration. If None, loads from chat_config.yaml.
        """
        self.config = config or get_chat_config()
        self._client: Optional[httpx.AsyncClient] = None

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
    ) -> ChatResult:
        """Send a message and get a response.
        
        Args:
            conversation_id: ID of the conversation.
            message: User's message.
            run_id: Optional run ID. Generated if not provided.
            event_callback: Optional callback for streaming events.
            
        Returns:
            ChatResult with the response.
        """
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
            # Call model
            response_text, usage = await self._call_model(messages)
            
            timing_ms = int((time.time() - start_time) * 1000)
            
            # Update trace with result
            await trace_repo.update_conversation_trace(
                run_id=run_id,
                final_answer=response_text,
                status="succeeded",
                usage_stats={
                    **(usage or {}),
                    "timing_ms": timing_ms,
                },
            )
            
            # Log model call if enabled
            if self.config.tracing.log_model_calls:
                await trace_repo.add_reasoning_step(
                    run_id=run_id,
                    seq=1,
                    step_type="model_call",
                    content=response_text,  # Full response
                    metadata={
                        "messages": messages,  # Full message array sent to model
                        "response": response_text,  # Full response from model
                        "input_tokens": usage.get("prompt_tokens") if usage else None,
                        "output_tokens": usage.get("completion_tokens") if usage else None,
                        "timing_ms": timing_ms,
                        "config_snapshot": self.config.get_snapshot(),
                    },
                )
            
            # Emit completion event
            if event_callback:
                event_callback({
                    "type": "CHAT_COMPLETED",
                    "run_id": run_id,
                    "response": response_text,
                })
            
            return ChatResult(
                run_id=run_id,
                conversation_id=conversation_id,
                message=message,
                response=response_text,
                status="succeeded",
                timing_ms=timing_ms,
                token_usage=usage,
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

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
