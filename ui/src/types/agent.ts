/**
 * Agent Types - TypeScript definitions for browser coding agent.
 * Mirrors orchestrator/schemas.py agent types.
 */

// =============================================================================
// Enums
// =============================================================================

/** Step states from AgentStepState enum */
export type AgentStepState =
  | 'planning'
  | 'tool_calling'
  | 'synthesizing'
  | 'complete'
  | 'error';

/** Tool call status from AgentToolCallStatus enum */
export type AgentToolCallStatus =
  | 'pending'
  | 'running'
  | 'success'
  | 'error'
  | 'timeout'
  | 'interrupted';

// =============================================================================
// Data Models (mirror backend schemas)
// =============================================================================

/** Agent step response - from AgentStepResponse schema */
export interface AgentStep {
  id: string;
  run_id: string;
  step_number: number;
  state: AgentStepState;
  thinking_text?: string;
  decision?: string;
  created_at: string;
  completed_at?: string;
  error_message?: string;
}

/** Agent tool call response - from AgentToolCallResponse schema */
export interface AgentToolCall {
  id: string;
  run_id: string;
  step_id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  status: AgentToolCallStatus;
  result_summary?: string;
  error_message?: string;
  duration_ms?: number;
  created_at: string;
  started_at?: string;
  completed_at?: string;
  idempotency_key: string;
  execution_attempt: number;
  result_data?: string;
  bash_output?: {
    stdout: string;
    stderr: string;
    exit_code?: number;
    truncated?: boolean;
  };
  approval_required?: boolean;
  approval_decision?: 'approved' | 'denied' | 'auto' | 'timeout';
  permission_level?: string;
  diff_preview?: string | null;
}

/** Agent citation response - from AgentCitationResponse schema */
export interface AgentCitation {
  id: string;
  run_id: string;
  tool_call_id: string;
  source_url: string;
  title?: string;
  snippet: string;
  used_in_answer: boolean;
  created_at: string;
}

// =============================================================================
// API Request/Response Types
// =============================================================================

export interface ModelPricing {
  input_cost_per_million?: number | null;
  cached_input_cost_per_million?: number | null;
  output_cost_per_million?: number | null;
}

export interface ModelContextProfile {
  provider_name: string;
  model_id: string;
  display_name: string;
  context_window: number;
  max_output_tokens: number;
  effective_input_budget: number;
  supports_tools: boolean;
  supports_reasoning: boolean;
  pricing?: ModelPricing;
  source: string;
}

export interface AgentSystemEvent {
  event_type: string;
  message: string;
  step_number?: number;
  seq?: number;
  created_at?: string;
}

/** Request to create agent run */
export interface CreateAgentRunRequest {
  query: string;
  conversation_id?: string;
  max_steps?: number;
  workspace_path?: string;
  filesystem_enabled?: boolean;
  permission_policy?: 'strict' | 'relaxed' | 'yolo';
  capabilities?: {
    web: boolean;
    filesystem: boolean;
    bash: boolean;
    python: boolean;
  };
  image_attachments?: Array<{
    name: string;
    mime_type: string;
    data_url: string;
  }>;
}

/** Response from creating agent run */
export interface CreateAgentRunResponse {
  run_id: string;
  status: string;
  stream_url: string;
  stream_token: string;
  conversation_id?: string;
}

/** Agent run status response */
export interface AgentRunStatus {
  run_id: string;
  status: string;
  agent_state?: string;
  current_step: number;
  max_steps: number;
  final_answer?: string;
  error_message?: string;
  usage?: TokenUsage;
  cost?: CostUsage | null;
  context_usage?: ContextUsage;
  stored_context?: StoredContextUsage;
  context_profile?: ModelContextProfile;
  compaction_count: number;
  last_compacted_at_step?: number;
  created_at: string;
  updated_at?: string;
}

/** Full agent run trace */
export interface AgentRunTrace {
  run_id: string;
  status: string;
  agent_state?: string;
  steps: AgentStep[];
  tool_calls: AgentToolCall[];
  citations: AgentCitation[];
  system_events?: AgentSystemEvent[];
  final_answer?: string;
  usage?: TokenUsage;
  cost?: CostUsage | null;
  context_usage?: ContextUsage;
  stored_context?: StoredContextUsage;
  context_profile?: ModelContextProfile;
  compaction_count: number;
  last_compacted_at_step?: number;
}

// =============================================================================
// SSE Event Types - from _EVENT_TYPE_MAP in agent_runs.py
// =============================================================================

/** SSE event types emitted by agent stream */
export type AgentSSEEventType =
  | 'agent_state' // agent_started, synthesizing
  | 'step_start' // step_started
  | 'thinking' // thinking text tokens
  | 'tool_start' // tool beginning execution
  | 'tool_approval_required' // tool waiting for browser approval
  | 'tool_result' // tool finished
  | 'answer' // streaming answer tokens
  | 'complete' // run finished
  | 'error' // run failed
  | 'cancelled' // run cancelled
  | 'paused' // run paused between steps
  | 'resumed' // run resumed after pause
  | 'steer' // steering message injected
  | 'usage_update' // token/cost usage update
  | 'conversation_compacted'
  | 'heartbeat'; // keep-alive

/** Base SSE event structure */
export interface AgentSSEEventBase {
  seq: number;
  type: AgentSSEEventType;
  timestamp: string;
  run_id?: string;
}

/** Agent state change event */
export interface AgentStateEvent extends AgentSSEEventBase {
  type: 'agent_state';
  query?: string; // Present on agent_started
  state?: string;
}

