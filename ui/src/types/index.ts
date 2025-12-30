// API Types

export interface ThinkingStep {
  seq: number;
  step_type: string;
  summary: string;
  status: string;
}

export interface Run {
  run_id: string;
  created_at: string;
  status: 'running' | 'succeeded' | 'failed';
  mode: string;
  profile: string;
  prompt: string;
  user_message?: string;
  conversation_id?: string;
  conversation_summary?: string;
  final_answer?: string;
  final_report?: string;
  error_code?: string;
  error_detail?: string;
  // Thinking data
  thinking_summary?: string;
  thinking_steps?: ThinkingStep[];
  strategy?: string;
}

export interface Event {
  run_id: string;
  seq: number;
  ts: string;
  type: string;
  display: {
    title: string;
    summary: string;
    status?: string;
    result_preview?: string;
  };
  payload: Record<string, unknown>;
}

export interface TimelineEntry {
  seq: number;
  ts: string;
  type: string;
  title: string;
  summary: string;
  status?: string;
}

export interface CreateRunRequest {
  prompt: string;
  mode?: string;
  profile?: string;
}

export interface CreateRunResponse {
  run_id: string;
  stream_url: string;
}

export interface Conversation {
  conversation_id: string;
  created_at: string;
  title?: string;
  summary?: string;
  status: string;
  metadata?: Record<string, unknown>;
}

export interface ConversationDetailResponse {
  conversation: Conversation;
  runs: Run[];
}

export interface CreateConversationRequest {
  title?: string;
}

export interface CreateConversationResponse {
  conversation_id: string;
}

export interface CreateConversationRunRequest {
  message: string;
}
