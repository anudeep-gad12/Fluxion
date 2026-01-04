"""Agent module for web research agent.

This module provides:
- Tool protocol and implementations
- Tool registry for management
- Context pruning for token management
- State machine for agent execution flow
- Recovery helpers for crash recovery
- Agent engine for orchestration
- Factory functions for setup
"""

from orchestrator.agent.tools import (
    BaseTool,
    PythonSandboxTool,
    ToolError,
    ToolExecutionError,
    ToolRegistry,
    ToolResult,
    ToolSchema,
    ToolTimeoutError,
    WebExtractTool,
    WebSearchTool,
    create_tool_registry,
)
from orchestrator.agent.context_pruner import ContextPruner, PruneStats
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
    "create_tool_registry",
    # Tools
    "WebSearchTool",
    "WebExtractTool",
    "PythonSandboxTool",
    # Context Pruner
    "ContextPruner",
    "PruneStats",
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
]
