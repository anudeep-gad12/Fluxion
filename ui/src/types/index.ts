// API Types

import type {
  TokenUsage,
  CostUsage,
  ContextUsage,
  StoredContextUsage,
  ModelContextProfile,
} from './agent';

export interface ThinkingStep {
  seq: number;
  step_type: string;
  summary: string;
  status: string;
}

export interface Run {
  run_id: string;
  created_at: string;
  status: 'running' | 'succeeded' | 'failed' | 'cancelled' | 'interrupted';
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
  usage?: TokenUsage;
  cost?: CostUsage | null;
  context_usage?: ContextUsage;
  stored_context?: StoredContextUsage;
  context_profile?: ModelContextProfile;
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
  image_attachments?: ImageAttachment[];
}

export interface CreateRunResponse {
  run_id: string;
  stream_url: string;
}

export interface Conversation {
  conversation_id: string;
  created_at: string;
  updated_at?: string | null;
  title?: string;
  summary?: string;
  workspace_path?: string | null;
  status: string;
  metadata?: Record<string, unknown>;
}

export interface ConversationModelSelection {
  provider: string;
  model_id: string;
  display_name: string;
  context_window: number;
  max_output_tokens: number;
  effective_input_budget: number;
  supports_tools: boolean;
  supports_reasoning: boolean;
  supports_vision: boolean;
  source?: string;
  selected_at?: string;
}

export interface ConversationDetailResponse {
  conversation: Conversation;
  runs: Run[];
}

export interface CreateConversationRequest {
  title?: string;
  workspace_path?: string;
  metadata?: Record<string, unknown>;
}

export interface CreateConversationResponse {
  conversation_id: string;
}

export type ThinkingMode = 'default' | 'thinking';

export type ReasoningEffort = 'low' | 'medium' | 'high';

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

export interface CreateConversationRunRequest {
  message: string;
  thinking_mode?: ThinkingMode;
  reasoning_effort?: ReasoningEffort;
  image_attachments?: ImageAttachment[];
}

export interface ImageAttachment {
  id?: string;
  name: string;
  mime_type: string;
  data_url: string;
}
