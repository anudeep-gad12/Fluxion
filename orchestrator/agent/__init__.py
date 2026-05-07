"""Coding-agent runtime module."""

from orchestrator.agent.tools import (
    BaseTool,
    ToolError,
    ToolExecutionError,
    ToolRegistry,
    ToolResult,
    ToolSchema,
    ToolTimeoutError,
    WebExtractTool,
    WebSearchTool,
)
from orchestrator.agent.context_pruner import ContextPruner
from orchestrator.agent.state_machine import (
    AgentState,
    AgentStateMachine,
    MaxStepsExceededError,
    RecoveryContext,
    StateTransitionError,
    StepResult,
)
from orchestrator.agent.recovery import (
    RecoveryAction,
    build_recovery_messages,
    create_idempotency_key,
    determine_recovery_actions,
    get_cached_tool_result,
    should_retry_tool,
)
from orchestrator.agent.agent_engine import (
    AgentEngine,
    AgentResult,
    ParsedToolCall,
)
from orchestrator.agent.factory import create_agent_engine
from orchestrator.agent.profile import AgentProfile, CODING_AGENT_PROFILE, get_profile
from orchestrator.agent.context import get_context_strategy

__all__ = [
    # Base types
    "BaseTool",
    "ToolError",
    "ToolExecutionError",
    "ToolResult",
    "ToolSchema",
    "ToolTimeoutError",
    # Registry
    "ToolRegistry",
    # Tools
    "WebSearchTool",
    "WebExtractTool",
    # Context Pruner
    "ContextPruner",
    # State Machine
    "AgentState",
    "AgentStateMachine",
    "MaxStepsExceededError",
    "RecoveryContext",
    "StateTransitionError",
    "StepResult",
    # Recovery
    "RecoveryAction",
    "build_recovery_messages",
    "create_idempotency_key",
    "determine_recovery_actions",
    "get_cached_tool_result",
    "should_retry_tool",
    # Agent Engine
    "AgentEngine",
    "AgentResult",
    "ParsedToolCall",
    # Factory
    "create_agent_engine",
    # Profiles
    "AgentProfile",
    "CODING_AGENT_PROFILE",
    "get_profile",
    # Context
    "get_context_strategy",
]
