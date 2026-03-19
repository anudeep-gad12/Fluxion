/**
 * Agent Types - TypeScript definitions for web research agent.
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

/** Request to create agent run */
export interface CreateAgentRunRequest {
  query: string;
  conversation_id?: string;
  max_steps?: number;
}

/** Response from creating agent run */
export interface CreateAgentRunResponse {
  run_id: string;
  status: string;
  stream_url: string;
  stream_token: string;
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
  final_answer?: string;
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
  | 'tool_result' // tool finished
  | 'answer' // streaming answer tokens
  | 'complete' // run finished
  | 'error' // run failed
  | 'cancelled' // run cancelled
  | 'paused' // run paused between steps
  | 'resumed' // run resumed after pause
  | 'steer' // steering message injected
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

/** Tool result event */
export interface ToolResultEvent extends AgentSSEEventBase {
  type: 'tool_result';
  tool_call_id: string;
  tool_name: string;
  success: boolean;
  result_summary: string;
  duration_ms?: number;
}

/** Answer token event */
export interface AnswerEvent extends AgentSSEEventBase {
  type: 'answer';
  content: string;
}

/** Context usage from budget tracker */
export interface ContextUsage {
  total_tokens_used: number;
  history_tokens: number;
  max_tokens: number;
  utilization_pct: number;
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
  context_usage?: ContextUsage;
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

/** Union type for all agent SSE events */
export type AgentSSEEvent =
  | AgentStateEvent
  | StepStartEvent
  | ThinkingEvent
  | ToolStartEvent
  | ToolResultEvent
  | AnswerEvent
  | CompleteEvent
  | ErrorEvent
  | PausedEvent
  | ResumedEvent;

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
  context_tokens?: number;
  context_remaining?: number;
  injectedSteers: Array<{ content: string; step_number: number }>;
}
