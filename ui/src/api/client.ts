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

const API_BASE = '/api';
const OWNER_TOKEN_KEY = 'reasoner_owner_token';

function getOwnerToken(): string | null {
  return localStorage.getItem(OWNER_TOKEN_KEY);
}

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const ownerToken = getOwnerToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(ownerToken ? { 'X-Owner-Token': ownerToken } : {}),
    ...(options?.headers as Record<string, string>),
  };

  const response = await fetch(url, {
    ...options,
    headers,
  });

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
  return withRetry(() => fetchJson(`${API_BASE}/conversations/${conversationId}`));
}

export interface ConversationTraceEvent extends TraceEvent {
  user_message?: string;
}

export interface ConversationTracesResponse {
  conversation_id: string;
  events: ConversationTraceEvent[];
  total_events: number;
}

export async function getConversationTraces(conversationId: string): Promise<ConversationTracesResponse> {
  return withRetry(() => fetchJson(`${API_BASE}/conversations/${conversationId}/traces`));
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
  const eventSource = new EventSource(`${API_BASE}/runs/${runId}/stream${params}`);

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
} from '@/types/agent';

/**
 * Create a new agent research run.
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
    citations?: AgentCitation[];
    total_steps: number;
    timing_ms: number;
  }) => void,
  onError: (error: string) => void,
  onCancelled?: () => void,
  streamToken?: string,
): () => void {
  const params = new URLSearchParams();
  if (sinceSeq > 0) params.set('since_seq', String(sinceSeq));
  if (streamToken) params.set('token', streamToken);
  const ownerToken = getOwnerToken();
  if (ownerToken) params.set('owner', ownerToken);
  const qs = params.toString();
  const url = `${API_BASE}/agent/runs/${runId}/stream${qs ? `?${qs}` : ''}`;
  const eventSource = new EventSource(url);

  // Map of SSE event names to handlers
  const eventTypes = [
    'agent_state',
    'step_start',
    'thinking',
    'tool_start',
    'tool_result',
    'answer',
    'paused',
    'resumed',
    'steer',
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
    // Connection closed or error
    eventSource.close();
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
  provider: 'local' | 'cloud';
  model_name: string | null;
  base_url: string | null;
  local_running: boolean;
}

export async function listLocalModels(): Promise<LocalModel[]> {
  return fetchJson<LocalModel[]>(`${API_BASE}/models/local`);
}

export async function startLocalModel(
  modelPath: string,
): Promise<{ status: string; model_name: string }> {
  return fetchJson(`${API_BASE}/models/local/start`, {
    method: 'POST',
    body: JSON.stringify({ model_path: modelPath }),
  });
}

export async function stopLocalModel(): Promise<{ status: string; provider: string }> {
  return fetchJson(`${API_BASE}/models/local/stop`, { method: 'POST' });
}

export async function getModelStatus(): Promise<ModelStatus> {
  return fetchJson<ModelStatus>(`${API_BASE}/models/status`);
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
  return fetchJson<RegistryModelsResponse>(`${API_BASE}/models`);
}

export async function selectModel(model: string): Promise<{
  status: string;
  model_id: string;
  display_name: string;
  provider: string;
  context_window: number;
}> {
  return fetchJson(`${API_BASE}/models/select`, {
    method: 'POST',
    body: JSON.stringify({ model }),
  });
}
