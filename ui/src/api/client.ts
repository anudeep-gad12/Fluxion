// API Client for the orchestrator

import type {
  Run,
  Event,
  CreateRunRequest,
  CreateRunResponse,
  Conversation,
  ConversationDetailResponse,
  CreateConversationRequest,
  CreateConversationResponse,
  CreateConversationRunRequest,
} from '@/types';
import { withRetry } from '@/lib/retry';

const API_PATH = '/api';
const DEFAULT_TIMEOUT_MS = 30_000;
const OWNER_TOKEN_KEY = 'reasoner_owner_token';

function getApiBase(): string {
  if (typeof window === 'undefined') return API_PATH;
  const { protocol, hostname, port } = window.location;
  if ((hostname === '127.0.0.1' || hostname === 'localhost') && port === '3000') {
    return `${protocol}//${hostname}:9000${API_PATH}`;
  }
  return API_PATH;
}

const API_BASE = getApiBase();

function getOwnerToken(): string | null {
  if (typeof window !== 'undefined') {
    const { hostname, port } = window.location;
    if ((hostname === '127.0.0.1' || hostname === 'localhost') && port === '3000') {
      return null;
    }
  }
  return localStorage.getItem(OWNER_TOKEN_KEY);
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

type FetchJsonOptions = RequestInit & {
  timeoutMs?: number;
};

async function fetchJson<T>(url: string, options?: FetchJsonOptions): Promise<T> {
  const ownerToken = getOwnerToken();
  const { timeoutMs = DEFAULT_TIMEOUT_MS, ...fetchOptions } = options ?? {};
  const optionHeaders = (fetchOptions.headers as Record<string, string> | undefined) ?? {};
  const hasBody = fetchOptions.body !== undefined && fetchOptions.body !== null;
  const headers: Record<string, string> = {
    ...(ownerToken ? { 'X-Owner-Token': ownerToken } : {}),
    ...(hasBody ? { 'Content-Type': 'application/json' } : {}),
    ...optionHeaders,
  };

  const controller = new AbortController();
  const timeoutId = timeoutMs > 0
    ? window.setTimeout(() => controller.abort(), timeoutMs)
    : null;

  let response: Response;
  try {
    response = await fetch(url, {
      ...fetchOptions,
      headers,
      credentials: 'include',
      signal: controller.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ApiError(0, 'Request timed out');
    }
    console.error('Fetch network error:', url, error);
    throw error;
  } finally {
    if (timeoutId !== null) {
      window.clearTimeout(timeoutId);
    }
  }

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new ApiError(response.status, error.detail || 'Request failed');
  }

  return response.json();
}

// Runs
export async function createRun(request: CreateRunRequest): Promise<CreateRunResponse> {
  return fetchJson<CreateRunResponse>(`${API_BASE}/runs`, {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

export async function listRuns(status?: string, limit = 50): Promise<{ runs: Run[]; total: number }> {
  const params = new URLSearchParams();
  if (status) params.set('status', status);
  params.set('limit', String(limit));
  return fetchJson(`${API_BASE}/runs?${params}`);
}

export async function getRun(runId: string): Promise<Run> {
  return withRetry(() => fetchJson(`${API_BASE}/runs/${runId}`));
}

export async function getRunEvents(runId: string, sinceSeq?: number): Promise<{ events: Event[] }> {
  const params = new URLSearchParams();
  if (sinceSeq !== undefined) params.set('since_seq', String(sinceSeq));
  const query = params.toString() ? `?${params}` : '';
  return withRetry(() => fetchJson(`${API_BASE}/runs/${runId}/events${query}`));
}

export async function abortRun(runId: string): Promise<{ status: string; run_id: string }> {
  return fetchJson(`${API_BASE}/runs/${runId}/abort`, {
    method: 'POST',
  });
}

// Trace Events (timeline)
export interface TraceEvent {
  id: string;
  run_id: string;
  seq: number;
  created_at: string;
  event_type: string;
  event_status: string;
  actor: string;
  endpoint?: string;
  attempt: number;
  content: Record<string, unknown>;
  parent_event_id?: string;
  step_number?: number;
  duration_ms?: number;
  token_count?: number;
  error_message?: string;
}

export interface RunTimeline {
  run_id: string;
  status: string;
  created_at: string;
  events: TraceEvent[];
  total_events: number;
}

export async function getRunTimeline(runId: string): Promise<RunTimeline> {
  return withRetry(() => fetchJson(`${API_BASE}/runs/${runId}/timeline`));
}

export async function getRunReport(runId: string): Promise<{ run_id: string; report: string; timeline: unknown[] }> {
  return withRetry(() => fetchJson(`${API_BASE}/runs/${runId}/report`));
}

// Conversations
export async function createConversation(
  request: CreateConversationRequest = {},
): Promise<CreateConversationResponse> {
  return fetchJson<CreateConversationResponse>(`${API_BASE}/conversations`, {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

export async function listConversations(
  status?: string,
  limit = 50,
): Promise<{ conversations: Conversation[]; total: number }> {
  const params = new URLSearchParams();
  if (status) params.set('status', status);
  params.set('limit', String(limit));
  return withRetry(() => fetchJson(`${API_BASE}/conversations?${params}`));
}

export async function getConversation(conversationId: string): Promise<ConversationDetailResponse> {
  // Do not retry 404s here. Deleted/stale conversation URLs need to clear
  // immediately so workspace drafts and @ file mentions keep using the current
  // workspace instead of staying locked to a missing conversation.
  return fetchJson(`${API_BASE}/conversations/${conversationId}`);
}

export interface ConversationTraceEvent extends TraceEvent {
  user_message?: string;
}

export interface ConversationTracesResponse {
  conversation_id: string;
  events: ConversationTraceEvent[];
  total_events: number;
}

export interface ConversationRewindCheckpoint {
  run_id: string;
  user_message: string;
  created_at: string;
}

export interface ConversationRewindCheckpointsResponse {
  conversation_id: string;
  checkpoints: ConversationRewindCheckpoint[];
}

export interface ConversationRewindResponse {
  conversation: Conversation;
  runs: Run[];
  restored_prompt: string;
  rewound_run_ids: string[];
}

export async function getConversationTraces(conversationId: string): Promise<ConversationTracesResponse> {
  return withRetry(() => fetchJson(`${API_BASE}/conversations/${conversationId}/traces`));
}

export async function listConversationRewindCheckpoints(
  conversationId: string,
): Promise<ConversationRewindCheckpointsResponse> {
  return withRetry(() => fetchJson(`${API_BASE}/conversations/${conversationId}/rewind/checkpoints`));
}

export async function rewindConversation(
  conversationId: string,
  request: { run_id: string },
): Promise<ConversationRewindResponse> {
  return fetchJson(`${API_BASE}/conversations/${conversationId}/rewind`, {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

export async function deleteConversation(conversationId: string): Promise<{ status: string }> {
  return fetchJson(`${API_BASE}/conversations/${conversationId}`, {
    method: 'DELETE',
  });
}

export async function createConversationRun(
  conversationId: string,
  request: CreateConversationRunRequest,
): Promise<CreateRunResponse> {
  return fetchJson<CreateRunResponse>(`${API_BASE}/conversations/${conversationId}/runs`, {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

// Health
export async function healthCheck(): Promise<{ status: string }> {
  return fetchJson(`${API_BASE}/health`);
}

// SSE Stream
export function subscribeToRun(
  runId: string,
  onEvent: (event: Event) => void,
  onComplete: (result: { run_id: string; status: string; final_answer?: string }) => void,
  onError: (error: string) => void,
  onAbort?: () => void,
): () => void {
  const ownerToken = getOwnerToken();
  const params = ownerToken ? `?owner=${encodeURIComponent(ownerToken)}` : '';
  const eventSource = new EventSource(`${API_BASE}/runs/${runId}/stream${params}`, {
    withCredentials: true,
  });

  eventSource.addEventListener('event', (e) => {
    try {
      const event = JSON.parse(e.data);
      onEvent(event);
    } catch (err) {
      console.error('Failed to parse event:', err);
    }
  });

  eventSource.addEventListener('complete', (e) => {
    try {
      const result = JSON.parse(e.data);
      onComplete(result);
    } catch (err) {
      console.error('Failed to parse complete:', err);
    }
    eventSource.close();
  });

  eventSource.addEventListener('aborted', () => {
    // Stream was aborted by user
    if (onAbort) {
      onAbort();
    }
    eventSource.close();
  });

  eventSource.addEventListener('error', (e) => {
    if (e instanceof MessageEvent) {
      try {
        const error = JSON.parse(e.data);
        onError(error.error || 'Stream error');
      } catch {
        onError('Stream error');
      }
    } else {
      onError('Connection error');
    }
    eventSource.close();
  });

  eventSource.onerror = () => {
    // Connection closed or error
    eventSource.close();
  };

  return () => eventSource.close();
}

// =============================================================================
// Agent Runs API
// =============================================================================

import type {
  CreateAgentRunRequest,
  CreateAgentRunResponse,
  AgentRunStatus,
  AgentRunTrace,
  AgentSSEEvent,
  AgentCitation,
  ContextUsage,
  StoredContextUsage,
  TokenUsage,
  CostUsage,
  ModelContextProfile,
} from '@/types/agent';

/**
 * Create a new agent run.
 */
export async function createAgentRun(
  request: CreateAgentRunRequest,
): Promise<CreateAgentRunResponse> {
  return fetchJson<CreateAgentRunResponse>(`${API_BASE}/agent/runs`, {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

/**
 * Get agent run status.
 */
export async function getAgentRunStatus(runId: string): Promise<AgentRunStatus> {
  return withRetry(() => fetchJson(`${API_BASE}/agent/runs/${runId}`));
}

/**
 * Get full agent run trace with steps, tool calls, and citations.
 */
export async function getAgentRunTrace(runId: string): Promise<AgentRunTrace> {
  return withRetry(() => fetchJson(`${API_BASE}/agent/runs/${runId}/trace`));
}

/**
 * Cancel an active agent run.
 */
export async function cancelAgentRun(
  runId: string,
): Promise<{ run_id: string; status: string }> {
  return fetchJson(`${API_BASE}/agent/runs/${runId}/cancel`, {
    method: 'POST',
  });
}

export async function pauseAgentRun(
  runId: string,
): Promise<{ run_id: string; status: string }> {
  return fetchJson(`${API_BASE}/agent/runs/${runId}/pause`, {
    method: 'POST',
  });
}

export async function resumeAgentRun(
  runId: string,
): Promise<{ run_id: string; status: string }> {
  return fetchJson(`${API_BASE}/agent/runs/${runId}/resume`, {
    method: 'POST',
  });
}

export async function steerAgentRun(
  runId: string,
  message: string,
): Promise<{ run_id: string; status: string; queue_size: number }> {
  return fetchJson(`${API_BASE}/agent/runs/${runId}/steer`, {
    method: 'POST',
    body: JSON.stringify({ message }),
  });
}

export async function approveAgentToolCall(
  runId: string,
  toolCallId: string,
): Promise<{ status: string; run_id: string; tool_call_id: string }> {
  return fetchJson(`${API_BASE}/agent/runs/${runId}/approve/${encodeURIComponent(toolCallId)}`, {
    method: 'POST',
  });
}

export async function denyAgentToolCall(
  runId: string,
  toolCallId: string,
): Promise<{ status: string; run_id: string; tool_call_id: string }> {
  return fetchJson(`${API_BASE}/agent/runs/${runId}/deny/${encodeURIComponent(toolCallId)}`, {
    method: 'POST',
  });
}

export async function approveAgentPlan(
  runId: string,
  planId: string,
): Promise<{
  status: string;
  run_id: string;
  plan_id: string;
  implementation_run_id?: string;
  implementation_stream_token?: string;
  implementation_stream_url?: string;
}> {
  return fetchJson(`${API_BASE}/agent/runs/${runId}/plan/approve`, {
    method: 'POST',
    body: JSON.stringify({ plan_id: planId }),
  });
}

export async function rejectAgentPlan(
  runId: string,
  planId: string,
  feedback?: string,
): Promise<{ status: string; run_id: string; plan_id: string }> {
  return fetchJson(`${API_BASE}/agent/runs/${runId}/plan/reject`, {
    method: 'POST',
    body: JSON.stringify({ plan_id: planId, feedback }),
  });
}

export async function answerAgentUserInput(
  runId: string,
  requestId: string,
  answers: Record<string, unknown>,
): Promise<{ status: string; run_id: string; request_id: string }> {
  return fetchJson(`${API_BASE}/agent/runs/${runId}/input/${encodeURIComponent(requestId)}`, {
    method: 'POST',
    body: JSON.stringify({ answers }),
  });
}

/**
 * Subscribe to agent run SSE stream with resumption support.
 *
 * @param runId - The run ID to subscribe to
 * @param sinceSeq - Sequence number to resume from (for reconnection)
 * @param onEvent - Callback for each event
 * @param onComplete - Callback when run completes
 * @param onError - Callback on error
 * @param onCancelled - Callback when run is cancelled
 * @returns Cleanup function to close connection
 */
export function subscribeToAgentRun(
  runId: string,
  sinceSeq: number,
  onEvent: (event: AgentSSEEvent) => void,
  onComplete: (result: {
    run_id: string;
    success: boolean;
    final_answer?: string;
    error_message?: string;
    citations?: AgentCitation[];
    total_steps: number;
    timing_ms: number;
    total_tokens?: number;
    status?: string;
    usage?: TokenUsage;
    cost?: CostUsage | null;
    context_usage?: ContextUsage;
    stored_context?: StoredContextUsage;
    context_profile?: ModelContextProfile;
    compaction_count?: number;
    last_compacted_at_step?: number;
  }) => void,
  onError: (error: string) => void,
  onCancelled?: () => void,
  streamToken?: string,
  onDisconnect?: () => void,
): () => void {
  const params = new URLSearchParams();
  if (sinceSeq > 0) params.set('since_seq', String(sinceSeq));
  if (streamToken) params.set('token', streamToken);
  const ownerToken = getOwnerToken();
  if (ownerToken) params.set('owner', ownerToken);
  const qs = params.toString();
  const url = `${API_BASE}/agent/runs/${runId}/stream${qs ? `?${qs}` : ''}`;
  const eventSource = new EventSource(url, {
    withCredentials: true,
  });

  // Map of SSE event names to handlers
  const eventTypes = [
    'agent_state',
    'step_start',
    'thinking',
    'tool_start',
    'tool_approval_required',
    'plan_approval_required',
    'plan_approved',
    'user_input_required',
    'tool_result',
    'answer',
    'paused',
    'resumed',
    'steer',
    'usage_update',
    'conversation_compacted',
  ];

  eventTypes.forEach((eventType) => {
    eventSource.addEventListener(eventType, (e) => {
      try {
        const data = JSON.parse((e as MessageEvent).data);
        onEvent(data as AgentSSEEvent);
      } catch (err) {
        console.error(`Failed to parse ${eventType} event:`, err);
      }
    });
  });

  eventSource.addEventListener('complete', (e) => {
    try {
      const result = JSON.parse((e as MessageEvent).data);
      onComplete(result);
    } catch (err) {
      console.error('Failed to parse complete event:', err);
    }
    eventSource.close();
  });

  eventSource.addEventListener('error', (e) => {
    if (e instanceof MessageEvent) {
      try {
        const error = JSON.parse(e.data);
        onError(error.error || 'Stream error');
      } catch {
        onError('Stream error');
      }
    } else {
      onError('Connection error');
    }
    eventSource.close();
  });

  eventSource.addEventListener('cancelled', () => {
    if (onCancelled) {
      onCancelled();
    }
    eventSource.close();
  });

  eventSource.addEventListener('heartbeat', () => {
    // Keep-alive, no action needed
  });

  eventSource.onerror = () => {
    // Browser EventSource otherwise gets stuck closed after a transient
    // disconnect. The hook reconnects with the latest seen seq so replay
    // resumes without duplicating the full run.
    eventSource.close();
    onDisconnect?.();
  };

  return () => eventSource.close();
}

// =============================================================================
// Local Models API
// =============================================================================

export interface LocalModel {
  path: string;
  name: string;
  size_bytes: number;
  size_display: string;
  model_type: 'gguf' | 'mlx';
}

export interface ModelStatus {
  provider: string;
  model_name: string | null;
  base_url: string | null;
  local_running: boolean;
  context_window: number;
  max_output_tokens: number;
  effective_input_budget: number;
  supports_tools: boolean;
  supports_reasoning: boolean;
  supports_vision: boolean;
  provider_family: string;
  reasoning_capabilities?: ReasoningCapabilities | null;
  source: string;
}

export interface ReasoningControlCapability {
  supported: boolean;
  reason?: string | null;
  options: string[];
}

export interface ReasoningCapabilities {
  provider_family: string;
  max_output_tokens: ReasoningControlCapability;
  reasoning_effort: ReasoningControlCapability;
  reasoning_summary: ReasoningControlCapability;
  reasoning_enabled: ReasoningControlCapability;
  reasoning_max_tokens: ReasoningControlCapability;
  reasoning_exclude: ReasoningControlCapability;
  fireworks_reasoning_mode: ReasoningControlCapability;
  fireworks_thinking_budget_tokens: ReasoningControlCapability;
  fireworks_reasoning_history: ReasoningControlCapability;
}

export interface ReasoningSettings {
  max_output_tokens: number | null;
  reasoning_effort: string | null;
  reasoning_summary: string | null;
  reasoning_enabled: boolean | null;
  reasoning_max_tokens: number | null;
  reasoning_exclude: boolean | null;
  fireworks_reasoning_mode: 'effort' | 'thinking';
  fireworks_thinking_type: 'enabled';
  fireworks_thinking_budget_tokens: number | null;
  fireworks_reasoning_history: 'discarded' | 'preserved' | null;
}

export interface ReasoningSettingsResponse {
  settings: ReasoningSettings;
  capabilities: ReasoningCapabilities;
  provider_family: string;
  model_name: string | null;
  updated_at?: string | null;
  source: string;
}

export async function listLocalModels(): Promise<LocalModel[]> {
  return fetchJson<LocalModel[]>(`${API_BASE}/models/local`, { timeoutMs: 8_000 });
}

export async function startLocalModel(
  modelPath: string,
): Promise<{ status: string; model_name: string }> {
  return fetchJson(`${API_BASE}/models/local/start`, {
    method: 'POST',
    body: JSON.stringify({ model_path: modelPath }),
    timeoutMs: 120_000,
  });
}

export async function stopLocalModel(): Promise<{ status: string; provider: string }> {
  return fetchJson(`${API_BASE}/models/local/stop`, { method: 'POST', timeoutMs: 20_000 });
}

export async function getModelStatus(): Promise<ModelStatus> {
  return fetchJson<ModelStatus>(`${API_BASE}/models/status`, { timeoutMs: 5_000 });
}

export async function getReasoningSettings(): Promise<ReasoningSettingsResponse> {
  return fetchJson<ReasoningSettingsResponse>(`${API_BASE}/models/reasoning-settings`, { timeoutMs: 5_000 });
}

export async function updateReasoningSettings(
  settings: ReasoningSettings,
): Promise<ReasoningSettingsResponse> {
  return fetchJson<ReasoningSettingsResponse>(`${API_BASE}/models/reasoning-settings`, {
    method: 'PUT',
    body: JSON.stringify({ settings }),
  });
}

export interface WorkspaceDirectoryEntry {
  name: string;
  path: string;
  hidden: boolean;
}

export interface WorkspaceFileEntry {
  name: string;
  path: string;
}

export interface WorkspaceBrowseResponse {
  path: string;
  parent: string | null;
  entries: WorkspaceDirectoryEntry[];
}

export interface WorkspaceFileSearchResponse {
  workspace_path: string;
  query: string;
  entries: WorkspaceFileEntry[];
}

export interface TerminalSessionRequest {
  workspace_path?: string;
  cols?: number;
  rows?: number;
}

export interface TerminalSessionResponse {
  session_id: string;
  conversation_id: string;
  workspace_path?: string | null;
  shell: string;
  title?: string;
  status: string;
  cols: number;
  rows: number;
  created_at: string;
  updated_at: string;
  last_activity_at: string;
  reconnect_supported: boolean;
  replay_buffer: string;
}

export interface TerminalSessionListResponse {
  sessions: TerminalSessionResponse[];
  max_sessions_per_conversation: number;
}

export async function browseWorkspaceDirectories(
  path?: string,
): Promise<WorkspaceBrowseResponse> {
  const params = new URLSearchParams();
  if (path) params.set('path', path);
  const query = params.toString() ? `?${params}` : '';
  return fetchJson<WorkspaceBrowseResponse>(`${API_BASE}/workspaces/browse${query}`);
}

export async function searchWorkspaceFiles(
  workspacePath: string,
  query: string,
  limit = 20,
): Promise<WorkspaceFileSearchResponse> {
  const params = new URLSearchParams();
  params.set('workspace_path', workspacePath);
  params.set('q', query);
  params.set('limit', String(limit));
  const queryString = params.toString();
  try {
    return await fetchJson<WorkspaceFileSearchResponse>(`${API_BASE}/workspaces/search-files?${queryString}`);
  } catch (error) {
    // Safari/localhost can occasionally fail absolute localhost:9000 requests
    // while the Vite same-origin proxy still works. @ file mentions should not
    // break on that transport detail.
    if (API_BASE !== API_PATH && !(error instanceof ApiError && error.status > 0)) {
      return fetchJson<WorkspaceFileSearchResponse>(`${API_PATH}/workspaces/search-files?${queryString}`);
    }
    throw error;
  }
}

export async function getTerminalSession(
  conversationId: string,
): Promise<TerminalSessionResponse> {
  return fetchJson<TerminalSessionResponse>(`${API_BASE}/terminal/conversations/${conversationId}/session`);
}

export async function listTerminalSessions(
  conversationId: string,
): Promise<TerminalSessionListResponse> {
  return fetchJson<TerminalSessionListResponse>(
    `${API_BASE}/terminal/conversations/${conversationId}/sessions`,
  );
}

export async function createTerminalSession(
  conversationId: string,
  request: TerminalSessionRequest,
): Promise<TerminalSessionResponse> {
  return fetchJson<TerminalSessionResponse>(
    `${API_BASE}/terminal/conversations/${conversationId}/sessions`,
    {
      method: 'POST',
      body: JSON.stringify(request),
    },
  );
}

/** Legacy: first session or create one. */
export async function createOrGetTerminalSession(
  conversationId: string,
  request: TerminalSessionRequest,
): Promise<TerminalSessionResponse> {
  return fetchJson<TerminalSessionResponse>(`${API_BASE}/terminal/conversations/${conversationId}/session`, {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

export async function restartTerminalSession(
  conversationId: string,
  sessionId: string,
  request: TerminalSessionRequest,
): Promise<TerminalSessionResponse> {
  return fetchJson<TerminalSessionResponse>(
    `${API_BASE}/terminal/conversations/${conversationId}/sessions/${sessionId}/restart`,
    {
      method: 'POST',
      body: JSON.stringify(request),
    },
  );
}

/** Legacy: restart first running session. */
export async function restartFirstTerminalSession(
  conversationId: string,
  request: TerminalSessionRequest,
): Promise<TerminalSessionResponse> {
  return fetchJson<TerminalSessionResponse>(
    `${API_BASE}/terminal/conversations/${conversationId}/session/restart`,
    {
      method: 'POST',
      body: JSON.stringify(request),
    },
  );
}

export async function closeTerminalSession(
  conversationId: string,
  sessionId: string,
): Promise<{ status: string; session_id: string }> {
  return fetchJson(
    `${API_BASE}/terminal/conversations/${conversationId}/sessions/${sessionId}/close`,
    { method: 'POST' },
  );
}

export async function closeAllTerminalSessions(
  conversationId: string,
): Promise<{ status: string; conversation_id: string }> {
  return fetchJson(`${API_BASE}/terminal/conversations/${conversationId}/session/close`, {
    method: 'POST',
  });
}

export function createTerminalWebSocket(
  conversationId: string,
  sessionId: string,
): WebSocket {
  const apiUrl = new URL(API_BASE, window.location.origin);
  const protocol = apiUrl.protocol === 'https:' ? 'wss:' : 'ws:';
  const ownerToken = getOwnerToken();
  const params = new URLSearchParams({ session_id: sessionId });
  if (ownerToken) {
    params.set('owner', ownerToken);
  }
  return new WebSocket(
    `${protocol}//${apiUrl.host}${apiUrl.pathname}/terminal/conversations/${conversationId}/ws?${params.toString()}`
  );
}

export interface UsageInfo {
  limit: number;   // -1 = unlimited (owner or no demo mode)
  used: number;
  remaining: number; // -1 = unlimited
}

export async function getUsage(): Promise<UsageInfo> {
  return fetchJson<UsageInfo>(`${API_BASE}/usage`);
}

export interface RegistryModelPreset {
  model_id: string;
  display_name: string;
  aliases: string[];
  context_window: number;
  max_output_tokens: number;
  supports_tools: boolean;
  supports_reasoning: boolean;
  supports_vision: boolean;
  input_cost_per_million?: number | null;
  cached_input_cost_per_million?: number | null;
  output_cost_per_million?: number | null;
}

export interface RegistryModelsResponse {
  providers: Record<string, {
    models: RegistryModelPreset[];
    available: boolean;
    api_key_env: string;
  }>;
  active_model: string | null;
  active_model_id: string | null;
}

export async function listRegistryModels(): Promise<RegistryModelsResponse> {
  return fetchJson<RegistryModelsResponse>(`${API_BASE}/models`, { timeoutMs: 8_000 });
}

export async function selectModel(model: string): Promise<{
  status: string;
  model_id: string;
  display_name: string;
  provider: string;
  context_window: number;
  max_output_tokens: number;
  effective_input_budget: number;
  supports_tools: boolean;
  supports_reasoning: boolean;
  supports_vision: boolean;
  source: string;
}> {
  return fetchJson(`${API_BASE}/models/select`, {
    method: 'POST',
    body: JSON.stringify({ model }),
    timeoutMs: 10_000,
  });
}

export interface ProviderKeyStatus {
  provider: string;
  api_key_env: string;
  has_key: boolean;
  source: string;
}

export async function listProviderKeys(): Promise<{ providers: ProviderKeyStatus[] }> {
  return fetchJson(`${API_BASE}/models/provider-keys`, { timeoutMs: 8_000 });
}

export async function saveProviderKey(
  provider: string,
  apiKey: string,
): Promise<ProviderKeyStatus> {
  return fetchJson(`${API_BASE}/models/provider-keys/${provider}`, {
    method: 'PUT',
    body: JSON.stringify({ api_key: apiKey }),
    timeoutMs: 10_000,
  });
}

export async function clearProviderKey(provider: string): Promise<ProviderKeyStatus> {
  return fetchJson(`${API_BASE}/models/provider-keys/${provider}`, {
    method: 'DELETE',
    timeoutMs: 10_000,
  });
}
