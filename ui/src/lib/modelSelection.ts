// Shared helpers for per-conversation model selection and the sticky
// cross-session default. Every run must send explicit X-Provider/X-Model
// headers so concurrent conversations never fall back to the backend's
// process-global active model.

import type { Conversation, ConversationModelSelection } from '@/types';
import type { ModelStatus, RegistryModelsResponse } from '@/api/client';

export const CONVERSATION_MODEL_METADATA_KEY = 'model_selection';

const LAST_MODEL_STORAGE_KEY = 'reasoner_last_model_selection';

function isValidSelection(value: unknown): value is ConversationModelSelection {
  if (!value || typeof value !== 'object') return false;
  const selection = value as Partial<ConversationModelSelection>;
  return !!(selection.provider && selection.model_id && selection.display_name);
}

export function getConversationModelSelection(
  conversation?: Conversation | null,
): ConversationModelSelection | null {
  const value = conversation?.metadata?.[CONVERSATION_MODEL_METADATA_KEY];
  return isValidSelection(value) ? (value as ConversationModelSelection) : null;
}

export function loadStickyModelSelection(): ConversationModelSelection | null {
  try {
    const raw = localStorage.getItem(LAST_MODEL_STORAGE_KEY);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    return isValidSelection(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

export function saveStickyModelSelection(selection: ConversationModelSelection): void {
  // Local models are not sticky: the local server may not be running next
  // session, and a stale local default would make every new conversation fail.
  if (selection.provider === 'local') return;
  try {
    localStorage.setItem(LAST_MODEL_STORAGE_KEY, JSON.stringify(selection));
  } catch {
    // Quota/private-mode failures are non-fatal; the draft state still works.
  }
}

/**
 * Synthesize a selection from the backend's currently active model, used to
 * seed the sticky default on installs that predate client-side stickiness.
 */
export function selectionFromRegistryActive(
  registry: RegistryModelsResponse,
  status?: ModelStatus | null,
): ConversationModelSelection | null {
  const provider = registry.active_provider;
  const modelId = registry.active_model_id;
  if (!provider || !modelId || provider === 'local') return null;
  const preset = registry.providers[provider]?.models.find((m) => m.model_id === modelId);
  const statusMatches = status?.provider === provider;
  return {
    provider,
    model_id: modelId,
    display_name: (statusMatches ? status?.model_name : null) || preset?.display_name || modelId,
    context_window: Number((statusMatches ? status?.context_window : 0) || preset?.context_window || 0),
    max_output_tokens: Number((statusMatches ? status?.max_output_tokens : 0) || preset?.max_output_tokens || 0),
    effective_input_budget: Number((statusMatches ? status?.effective_input_budget : 0) || 0),
    supports_tools: (statusMatches ? status?.supports_tools : undefined) ?? preset?.supports_tools ?? true,
    supports_reasoning: (statusMatches ? status?.supports_reasoning : undefined) ?? preset?.supports_reasoning ?? false,
    supports_vision: (statusMatches ? status?.supports_vision : undefined) ?? preset?.supports_vision ?? false,
    source: (statusMatches ? status?.source : undefined) || preset?.source || 'registry',
    selected_at: new Date().toISOString(),
  };
}
