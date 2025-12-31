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

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
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
): () => void {
  const eventSource = new EventSource(`${API_BASE}/runs/${runId}/stream`);

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