/** Step started event */
export interface StepStartEvent extends AgentSSEEventBase {
  type: 'step_start';
  step_number: number;
  steps_remaining: number;
  context_tokens?: number;
  context_remaining?: number;
  context_usage?: ContextUsage;
  stored_context?: StoredContextUsage;
  context_profile?: ModelContextProfile;
  compaction_count?: number;
  last_compacted_at_step?: number;
}

/** Thinking content event */
export interface ThinkingEvent extends AgentSSEEventBase {
  type: 'thinking';
  content: string;
}

/** Tool start event */
export interface ToolStartEvent extends AgentSSEEventBase {
  type: 'tool_start';
  tool_call_id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
}

/** Tool approval required event */
export interface ToolApprovalRequiredEvent extends AgentSSEEventBase {
  type: 'tool_approval_required';
  tool_call_id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  permission_level: string;
  diff_preview?: string | null;
}

/** Tool result event */
export interface ToolResultEvent extends AgentSSEEventBase {
  type: 'tool_result';
  tool_call_id: string;
  tool_name: string;
  success: boolean;
  result_summary: string;
  result_data?: string;
  bash_output?: {
    stdout: string;
    stderr: string;
    exit_code?: number;
    truncated?: boolean;
  };
  duration_ms?: number;
}

/** Answer token event */
export interface AnswerEvent extends AgentSSEEventBase {
  type: 'answer';
  content: string;
}

/** Context usage from budget tracker */
export interface ContextUsage {
  context_window: number;
  reserved_output_tokens: number;
  effective_input_budget: number;
  prompt_tokens_current_call: number;
  conversation_tokens_active_history: number;
  utilization_pct_effective: number;
  utilization_pct: number;
  compaction_threshold_pct: number;
  next_compaction_at_tokens: number;
  remaining_tokens: number;
  compactions_so_far: number;
  compaction_count?: number;
  last_compacted_at_step?: number;
}

/** Replayable stored conversation context usage. */
export interface StoredContextUsage {
  context_window: number;
  stored_tokens: number;
  utilization_pct: number;
  replayable_entry_count: number;
}

/** Normalized token usage. */
export interface TokenUsage {
  input_tokens: number;
  output_tokens: number;
  reasoning_tokens: number;
  cached_tokens: number;
  total_tokens: number;
}

/** Estimated run cost. */
export interface CostUsage {
  estimated: boolean;
  currency: string;
  input_cost: number;
  cached_input_cost?: number;
  output_cost: number;
  total_cost: number;
  input_cost_per_million: number;
  cached_input_cost_per_million?: number;
  output_cost_per_million: number;
}

/** Token/cost usage update event */
export interface UsageUpdateEvent extends AgentSSEEventBase {
  type: 'usage_update';
  usage: TokenUsage;
  latest_usage?: TokenUsage;
  cost?: CostUsage | null;
  context_usage?: ContextUsage;
  stored_context?: StoredContextUsage;
  context_profile?: ModelContextProfile;
  compaction_count?: number;
  last_compacted_at_step?: number;
}

/** Complete event */
export interface CompleteEvent extends AgentSSEEventBase {
  type: 'complete';
  success: boolean;
  final_answer?: string;
  citations?: AgentCitation[];
  total_steps: number;
  timing_ms: number;
  total_tokens?: number;
  usage?: TokenUsage;
  cost?: CostUsage | null;
  context_usage?: ContextUsage;
  stored_context?: StoredContextUsage;
  context_profile?: ModelContextProfile;
  compaction_count?: number;
  last_compacted_at_step?: number;
}

/** Error event */
export interface ErrorEvent extends AgentSSEEventBase {
  type: 'error';
  error: string;
}

/** Paused event */
export interface PausedEvent extends AgentSSEEventBase {
  type: 'paused';
  step_number: number;
}

/** Resumed event */
export interface ResumedEvent extends AgentSSEEventBase {
  type: 'resumed';
  step_number: number;
}

/** Conversation compaction event */
export interface ConversationCompactedEvent extends AgentSSEEventBase {
  type: 'conversation_compacted';
  message: string;
  step_number?: number;
  context_usage?: ContextUsage;
  stored_context?: StoredContextUsage;
  context_profile?: ModelContextProfile;
  compaction_count?: number;
}

/** Union type for all agent SSE events */
export type AgentSSEEvent =
  | AgentStateEvent
  | StepStartEvent
  | ThinkingEvent
  | ToolStartEvent
  | ToolApprovalRequiredEvent
  | ToolResultEvent
  | AnswerEvent
  | CompleteEvent
  | ErrorEvent
  | PausedEvent
  | ResumedEvent
  | UsageUpdateEvent
  | ConversationCompactedEvent;

// =============================================================================
// UI State Types
// =============================================================================

/** Current agent run state in UI */
export interface AgentUIState {
  isActive: boolean;
  currentStep: number;
  maxSteps: number;
  agentState: string;
  thinkingBuffer: string;
  answerBuffer: string;
  steps: AgentStep[];
  toolCalls: AgentToolCall[];
  citations: AgentCitation[];
  lastSeq: number;
  timing_ms?: number;
  total_tokens?: number;
  context_usage?: ContextUsage;
  stored_context?: StoredContextUsage;
  usage?: TokenUsage;
  cost?: CostUsage | null;
  context_tokens?: number;
  context_remaining?: number;
  context_profile?: ModelContextProfile;
  compaction_count?: number;
  last_compacted_at_step?: number;
  systemEvents?: AgentSystemEvent[];
  injectedSteers: Array<{ content: string; step_number: number }>;
}
