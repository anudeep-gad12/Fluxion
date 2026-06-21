// Conversation view - simple chat interface

import { useEffect, useLayoutEffect, useMemo, useRef, useState, useCallback, memo } from 'react';
import type { KeyboardEvent, ChangeEvent, ClipboardEvent, MouseEvent as ReactMouseEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { AnswerMarkdown, extractAnswer } from '@/components/AnswerMarkdown';
import { ThinkingPanel } from '@/components/ThinkingPanel';
import { AgentRunMessage } from '@/components/AgentRunMessage';
import { AgentLiveHUD } from '@/components/AgentLiveHUD';
import { MessageActions } from '@/components/MessageActions';
import { ShimmerSkeleton, ThinkingTimer } from '@/components/StreamingIndicator';
import { ScrollToBottom } from '@/components/ScrollToBottom';
import { WorkspacePickerDialog } from '@/components/WorkspacePickerDialog';
import { VirtualizedConversationRunList } from '@/components/VirtualizedConversationRunList';
import { ConversationToolbar } from '@/components/desktop/ConversationToolbar';
import { DesktopChrome } from '@/components/desktop/DesktopChrome';
import { DesktopInputDock } from '@/components/desktop/DesktopInputDock';
import { DesktopComposerControls } from '@/components/desktop/DesktopComposerControls';
import { EmptyState } from '@/components/desktop/EmptyState';
import { Composer } from '@/components/desktop/Composer';
import { AgentComposerOptions, AgentContextFooter } from '@/components/desktop/AgentComposerOptions';
import { isApplePlatform } from '@/lib/platform';
import { startWindowDrag } from '@/lib/windowDrag';
import {
  createConversation,
  patchConversation,
  createConversationRun,
  getConversation,
  abortRun,
  createAgentRun,
  cancelAgentRun,
  getAgentRunStatus,
  listLocalModels,
  startLocalModel,
  stopLocalModel,
  getModelStatus,
  getReasoningSettings,
  listRegistryModels,
  getChatGPTLoginUrl,
  listProviderKeys,
  saveProviderKey,
  clearProviderKey,
  logoutChatGPT,
  cancelChatGPTLogin,
  startGrokLogin,
  cancelGrokLogin,
  submitGrokLoginCode,
  logoutGrok,
  selectModel,
  updateReasoningSettings,
  getUsage,
  steerAgentRun,
  searchWorkspaceFiles,
  listConversationRewindCheckpoints,
  rewindConversation,
  attachDraftTerminalSessions,
  ApiError,
} from '@/api/client';
import type {
  ConversationRewindCheckpoint,
  LocalModel,
  ModelStatus,
  ProviderKeyStatus,
  RegistryModelPreset,
  RegistryModelsResponse,
  UsageInfo,
  WorkspaceFileEntry,
  ReasoningSettingsResponse,
  ReasoningSettings,
} from '@/api/client';
import type { ConversationModelSelection } from '@/types';
import {
  Dialog,
  DialogHeader,
  DialogTitle,
  DialogContent,
} from '@/components/ui/dialog';
import { DRAFT_TERMINAL_CONVERSATION_ID, useConversationRuns, useSelectedConversation, useStore, useHasActiveRun, useConversationTerminal } from '@/hooks/useStore';
import { isLocalDesktopApp, openExternalUrl, openNativeWorkspacePicker } from '@/lib/platform';
import { DesktopTextOptionGroup } from '@/components/desktop/DesktopTextOptionGroup';
import { useSSE } from '@/hooks/useSSE';
import { useAgentSSE } from '@/hooks/useAgentSSE';
import { useAgentRunDetails } from '@/hooks/useAgentRunDetails';
import { formatAgentCost, formatAgentTokens } from '@/lib/agentLiveState';
import { inputCostTotal, normalizeTokenUsage, outputCostTotal } from '@/lib/usageMetrics';
import { cn, formatRelativeTime } from '@/lib/utils';
import type { Run, Conversation, ImageAttachment } from '@/types';

/** Maximum characters allowed in the input textarea (~2000 tokens) */
const MAX_INPUT_CHARS = 8000;
const MENTION_RESULT_LIMIT = 20;

type ChatGPTLoginState = {
  loginUrl: string;
  status: 'waiting' | 'timed_out';
};
const MAX_IMAGE_ATTACHMENTS = 8;
const MAX_IMAGE_BYTES = 20 * 1024 * 1024;

/** Mode: 'chat' for regular conversation, 'agent' for agent */
type ChatMode = 'chat' | 'agent';

function formatRunStatusLabel(run: Run): string {
  if (run.status === 'succeeded') return 'done';
  if (run.status === 'failed') return 'failed';
  if (run.status === 'cancelled') return 'stopped';
  if (run.status === 'interrupted') return 'interrupted';
  return 'running';
}

function getRunFooterMetrics(run: Run): string[] {
  const metrics: string[] = [];
  const usage = normalizeTokenUsage(run.usage);

  if (usage?.total_tokens) {
    metrics.push(`${formatAgentTokens(usage.total_tokens)} tok`);
  }
  if (usage) {
    metrics.push(
      `in ${formatAgentTokens(usage.input_tokens)} / out ${formatAgentTokens(usage.output_tokens)}`
    );
  }
  if (run.cost && typeof run.cost.total_cost === 'number') {
    metrics.push(`est ${formatAgentCost(run.cost.total_cost)}`);
  } else if (usage) {
    metrics.push('cost n/a');
  }
  if (typeof run.context_usage?.utilization_pct_effective === 'number') {
    metrics.push(`ctx ${Math.round(run.context_usage.utilization_pct_effective)}%`);
  }
  if (run.mode === 'chat') {
    metrics.push('chat');
  }

  return metrics;
}

function getLineStart(text: string, position: number): number {
  return text.lastIndexOf('\n', Math.max(0, position) - 1) + 1;
}

function getLineEnd(text: string, position: number): number {
  const nextBreak = text.indexOf('\n', position);
  return nextBreak === -1 ? text.length : nextBreak;
}

function classifyWordCharacter(char: string): 'space' | 'word' | 'punctuation' {
  if (/\s/.test(char)) return 'space';
  if (/[A-Za-z0-9_]/.test(char)) return 'word';
  return 'punctuation';
}

function moveWordLeft(text: string, position: number): number {
  let nextPosition = position;
  while (nextPosition > 0 && /\s/.test(text[nextPosition - 1])) {
    nextPosition -= 1;
  }
  if (nextPosition === 0) return 0;
  const kind = classifyWordCharacter(text[nextPosition - 1]);
  while (nextPosition > 0 && classifyWordCharacter(text[nextPosition - 1]) === kind) {
    nextPosition -= 1;
  }
  return nextPosition;
}

function moveWordRight(text: string, position: number): number {
  let nextPosition = position;
  while (nextPosition < text.length && /\s/.test(text[nextPosition])) {
    nextPosition += 1;
  }
  if (nextPosition >= text.length) return text.length;
  const kind = classifyWordCharacter(text[nextPosition]);
  while (nextPosition < text.length && classifyWordCharacter(text[nextPosition]) === kind) {
    nextPosition += 1;
  }
  return nextPosition;
}

function moveVertical(text: string, position: number, direction: -1 | 1, preferredColumn?: number | null): number {
  const currentLineStart = getLineStart(text, position);
  const currentColumn = preferredColumn ?? (position - currentLineStart);
  if (direction < 0) {
    if (currentLineStart === 0) return 0;
    const previousLineEnd = currentLineStart - 1;
    const previousLineStart = getLineStart(text, previousLineEnd);
    return Math.min(previousLineStart + currentColumn, previousLineEnd);
  }

  const currentLineEnd = getLineEnd(text, position);
  if (currentLineEnd >= text.length) return text.length;
  const nextLineStart = currentLineEnd + 1;
  const nextLineEnd = getLineEnd(text, nextLineStart);
  return Math.min(nextLineStart + currentColumn, nextLineEnd);
}

function hasTextSelection(textarea: HTMLTextAreaElement): boolean {
  return textarea.selectionStart !== textarea.selectionEnd;
}

function replaceTextareaRange(
  textarea: HTMLTextAreaElement,
  replacement: string,
  start: number,
  end: number,
  selectMode: SelectionMode = 'end',
): void {
  const scrollTop = textarea.scrollTop;
  const scrollLeft = textarea.scrollLeft;
  textarea.setRangeText(replacement, start, end, selectMode);
  textarea.scrollTop = scrollTop;
  textarea.scrollLeft = scrollLeft;
}

function isTextInputElement(element: EventTarget | null): boolean {
  if (!(element instanceof HTMLElement)) return false;
  const tagName = element.tagName.toLowerCase();
  if (tagName === 'input' || tagName === 'textarea' || tagName === 'select') {
    return true;
  }
  if (element.isContentEditable) {
    return true;
  }
  return !!element.closest('[contenteditable="true"], [role="textbox"]');
}

function formatContextTokens(tokens: number): string {
  if (tokens >= 1_000_000) return `${(tokens / 1_000_000).toFixed(tokens >= 10_000_000 ? 0 : 1)}m`;
  if (tokens >= 1_000) return `${(tokens / 1_000).toFixed(tokens >= 10_000 ? 0 : 1)}k`;
  return tokens.toLocaleString();
}

const CONVERSATION_MODEL_METADATA_KEY = 'model_selection';

function getConversationModelSelection(conversation?: Conversation | null): ConversationModelSelection | null {
  const value = conversation?.metadata?.[CONVERSATION_MODEL_METADATA_KEY];
  if (!value || typeof value !== 'object') return null;
  const selection = value as Partial<ConversationModelSelection>;
  if (!selection.provider || !selection.model_id || !selection.display_name) return null;
  return selection as ConversationModelSelection;
}

function modelStatusFromSelection(
  selection: ConversationModelSelection,
  previous: ModelStatus | null,
): ModelStatus {
  return {
    provider: selection.provider,
    model_name: selection.display_name,
    base_url: previous?.provider === selection.provider ? previous.base_url : null,
    local_running: selection.provider === 'local' ? (previous?.local_running ?? false) : false,
    context_window: Number(selection.context_window || previous?.context_window || 0),
    max_output_tokens: Number(selection.max_output_tokens || previous?.max_output_tokens || 0),
    effective_input_budget: Number(selection.effective_input_budget || previous?.effective_input_budget || 0),
    supports_tools: selection.supports_tools ?? previous?.supports_tools ?? true,
    supports_reasoning: selection.supports_reasoning ?? previous?.supports_reasoning ?? false,
    supports_vision: selection.supports_vision ?? previous?.supports_vision ?? false,
    provider_family: selection.provider,
    reasoning_capabilities: previous?.provider === selection.provider ? previous.reasoning_capabilities : null,
    source: selection.source || 'registry',
  };
}

function selectionFromRegistryModel(
  provider: string,
  model: RegistryModelPreset,
  status: ModelStatus,
): ConversationModelSelection {
  return {
    provider,
    model_id: model.model_id,
    display_name: status.model_name || model.display_name,
    context_window: status.context_window,
    max_output_tokens: status.max_output_tokens,
    effective_input_budget: status.effective_input_budget,
    supports_tools: status.supports_tools,
    supports_reasoning: status.supports_reasoning,
    supports_vision: status.supports_vision,
    source: status.source,
    selected_at: new Date().toISOString(),
  };
}

/** Model picker component shown in the status bar */
function ModelPicker({
  open,
  onOpenChange,
  modelStatus,
  onModelStatusChange,
  activeSelection,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  modelStatus: ModelStatus | null;
  onModelStatusChange: (status: ModelStatus, selection?: ConversationModelSelection | null) => void;
  activeSelection: ConversationModelSelection | null;
}) {
  const [registryData, setRegistryData] = useState<RegistryModelsResponse | null>(null);
  const [localModels, setLocalModels] = useState<LocalModel[]>([]);
  const [providerKeys, setProviderKeys] = useState<ProviderKeyStatus[]>([]);
  const [providerKeyDrafts, setProviderKeyDrafts] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [switching, setSwitching] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedProvider, setSelectedProvider] = useState<string>('openai');
  const [modelSearch, setModelSearch] = useState('');
  const [focusedModel, setFocusedModel] = useState<{ provider: string; model: RegistryModelPreset } | null>(null);
  const [chatGPTLogin, setChatGPTLogin] = useState<ChatGPTLoginState | null>(null);
  const [grokLoginCode, setGrokLoginCode] = useState('');
  const pickerLoadSeqRef = useRef(0);
  const chatGPTLoginTimerRef = useRef<number | null>(null);
  const grokLoginTimerRef = useRef<number | null>(null);

  const clearChatGPTLoginTimer = useCallback(() => {
    if (chatGPTLoginTimerRef.current !== null) {
      window.clearInterval(chatGPTLoginTimerRef.current);
      chatGPTLoginTimerRef.current = null;
    }
  }, []);

  const clearGrokLoginTimer = useCallback(() => {
    if (grokLoginTimerRef.current !== null) {
      window.clearInterval(grokLoginTimerRef.current);
      grokLoginTimerRef.current = null;
    }
  }, []);

  useEffect(() => clearChatGPTLoginTimer, [clearChatGPTLoginTimer]);
  useEffect(() => clearGrokLoginTimer, [clearGrokLoginTimer]);

  const refreshPickerData = useCallback(async () => {
    const seq = ++pickerLoadSeqRef.current;
    const failures: string[] = [];

    const registryPromise = listRegistryModels()
      .then((registry) => {
        if (seq === pickerLoadSeqRef.current) setRegistryData(registry);
      })
      .catch(() => {
        failures.push('models');
        if (seq === pickerLoadSeqRef.current) setRegistryData(null);
      });

    const localPromise = listLocalModels()
      .then((local) => {
        if (seq === pickerLoadSeqRef.current) setLocalModels(local);
      })
      .catch(() => {
        failures.push('local');
        if (seq === pickerLoadSeqRef.current) setLocalModels([]);
      });

    const keysPromise = listProviderKeys()
      .then((keys) => {
        if (seq === pickerLoadSeqRef.current) setProviderKeys(keys.providers);
      })
      .catch(() => {
        failures.push('provider keys');
        if (seq === pickerLoadSeqRef.current) setProviderKeys([]);
      });

    await Promise.allSettled([registryPromise, localPromise, keysPromise]);
    if (seq === pickerLoadSeqRef.current && failures.length > 0) {
      setError(`Failed to load ${failures.join(', ')}`);
    }
    if (seq === pickerLoadSeqRef.current) {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!open) {
      pickerLoadSeqRef.current += 1;
      setLoading(false);
      const hadGrokLoginTimer = grokLoginTimerRef.current !== null;
      clearGrokLoginTimer();
      if (hadGrokLoginTimer) void cancelGrokLogin().catch(() => {});
      return;
    }
    setLoading(true);
    setError(null);
    void refreshPickerData();
  }, [open, refreshPickerData, clearGrokLoginTimer]);

  useEffect(() => {
    if (!open) return;
    setSelectedProvider(activeSelection?.provider || registryData?.active_provider || 'openai');
  }, [open, activeSelection?.provider, registryData?.active_provider]);

  const handleSelectRegistry = async (provider: string, modelId: string) => {
    setSwitching(`${provider}:${modelId}`);
    setError(null);
    try {
      if (modelStatus?.provider === 'local') {
        await stopLocalModel();
      }
      const selected = await selectModel({ provider, model_id: modelId });
      const nextStatus: ModelStatus = {
        provider: selected.provider,
        model_name: selected.display_name,
        base_url: modelStatus?.provider === selected.provider ? modelStatus.base_url : null,
        local_running: false,
        context_window: selected.context_window,
        max_output_tokens: selected.max_output_tokens,
        effective_input_budget: selected.effective_input_budget,
        supports_tools: selected.supports_tools,
        supports_reasoning: selected.supports_reasoning,
        supports_vision: selected.supports_vision,
        provider_family: selected.provider,
        reasoning_capabilities: modelStatus?.provider === selected.provider
          ? modelStatus.reasoning_capabilities
          : null,
        source: selected.source,
      };
      const model = registryData?.providers[provider]?.models.find((entry) => entry.model_id === modelId);
      onModelStatusChange(
        nextStatus,
        model ? selectionFromRegistryModel(provider, model, nextStatus) : {
          provider: selected.provider,
          model_id: selected.model_id,
          display_name: selected.display_name,
          context_window: selected.context_window,
          max_output_tokens: selected.max_output_tokens,
          effective_input_budget: selected.effective_input_budget,
          supports_tools: selected.supports_tools,
          supports_reasoning: selected.supports_reasoning,
          supports_vision: selected.supports_vision,
          source: selected.source,
          selected_at: new Date().toISOString(),
        },
      );
      onOpenChange(false);
    } catch {
      setError('Failed to switch model');
    } finally {
      setSwitching(null);
    }
  };

  const handleChatGPTConnect = async () => {
    const loginUrl = getChatGPTLoginUrl();
    clearChatGPTLoginTimer();
    setChatGPTLogin({ loginUrl, status: 'waiting' });
    setSwitching('chatgpt-login');
    setError(null);

    const openedExternally = await openExternalUrl(loginUrl);
    if (!openedExternally) {
      setError('Could not open the browser automatically. Paste the login URL below into your browser.');
    }

    const startedAt = Date.now();
    chatGPTLoginTimerRef.current = window.setInterval(async () => {
      try {
        const registry = await listRegistryModels();
        setRegistryData(registry);
        if (registry.providers.chatgpt?.auth?.authenticated) {
          clearChatGPTLoginTimer();
          setChatGPTLogin(null);
          setSwitching(null);
        }
      } catch {
        // Keep polling; the local API may still be starting or auth may be mid-flight.
      }
      if (Date.now() - startedAt > 120_000) {
        clearChatGPTLoginTimer();
        setChatGPTLogin((state) => state ? { ...state, status: 'timed_out' } : state);
        setSwitching(null);
        setError('ChatGPT login timed out. Retry to open a fresh login, or cancel.');
        void cancelChatGPTLogin().catch(() => {});
        void refreshPickerData();
      }
    }, 1200);
  };

  const handleChatGPTCancelLogin = async () => {
    clearChatGPTLoginTimer();
    setSwitching('chatgpt-cancel');
    setError(null);
    try {
      await cancelChatGPTLogin();
    } catch {
      // Local UI lifecycle should still stop even if the backend already expired the attempt.
    } finally {
      setChatGPTLogin(null);
      setSwitching(null);
      void refreshPickerData();
    }
  };

  const handleChatGPTRetryLogin = async () => {
    await handleChatGPTCancelLogin();
    await handleChatGPTConnect();
  };

  const handleCopyChatGPTLoginUrl = async () => {
    if (!chatGPTLogin) return;
    await navigator.clipboard?.writeText(chatGPTLogin.loginUrl);
    toast.success('Login URL copied');
  };

  const handleChatGPTLogout = async () => {
    clearChatGPTLoginTimer();
    setChatGPTLogin(null);
    setSwitching('chatgpt-logout');
    setError(null);
    try {
      await logoutChatGPT();
      await refreshPickerData();
    } catch {
      setError('Failed to disconnect ChatGPT');
    } finally {
      setSwitching(null);
    }
  };

  const handleGrokConnect = async () => {
    clearGrokLoginTimer();
    setSwitching('grok-login');
    setError(null);
    try {
      const started = await startGrokLogin();
      if (started.status === 'missing_cli') {
        setError(started.message || 'Grok CLI is not installed or not on PATH.');
        return;
      }
      await refreshPickerData();
      setSwitching(null);
      const startedAt = Date.now();
      grokLoginTimerRef.current = window.setInterval(async () => {
        try {
          const registry = await listRegistryModels();
          setRegistryData(registry);
          const auth = registry.providers.grok?.auth;
          if (auth?.authenticated) {
            clearGrokLoginTimer();
          } else if (auth?.last_error) {
            clearGrokLoginTimer();
            setError(auth.last_error);
          }
        } catch {
          // Keep polling while the local login flow is active.
        }
        if (Date.now() - startedAt > 120_000) {
          clearGrokLoginTimer();
          setError('Grok login timed out. Retry to start a fresh OAuth login, or cancel.');
          void cancelGrokLogin().catch(() => {});
          void refreshPickerData();
        }
      }, 1200);
    } catch {
      setError('Failed to start Grok login');
    } finally {
      setSwitching((current) => (current === 'grok-login' ? null : current));
    }
  };

  const handleGrokCancelLogin = async () => {
    clearGrokLoginTimer();
    setSwitching('grok-cancel');
    setError(null);
    try {
      await cancelGrokLogin();
    } catch {
      // UI lifecycle still stops.
    } finally {
      setSwitching(null);
      void refreshPickerData();
    }
  };

  const handleGrokSubmitCode = async () => {
    const code = grokLoginCode.trim();
    if (!code) {
      setError('Paste the Grok browser fallback code first');
      return;
    }
    setSwitching('grok-code');
    setError(null);
    try {
      const result = await submitGrokLoginCode(code);
      if (result.status === 'authenticated') {
        clearGrokLoginTimer();
        setGrokLoginCode('');
        await refreshPickerData();
      } else if (result.status === 'submitted') {
        setGrokLoginCode('');
        await refreshPickerData();
        const startedAt = Date.now();
        clearGrokLoginTimer();
        grokLoginTimerRef.current = window.setInterval(async () => {
          try {
            const registry = await listRegistryModels();
            setRegistryData(registry);
            const auth = registry.providers.grok?.auth;
            if (auth?.authenticated) {
              clearGrokLoginTimer();
              setSwitching(null);
            } else if (auth?.last_error) {
              clearGrokLoginTimer();
              setSwitching(null);
              setError(auth.last_error);
            }
          } catch {
            // Keep polling while the local login flow finishes.
          }
          if (Date.now() - startedAt > 30_000) {
            clearGrokLoginTimer();
            setError('Grok code was submitted, but login has not completed yet. Retry or cancel.');
            void refreshPickerData();
          }
        }, 1200);
      } else {
        setError(result.message || 'No active Grok login is waiting for a code');
        await refreshPickerData();
      }
    } catch {
      setError('Failed to submit Grok fallback code');
    } finally {
      setSwitching(null);
    }
  };

  const handleGrokLogout = async () => {
    clearGrokLoginTimer();
    setSwitching('grok-logout');
    setError(null);
    try {
      const result = await logoutGrok();
      if (result.status === 'error') {
        setError(result.message || 'Failed to disconnect Grok');
      }
      await refreshPickerData();
    } catch {
      setError('Failed to disconnect Grok');
    } finally {
      setSwitching(null);
    }
  };

  const handleSelectLocal = async (model: LocalModel) => {
    if (model.supported === false) {
      setError(model.status_message || 'This local model is not supported by the installed server.');
      return;
    }
    setSwitching(`local:${model.path}`);
    setError(null);
    try {
      const started = await startLocalModel(model.path);
      onModelStatusChange({
        provider: 'local',
        model_name: started.model_name,
        base_url: started.base_url,
        local_running: true,
        context_window: started.context_window,
        max_output_tokens: started.max_output_tokens,
        effective_input_budget: started.effective_input_budget,
        supports_tools: started.supports_tools,
        supports_reasoning: started.supports_reasoning,
        supports_vision: started.supports_vision,
        provider_family: 'local',
        reasoning_capabilities: null,
        source: started.source,
      }, {
        provider: 'local',
        model_id: started.model_id,
        display_name: started.model_name,
        context_window: started.context_window,
        max_output_tokens: started.max_output_tokens,
        effective_input_budget: started.effective_input_budget,
        supports_tools: started.supports_tools,
        supports_reasoning: started.supports_reasoning,
        supports_vision: started.supports_vision,
        source: started.source,
        selected_at: new Date().toISOString(),
      });
      onOpenChange(false);
    } catch (err) {
      const detail = err instanceof ApiError || err instanceof Error ? err.message : null;
      setError(detail || `Failed to start model. Check logs/${model.model_type === 'mlx' ? 'mlx' : 'llama'}.log`);
    } finally {
      setSwitching(null);
    }
  };

  const handleSaveProviderKey = async (provider: string) => {
    const nextKey = (providerKeyDrafts[provider] || '').trim();
    if (!nextKey) {
      setError('API key cannot be empty');
      return;
    }
    setSwitching(`provider-key:${provider}`);
    setError(null);
    try {
      await saveProviderKey(provider, nextKey);
      setProviderKeyDrafts((drafts) => ({ ...drafts, [provider]: '' }));
      await refreshPickerData();
    } catch {
      setError(`Failed to save ${provider} API key`);
    } finally {
      setSwitching(null);
    }
  };

  const handleClearProviderKey = async (provider: string) => {
    setSwitching(`provider-key:${provider}`);
    setError(null);
    try {
      await clearProviderKey(provider);
      setProviderKeyDrafts((drafts) => ({ ...drafts, [provider]: '' }));
      await refreshPickerData();
    } catch {
      setError(`Failed to clear ${provider} API key`);
    } finally {
      setSwitching(null);
    }
  };

  const registryProviders = registryData
    ? Object.entries(registryData.providers)
        .filter(([providerName, info]) => providerName !== 'local' && info.models.length > 0)
    : [];
  const registryProviderNames = new Set(registryProviders.map(([providerName]) => providerName));
  const standaloneProviderKeys = providerKeys.filter((keyStatus) => (
    keyStatus.api_key_env && !registryProviderNames.has(keyStatus.provider)
  ));

  const providerSections = [
    {
      key: 'local-gguf',
      label: 'local',
      models: localModels.filter((model) => model.model_type === 'gguf'),
    },
    {
      key: 'local-mlx',
      label: 'mlx',
      models: localModels.filter((model) => model.model_type === 'mlx'),
    },
  ];

  const desktop = isLocalDesktopApp();
  const activeProviderSection = providerSections.find((section) => section.key === selectedProvider);
  const selectedStandaloneProviderKey = selectedProvider
    ? standaloneProviderKeys.find((keyStatus) => keyStatus.provider === selectedProvider)
    : undefined;
  const activeProvider = selectedProvider && (registryData?.providers[selectedProvider] || activeProviderSection || selectedStandaloneProviderKey)
    ? selectedProvider
    : activeProviderSection
      ? selectedProvider
      : (activeSelection?.provider || registryData?.active_provider || registryProviders[0]?.[0] || 'openai');
  const activeProviderInfo = registryData?.providers[activeProvider];
  const activeLocalSection = providerSections.find((section) => section.key === activeProvider);
  const providerKeyStatus = providerKeys.find((key) => key.provider === activeProvider);
  const activeStandaloneProviderKey = standaloneProviderKeys.find((keyStatus) => keyStatus.provider === activeProvider);
  const allRegistryModels = registryProviders.flatMap(([provider, info]) => (
    info.models.map((model) => ({ provider, model }))
  ));
  const normalizedSearch = modelSearch.trim().toLowerCase();
  const visibleModels = (activeProviderInfo?.models || []).filter((model) => {
    if (!normalizedSearch) return true;
    return [
      model.model_id,
      model.display_name,
      model.category,
      ...(model.aliases || []),
    ].some((value) => String(value || '').toLowerCase().includes(normalizedSearch));
  });
  const recommendedModels = allRegistryModels
    .filter(({ provider, model }) => (
      model.recommended
      && (!normalizedSearch || [provider, model.model_id, model.display_name, ...(model.aliases || [])]
        .some((value) => String(value || '').toLowerCase().includes(normalizedSearch)))
    ))
    .slice(0, 8);
  const selectedDetail = focusedModel
    || (visibleModels[0] ? { provider: activeProvider, model: visibleModels[0] } : null);

  const formatProviderName = (provider: string, displayName?: string) => displayName || provider.replace(/-/g, ' ');
  const formatModelCost = (model: RegistryModelPreset) => {
    if (model.input_cost_per_million == null || model.output_cost_per_million == null) {
      return null;
    }
    const cached = model.cached_input_cost_per_million != null
      ? ` · cached $${model.cached_input_cost_per_million}/M`
      : '';
    return `in $${model.input_cost_per_million}/M · out $${model.output_cost_per_million}/M${cached}`;
  };
  const formatModelMeta = (model: RegistryModelPreset) => [
    `${formatContextTokens(model.context_window)} ctx`,
    `${formatContextTokens(model.max_output_tokens)} out`,
    model.supports_tools ? 'tools' : null,
    model.supports_reasoning ? 'reasoning' : null,
    model.supports_vision ? 'vision' : null,
    model.category && model.category !== 'general' ? model.category : null,
  ].filter(Boolean);
  const startingLocalModel = switching?.startsWith('local:') ?? false;
  const initialPickerLoading = loading && !registryData && localModels.length === 0 && providerKeys.length === 0;
  const handleDialogOpenChange = (nextOpen: boolean) => {
    if (!nextOpen && startingLocalModel) return;
    onOpenChange(nextOpen);
  };

  return (
    <Dialog
      open={open}
      onOpenChange={handleDialogOpenChange}
      className="max-h-[90vh] max-w-6xl"
    >
      <DialogHeader>
        <DialogTitle>Select model</DialogTitle>
      </DialogHeader>
      <DialogContent className="space-y-4 overflow-hidden">
        {error && (
          <p className={cn(
            desktop ? 'desktop-settings-hint-error' : 'rounded-xl border border-red-500/20 bg-red-500/[0.08] px-3 py-2 text-xs text-red-300'
          )}>{error}</p>
        )}
        {loading && (
          <p className={cn(desktop ? 'desktop-settings-hint px-1 py-2' : 'px-1 py-2 text-xs text-zinc-500')}>Loading models…</p>
        )}
        {startingLocalModel && (
          <p className={cn(desktop ? 'desktop-settings-hint px-1 py-2' : 'px-1 py-2 text-xs text-cyan-200')}>
            Starting local model… keep this window open while the server loads.
          </p>
        )}
        <div className={cn(desktop ? 'desktop-model-picker-shell' : 'grid gap-4 lg:grid-cols-[220px_minmax(0,1fr)]')}>
          <aside className={cn(desktop ? 'desktop-model-provider-rail' : 'premium-panel p-2')}>
            {initialPickerLoading && (
              <div className="space-y-2 p-1">
                {Array.from({ length: 6 }).map((_, index) => (
                  <div key={index} className="h-11 rounded-xl bg-white/[0.04]" />
                ))}
              </div>
            )}
            {registryProviders.map(([providerName, info]) => {
              const isSelected = activeProvider === providerName;
              const authReady = info.auth_type === 'oauth' ? !!info.auth?.authenticated : info.available;
              return (
                  <button
                    key={providerName}
                    type="button"
                    disabled={!!switching}
                    onClick={() => {
                      setSelectedProvider(providerName);
                      setFocusedModel(null);
                  }}
                  data-active={desktop && isSelected ? 'true' : undefined}
                  className={cn(
                    desktop
                      ? 'desktop-model-provider-tab'
                      : 'mb-1 flex w-full items-center justify-between rounded-xl px-3 py-2 text-left text-xs text-zinc-300 hover:bg-white/[0.05]',
                    !desktop && isSelected && 'bg-cyan-300/[0.08] text-cyan-100'
                  )}
                >
                  <span className="min-w-0">
                    <span className="block truncate capitalize">{formatProviderName(providerName, info.display_name)}</span>
                    <span className={cn(desktop ? 'desktop-model-provider-sub' : 'text-[10px] text-zinc-500')}>
                      {info.models.length} models · {authReady ? 'ready' : 'setup'}
                    </span>
                  </span>
                  {!authReady && <span className={cn(desktop ? 'desktop-model-provider-dot' : 'text-amber-300')}>!</span>}
                </button>
              );
            })}
            {standaloneProviderKeys.length > 0 && (
              <div className={cn(desktop ? 'desktop-model-provider-divider' : 'my-2 border-t border-white/10 pt-2')}>
                {standaloneProviderKeys.map((keyStatus) => {
                  const isSelected = activeProvider === keyStatus.provider;
                  return (
                    <button
                      key={keyStatus.provider}
                      type="button"
                      disabled={!!switching}
                      onClick={() => {
                        setSelectedProvider(keyStatus.provider);
                        setFocusedModel(null);
                      }}
                      data-active={desktop && isSelected ? 'true' : undefined}
                      className={cn(
                        desktop
                          ? 'desktop-model-provider-tab'
                          : 'mb-1 flex w-full items-center justify-between rounded-xl px-3 py-2 text-left text-xs text-zinc-300 hover:bg-white/[0.05]',
                        !desktop && isSelected && 'bg-cyan-300/[0.08] text-cyan-100'
                      )}
                    >
                      <span className="min-w-0">
                        <span className="block truncate capitalize">{formatProviderName(keyStatus.provider, keyStatus.provider === 'parallel' ? 'Parallel' : undefined)}</span>
                        <span className={cn(desktop ? 'desktop-model-provider-sub' : 'text-[10px] text-zinc-500')}>
                          tools · {keyStatus.has_key ? 'ready' : 'setup'}
                        </span>
                      </span>
                      {!keyStatus.has_key && <span className={cn(desktop ? 'desktop-model-provider-dot' : 'text-amber-300')}>!</span>}
                    </button>
                  );
                })}
              </div>
            )}
            {providerSections.length > 0 && (
              <div className={cn(desktop ? 'desktop-model-provider-divider' : 'my-2 border-t border-white/10 pt-2')}>
                {providerSections.map((section) => (
                  <button
                    key={section.key}
                    type="button"
                    disabled={!!switching}
                    onClick={() => {
                      setSelectedProvider(section.key);
                      setFocusedModel(null);
                    }}
                    data-active={desktop && activeProvider === section.key ? 'true' : undefined}
                    className={cn(desktop ? 'desktop-model-provider-tab' : 'mb-1 block w-full rounded-xl px-3 py-2 text-left text-xs text-zinc-300 hover:bg-white/[0.05]')}
                  >
                    <span className="block truncate uppercase">{section.label}</span>
                    <span className={cn(desktop ? 'desktop-model-provider-sub' : 'text-[10px] text-zinc-500')}>
                      {section.models.length} {section.key === 'local-mlx' ? 'mlx' : 'local'}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </aside>

          <main className={cn(desktop ? 'desktop-model-picker-main' : 'min-w-0 space-y-3')}>
            {initialPickerLoading ? (
              <section className={cn(desktop ? 'desktop-model-section' : 'premium-panel p-3')}>
                <div className={cn(desktop ? 'desktop-settings-provider-header' : 'px-2 pb-2 text-xs uppercase tracking-[0.16em] text-zinc-500')}>
                  Loading catalog
                </div>
                <div className="space-y-2 p-2">
                  {Array.from({ length: 6 }).map((_, index) => (
                    <div key={index} className="h-14 rounded-xl bg-white/[0.035]" />
                  ))}
                </div>
              </section>
            ) : activeProviderInfo ? (
              <>
                <div className={cn(desktop ? 'desktop-model-picker-toolbar' : 'premium-panel p-3')}>
                  <div className="min-w-0">
                    <div className={cn(desktop ? 'desktop-settings-list-title' : 'text-sm font-semibold text-zinc-100')}>
                      {formatProviderName(activeProvider, activeProviderInfo.display_name)}
                    </div>
                    <div className={cn(desktop ? 'desktop-settings-list-meta' : 'mt-1 text-xs text-zinc-500')}>
                      {activeProviderInfo.catalog_source || 'curated'} catalog · {activeProviderInfo.available ? 'authenticated' : 'needs setup'}
                      {activeProviderInfo.catalog_error ? ` · live catalog unavailable` : ''}
                    </div>
                  </div>
                  <input
                    value={modelSearch}
                    onChange={(e) => setModelSearch(e.target.value)}
                    disabled={!!switching}
                    placeholder="Search models, aliases, capabilities…"
                    className={cn(desktop ? 'desktop-settings-field desktop-model-search' : 'premium-field w-full lg:w-80')}
                  />
                </div>

                <section className={cn(desktop ? 'desktop-model-account-card' : 'premium-panel p-3')}>
                  {activeProviderInfo.auth_type === 'oauth' ? (
                    activeProvider === 'chatgpt' ? (
                      <>
                        <div className="min-w-0 flex-1">
                          <div className={cn(desktop ? 'desktop-settings-key-name' : 'text-xs font-semibold text-zinc-200')}>
                            {activeProviderInfo.auth?.authenticated ? 'ChatGPT / Codex connected' : 'Connect ChatGPT / Codex'}
                          </div>
                          <div className={cn(desktop ? 'desktop-settings-key-env' : 'mt-1 text-xs text-zinc-500')}>
                            {activeProviderInfo.auth?.authenticated
                              ? `${activeProviderInfo.auth.account_id || 'ChatGPT account'} · OAuth token saved in Fluxion.`
                              : chatGPTLogin?.status === 'timed_out'
                                ? 'Login timed out. Retry opens a fresh browser login; cancel clears this attempt.'
                                : chatGPTLogin
                                  ? 'Waiting for browser login. This stops automatically after 2 minutes.'
                                  : 'OAuth login opens in your browser, then returns here automatically.'}
                          </div>
                          {chatGPTLogin && !activeProviderInfo.auth?.authenticated && (
                            <div className="mt-3 min-w-0 space-y-2">
                              <input
                                value={chatGPTLogin.loginUrl}
                                readOnly
                                className={cn(desktop ? 'desktop-settings-field w-full' : 'premium-field w-full')}
                                onFocus={(event) => event.currentTarget.select()}
                              />
                              <div className="flex flex-wrap gap-2">
                                <button
                                  type="button"
                                  onClick={() => chatGPTLogin.status === 'timed_out' ? handleChatGPTRetryLogin() : openExternalUrl(chatGPTLogin.loginUrl)}
                                  disabled={switching === 'chatgpt-cancel'}
                                  className={cn(desktop ? 'desktop-settings-btn-ghost' : 'premium-subtle-button')}
                                >
                                  Open URL
                                </button>
                                <button type="button" onClick={handleCopyChatGPTLoginUrl} className={cn(desktop ? 'desktop-settings-btn-ghost' : 'premium-subtle-button')}>
                                  Copy URL
                                </button>
                                <button type="button" onClick={handleChatGPTRetryLogin} disabled={switching === 'chatgpt-cancel'} className={cn(desktop ? 'desktop-settings-btn-ghost' : 'premium-subtle-button')}>
                                  Retry
                                </button>
                                <button type="button" onClick={handleChatGPTCancelLogin} disabled={switching === 'chatgpt-cancel'} className={cn(desktop ? 'desktop-settings-btn-ghost' : 'premium-subtle-button')}>
                                  Cancel
                                </button>
                              </div>
                            </div>
                          )}
                        </div>
                        {activeProviderInfo.auth?.authenticated ? (
                          <button type="button" onClick={handleChatGPTLogout} disabled={!!switching} className={cn(desktop ? 'desktop-settings-btn-ghost' : 'premium-subtle-button')}>
                            Disconnect
                          </button>
                        ) : !chatGPTLogin ? (
                          <button type="button" onClick={handleChatGPTConnect} disabled={switching === 'chatgpt-login'} className={cn(desktop ? 'desktop-settings-btn-primary' : 'premium-primary-button')}>
                            {switching === 'chatgpt-login' ? 'Waiting…' : 'Connect'}
                          </button>
                        ) : null}
                      </>
                    ) : (
                      <>
                        <div className="min-w-0 flex-1">
                          <div className={cn(desktop ? 'desktop-settings-key-name' : 'text-xs font-semibold text-zinc-200')}>
                            {activeProviderInfo.auth?.authenticated ? 'Grok connected' : 'Connect Grok'}
                          </div>
                          <div className={cn(desktop ? 'desktop-settings-key-env' : 'mt-1 text-xs text-zinc-500')}>
                            {activeProviderInfo.auth?.authenticated
                              ? `${activeProviderInfo.auth.account_id || 'Grok account'} · official Grok CLI OAuth.`
                              : activeProviderInfo.auth?.login_running || switching === 'grok-login'
                                ? 'Complete browser login. If it says it cannot reach the app, paste that fallback code below.'
                                : activeProviderInfo.auth?.enabled === false
                                  ? 'Install the Grok CLI first, then connect with OAuth.'
                                  : 'Uses official `grok login --oauth` credentials from ~/.grok/auth.json.'}
                          </div>
                          {activeProviderInfo.auth?.last_message && (
                            <div className={cn(desktop ? 'desktop-settings-hint mt-2' : 'mt-2 text-xs text-zinc-500')}>
                              {activeProviderInfo.auth.last_message}
                            </div>
                          )}
                          {activeProviderInfo.auth?.last_error && (
                            <div className={cn(desktop ? 'desktop-settings-hint-error mt-2' : 'mt-2 text-xs text-red-300')}>
                              {activeProviderInfo.auth.last_error}
                            </div>
                          )}
                          {(activeProviderInfo.auth?.login_running || switching === 'grok-login') && (
                            <div className="mt-3 flex min-w-0 flex-wrap gap-2">
                              <input
                                value={grokLoginCode}
                                onChange={(e) => setGrokLoginCode(e.target.value)}
                                placeholder="Paste browser fallback code"
                                type="password"
                                className={cn(desktop ? 'desktop-settings-field flex-1' : 'premium-field flex-1')}
                              />
                              <button
                                type="button"
                                onClick={handleGrokSubmitCode}
                                disabled={switching === 'grok-code'}
                                className={cn(desktop ? 'desktop-settings-btn-primary' : 'premium-primary-button')}
                              >
                                Submit code
                              </button>
                            </div>
                          )}
                        </div>
                        {activeProviderInfo.auth?.authenticated ? (
                          <button type="button" onClick={handleGrokLogout} disabled={!!switching} className={cn(desktop ? 'desktop-settings-btn-ghost' : 'premium-subtle-button')}>
                            Disconnect
                          </button>
                        ) : activeProviderInfo.auth?.login_running || switching === 'grok-login' ? (
                          <div className="flex flex-wrap gap-2">
                            <button type="button" onClick={handleGrokConnect} disabled={switching === 'grok-cancel'} className={cn(desktop ? 'desktop-settings-btn-ghost' : 'premium-subtle-button')}>
                              Retry
                            </button>
                            <button type="button" onClick={handleGrokCancelLogin} disabled={switching === 'grok-cancel'} className={cn(desktop ? 'desktop-settings-btn-ghost' : 'premium-subtle-button')}>
                              Cancel
                            </button>
                          </div>
                        ) : (
                          <button type="button" onClick={handleGrokConnect} disabled={!!switching || activeProviderInfo.auth?.enabled === false} className={cn(desktop ? 'desktop-settings-btn-primary' : 'premium-primary-button')}>
                            Connect
                          </button>
                        )}
                      </>
                    )
                  ) : providerKeyStatus ? (
                    <>
                      <div className="min-w-0 flex-1">
                        <div className={cn(desktop ? 'desktop-settings-key-name' : 'text-xs font-semibold text-zinc-200')}>
                          {formatProviderName(activeProvider, activeProviderInfo.display_name)} API key
                        </div>
                        <div className={cn(desktop ? 'desktop-settings-key-env' : 'mt-1 text-xs text-zinc-500')}>
                          {providerKeyStatus.api_key_env || 'No key required'} · {providerKeyStatus.has_key ? `configured via ${providerKeyStatus.source}` : 'not configured'}
                        </div>
                      </div>
                      {providerKeyStatus.api_key_env && (
                        <>
                          <input
                            value={providerKeyDrafts[activeProvider] || ''}
                            onChange={(e) => setProviderKeyDrafts((drafts) => ({ ...drafts, [activeProvider]: e.target.value }))}
                            placeholder={providerKeyStatus.has_key ? 'Enter replacement API key' : 'Enter API key'}
                            type="password"
                            className={cn(desktop ? 'desktop-settings-field flex-1' : 'premium-field flex-1')}
                          />
                          <button type="button" onClick={() => handleSaveProviderKey(activeProvider)} disabled={!!switching} className={cn(desktop ? 'desktop-settings-btn-primary' : 'premium-primary-button')}>
                            {providerKeyStatus.has_key ? 'Update' : 'Save'}
                          </button>
                          {providerKeyStatus.source === 'database' && (
                            <button type="button" onClick={() => handleClearProviderKey(activeProvider)} disabled={!!switching} className={cn(desktop ? 'desktop-settings-btn-ghost' : 'premium-subtle-button')}>
                              Clear
                            </button>
                          )}
                        </>
                      )}
                    </>
                  ) : null}
                </section>

                {recommendedModels.length > 0 && normalizedSearch && (
                  <section className={cn(desktop ? 'desktop-model-section' : 'premium-panel p-2')}>
                    <div className={cn(desktop ? 'desktop-settings-provider-header' : 'px-2 pb-2 text-xs uppercase tracking-[0.16em] text-zinc-500')}>Recommended matches</div>
                    <div className={cn(desktop ? 'desktop-model-grid' : 'grid gap-1')}>
                      {recommendedModels.map(({ provider, model }) => {
                        const isActive = activeSelection?.provider === provider && activeSelection.model_id === model.model_id;
                        return (
                          <button
                            key={`${provider}:${model.model_id}:rec`}
                            type="button"
                            onClick={() => desktop ? setFocusedModel({ provider, model }) : handleSelectRegistry(provider, model.model_id)}
                            onDoubleClick={() => handleSelectRegistry(provider, model.model_id)}
                            data-active={desktop && isActive ? 'true' : undefined}
                            className={cn(desktop ? 'desktop-settings-list-item' : 'rounded-xl px-3 py-2 text-left text-sm text-zinc-200 hover:bg-white/[0.05]')}
                          >
                            <div className={cn(desktop ? 'desktop-settings-list-title truncate' : 'truncate font-medium')}>{model.display_name}</div>
                            <div className={cn(desktop ? 'desktop-settings-list-meta flex flex-wrap gap-x-3' : 'mt-1 flex flex-wrap gap-x-3 text-xs text-zinc-500')}>
                              <span>{formatProviderName(provider, registryData?.providers[provider]?.display_name)}</span>
                              {formatModelMeta(model).slice(0, 4).map((part) => <span key={String(part)}>{part}</span>)}
                            </div>
                          </button>
                        );
                      })}
                    </div>
                  </section>
                )}

                <section className={cn(desktop ? 'desktop-model-section' : 'premium-panel p-2')}>
                  <div className={cn(desktop ? 'desktop-settings-provider-header' : 'px-2 pb-2 text-xs uppercase tracking-[0.16em] text-zinc-500')}>Models</div>
                  <div className={cn(desktop ? 'desktop-model-list' : 'max-h-[44vh] overflow-y-auto')}>
                    {visibleModels.map((model) => {
                      const isActive = activeSelection?.provider === activeProvider && activeSelection.model_id === model.model_id;
                      const isFocused = selectedDetail?.provider === activeProvider && selectedDetail?.model.model_id === model.model_id;
                      const isBusy = switching === `${activeProvider}:${model.model_id}`;
                      return (
                        <button
                          key={model.model_id}
                          type="button"
                          onClick={() => desktop ? setFocusedModel({ provider: activeProvider, model }) : handleSelectRegistry(activeProvider, model.model_id)}
                          onDoubleClick={() => handleSelectRegistry(activeProvider, model.model_id)}
                          disabled={!!switching}
                          data-active={desktop && (isActive || isFocused) ? 'true' : undefined}
                          className={cn(
                            desktop ? 'desktop-settings-list-item' : 'mb-1 block w-full rounded-[1rem] border px-4 py-3 text-left last:mb-0',
                            !desktop && isActive ? 'border-cyan-300/30 bg-cyan-300/[0.075] text-zinc-50' : !desktop && 'border-transparent bg-transparent text-zinc-300 hover:border-white/10 hover:bg-white/[0.045] hover:text-cyan-100',
                            isBusy && 'opacity-60'
                          )}
                        >
                          <div className="flex items-start justify-between gap-4">
                            <div className="min-w-0">
                              <div className={cn(desktop ? 'desktop-settings-list-title truncate' : 'truncate text-[13px] font-semibold tracking-[-0.02em] text-inherit')}>{model.display_name}</div>
                              <div className={cn(desktop ? 'desktop-settings-list-meta flex flex-wrap gap-x-3' : 'mt-1 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-zinc-500')}>
                                {formatModelMeta(model).map((part) => <span key={String(part)}>{part}</span>)}
                                {formatModelCost(model) && <span>{formatModelCost(model)}</span>}
                              </div>
                            </div>
                            {isActive && <span className={cn(desktop ? 'desktop-settings-list-active' : 'rounded-full border border-cyan-300/26 bg-cyan-300/[0.10] px-2 py-0.5 text-[10px] uppercase tracking-[0.16em] text-cyan-100')}>Active</span>}
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </section>
              </>
            ) : activeStandaloneProviderKey ? (
              <section className={cn(desktop ? 'desktop-model-account-card' : 'premium-panel p-3')}>
                <div className="min-w-0 flex-1">
                  <div className={cn(desktop ? 'desktop-settings-key-name' : 'text-xs font-semibold text-zinc-200')}>
                    {formatProviderName(activeStandaloneProviderKey.provider, activeStandaloneProviderKey.provider === 'parallel' ? 'Parallel' : undefined)} API key
                  </div>
                  <div className={cn(desktop ? 'desktop-settings-key-env' : 'mt-1 text-xs text-zinc-500')}>
                    {activeStandaloneProviderKey.api_key_env} · {activeStandaloneProviderKey.has_key ? `configured via ${activeStandaloneProviderKey.source}` : 'not configured'}
                  </div>
                  <div className={cn(desktop ? 'desktop-settings-hint mt-2' : 'mt-2 text-xs text-zinc-500')}>
                    {activeStandaloneProviderKey.provider === 'parallel'
                      ? 'Used by agent web_search and web_extract tools. This is not a chat model provider.'
                      : 'Used by agent tools. This is not a chat model provider.'}
                  </div>
                </div>
                <input
                  value={providerKeyDrafts[activeStandaloneProviderKey.provider] || ''}
                  onChange={(e) => setProviderKeyDrafts((drafts) => ({ ...drafts, [activeStandaloneProviderKey.provider]: e.target.value }))}
                  placeholder={activeStandaloneProviderKey.has_key ? 'Enter replacement API key' : 'Enter API key'}
                  type="password"
                  className={cn(desktop ? 'desktop-settings-field flex-1' : 'premium-field flex-1')}
                />
                <button
                  type="button"
                  onClick={() => handleSaveProviderKey(activeStandaloneProviderKey.provider)}
                  disabled={!!switching}
                  className={cn(desktop ? 'desktop-settings-btn-primary' : 'premium-primary-button')}
                >
                  {activeStandaloneProviderKey.has_key ? 'Update' : 'Save'}
                </button>
                {activeStandaloneProviderKey.source === 'database' && (
                  <button
                    type="button"
                    onClick={() => handleClearProviderKey(activeStandaloneProviderKey.provider)}
                    disabled={!!switching}
                    className={cn(desktop ? 'desktop-settings-btn-ghost' : 'premium-subtle-button')}
                  >
                    Clear
                  </button>
                )}
              </section>
            ) : (
              <section className={cn(desktop ? 'desktop-model-section' : 'premium-panel p-2')}>
                <div className={cn(desktop ? 'desktop-settings-provider-header' : 'px-2 pb-2 text-xs uppercase tracking-[0.16em] text-zinc-500')}>
                  {activeLocalSection?.label || 'Local models'}
                </div>
                {activeLocalSection && activeLocalSection.models.length > 0 ? (
                  activeLocalSection.models.map((model) => {
                    const isBusy = switching === `local:${model.path}`;
                    const unsupported = model.supported === false;
                    return (
                      <button
                        key={model.path}
                        onClick={() => handleSelectLocal(model)}
                        disabled={!!switching || unsupported}
                        title={model.status_message || undefined}
                        className={cn(
                          desktop ? 'desktop-settings-list-item' : 'mb-1 block w-full rounded-[1rem] border border-transparent px-4 py-3 text-left text-zinc-300 hover:border-white/10 hover:bg-white/[0.045]',
                          unsupported && 'cursor-not-allowed opacity-50',
                        )}
                      >
                        <div className={cn(desktop ? 'desktop-settings-list-title truncate' : 'truncate text-[13px] font-semibold')}>{model.name}</div>
                        <div className={cn(desktop ? 'desktop-settings-list-meta' : 'mt-1 text-[11px] text-zinc-500')}>
                          {isBusy ? 'Starting…' : unsupported ? (model.model_type_id ? `Unsupported ${model.model_type_id}` : 'Unsupported') : model.size_display}
                        </div>
                      </button>
                    );
                  })
                ) : (
                  <div className={cn(desktop ? 'desktop-settings-hint px-3 py-4' : 'px-3 py-4 text-sm text-zinc-500')}>
                    {activeProvider === 'local-mlx' ? 'No MLX models found.' : 'No GGUF models found.'}
                  </div>
                )}
              </section>
            )}
          </main>

          {desktop && selectedDetail && activeProviderInfo && (
            <aside className="desktop-model-detail-panel">
              <div className="desktop-model-detail-provider">{formatProviderName(selectedDetail.provider, registryData?.providers[selectedDetail.provider]?.display_name)}</div>
              <div className="desktop-model-detail-title">{selectedDetail.model.display_name}</div>
              <div className="desktop-model-detail-id">{selectedDetail.model.model_id}</div>
              <div className="desktop-model-detail-tags">
                {formatModelMeta(selectedDetail.model).map((part) => <span key={String(part)}>{part}</span>)}
              </div>
              <div className="desktop-model-detail-cost">
                {selectedDetail.model.input_cost_per_million != null && selectedDetail.model.output_cost_per_million != null
                  ? formatModelCost(selectedDetail.model)
                  : 'Pricing unavailable'}
              </div>
              <button
                type="button"
                disabled={!!switching || !registryData?.providers[selectedDetail.provider]?.available}
                onClick={() => handleSelectRegistry(selectedDetail.provider, selectedDetail.model.model_id)}
                className="desktop-settings-btn-primary desktop-model-select-btn"
              >
                {switching === `${selectedDetail.provider}:${selectedDetail.model.model_id}` ? 'Selecting…' : 'Select model'}
              </button>
            </aside>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

function ReasoningSettingsDialog({
  open,
  onOpenChange,
  settingsResponse,
  draft,
  onDraftChange,
  onSave,
  saving,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  settingsResponse: ReasoningSettingsResponse | null;
  draft: ReasoningSettings | null;
  onDraftChange: (next: ReasoningSettings) => void;
  onSave: () => void;
  saving: boolean;
}) {
  const capabilities = settingsResponse?.capabilities;
  const providerFamily = settingsResponse?.provider_family || 'generic';
  const modelName = settingsResponse?.model_name || 'model';
  const isFireworks = providerFamily === 'fireworks';
  const showReasoningEffort = !isFireworks && !!capabilities?.reasoning_effort?.supported;
  const showReasoningMaxTokens =
    providerFamily === 'openrouter' && !!capabilities?.reasoning_max_tokens?.supported;
  const fireworksMode = draft?.fireworks_reasoning_mode ?? 'effort';
  const openRouterMode = draft?.reasoning_max_tokens == null ? 'effort' : 'budget';
  const minFireworksThinkingBudget = 1024;
  const desktop = isLocalDesktopApp();
  const inputClassName = desktop ? 'desktop-settings-field' : 'premium-field';
  const selectClassName = 'premium-field appearance-none';

  const effortChoices =
    capabilities?.reasoning_effort?.options?.length
      ? capabilities.reasoning_effort.options
      : ['low', 'medium', 'high'];

  const disabledReason = (supported?: boolean, reason?: string | null) =>
    supported ? undefined : (reason || 'Unsupported by active provider/model');

  const update = <K extends keyof ReasoningSettings>(key: K, value: ReasoningSettings[K]) => {
    if (!draft) return;
    onDraftChange({ ...draft, [key]: value });
  };

  const updateMany = (patch: Partial<ReasoningSettings>) => {
    if (!draft) return;
    onDraftChange({ ...draft, ...patch });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange} className="max-w-3xl">
      <DialogHeader>
        <DialogTitle>Reasoning settings</DialogTitle>
      </DialogHeader>
      <DialogContent className="space-y-4">
        {!draft || !capabilities ? (
          <p className={cn(desktop ? 'desktop-settings-hint' : 'text-xs text-zinc-500')}>Loading reasoning settings…</p>
        ) : (
          <div className={cn('space-y-4', !desktop && 'font-mono text-xs')}>
            <section className={cn(desktop ? 'desktop-settings-section' : 'premium-panel px-4 py-3.5')}>
              <span className={cn(desktop ? 'desktop-settings-label' : 'premium-section-label')}>Active model</span>
              <div className={cn(desktop ? 'desktop-settings-model-line' : 'mt-2 text-sm text-zinc-100')}>{modelName}</div>
              <div className={cn(desktop ? 'desktop-settings-model-provider' : 'mt-1 text-[11px] uppercase tracking-[0.16em] text-zinc-500')}>
                {providerFamily}
              </div>
            </section>

            <section className={cn(desktop ? 'desktop-settings-section' : 'premium-panel px-4 py-4')}>
              <div className="grid gap-4 sm:grid-cols-2">
                <label className="space-y-2">
                  <div>
                    <div className={cn(desktop ? 'desktop-settings-field-label' : 'text-zinc-300')}>Max output</div>
                    <div className={cn(desktop ? 'desktop-settings-hint !mt-1' : 'mt-1 text-[11px] leading-5 text-zinc-500')}>
                      Leave blank to use the active model max.
                    </div>
                  </div>
                  <input
                    type="number"
                    min={1}
                    placeholder="Auto"
                    value={draft.max_output_tokens ?? ''}
                    onChange={(e) => update('max_output_tokens', e.target.value === '' ? null : Number(e.target.value))}
                    className={inputClassName}
                  />
                </label>
                {showReasoningEffort && !showReasoningMaxTokens && (
                  <div className="space-y-2">
                    <div>
                      <div className={cn(desktop ? 'desktop-settings-field-label' : 'text-zinc-300')}>Thinking effort</div>
                      <div className={cn(desktop ? 'desktop-settings-hint !mt-1' : 'mt-1 text-[11px] leading-5 text-zinc-500')}>
                        Provider-managed reasoning depth.
                      </div>
                    </div>
                    {desktop ? (
                      <DesktopTextOptionGroup
                        ariaLabel="Thinking effort"
                        value={draft.reasoning_effort ?? ''}
                        onChange={(value) => update('reasoning_effort', value || null)}
                        options={[
                          { value: '', label: 'Default' },
                          ...effortChoices.map((opt) => ({ value: opt, label: opt })),
                        ]}
                      />
                    ) : (
                      <select
                        value={draft.reasoning_effort ?? ''}
                        onChange={(e) => update('reasoning_effort', e.target.value || null)}
                        disabled={!capabilities.reasoning_effort.supported}
                        title={disabledReason(capabilities.reasoning_effort.supported, capabilities.reasoning_effort.reason)}
                        className={selectClassName}
                      >
                        <option value="">default</option>
                        {effortChoices.map((opt) => (
                          <option key={opt} value={opt}>{opt}</option>
                        ))}
                      </select>
                    )}
                  </div>
                )}
              </div>
            </section>

            {isFireworks ? (
              <section className={cn(desktop ? 'desktop-settings-section' : 'premium-panel px-4 py-4')}>
                <span className={cn(desktop ? 'desktop-settings-label' : 'premium-section-label')}>Fireworks</span>
                <div className="mt-3 grid gap-4 sm:grid-cols-2">
                  <div className="space-y-2">
                    <div className={cn(desktop ? 'desktop-settings-field-label' : 'text-zinc-300')}>Control mode</div>
                    {desktop ? (
                      <DesktopTextOptionGroup
                        ariaLabel="Fireworks control mode"
                        value={draft.fireworks_reasoning_mode}
                        onChange={(nextMode) => {
                          updateMany({
                            fireworks_reasoning_mode: nextMode,
                            fireworks_thinking_budget_tokens:
                              nextMode === 'thinking'
                                ? Math.max(draft.fireworks_thinking_budget_tokens ?? minFireworksThinkingBudget, minFireworksThinkingBudget)
                                : null,
                          });
                        }}
                        options={[
                          { value: 'effort', label: 'Effort' },
                          { value: 'thinking', label: 'Budget' },
                        ]}
                      />
                    ) : (
                      <select
                        value={draft.fireworks_reasoning_mode}
                        onChange={(e) => {
                          const nextMode = e.target.value as 'effort' | 'thinking';
                          updateMany({
                            fireworks_reasoning_mode: nextMode,
                            fireworks_thinking_budget_tokens:
                              nextMode === 'thinking'
                                ? Math.max(draft.fireworks_thinking_budget_tokens ?? minFireworksThinkingBudget, minFireworksThinkingBudget)
                                : null,
                          });
                        }}
                        disabled={!capabilities.fireworks_reasoning_mode.supported}
                        title={disabledReason(capabilities.fireworks_reasoning_mode.supported, capabilities.fireworks_reasoning_mode.reason)}
                        className={selectClassName}
                      >
                        <option value="effort">effort-based</option>
                        <option value="thinking">budget-based</option>
                      </select>
                    )}
                  </div>

                  {fireworksMode === 'effort' ? (
                    <div className="space-y-2">
                      <div className={cn(desktop ? 'desktop-settings-field-label' : 'text-zinc-300')}>Thinking effort</div>
                      {desktop ? (
                        <DesktopTextOptionGroup
                          ariaLabel="Thinking effort"
                          value={draft.reasoning_effort ?? ''}
                          onChange={(value) => update('reasoning_effort', value || null)}
                          options={[
                            { value: '', label: 'Default' },
                            ...effortChoices.map((opt) => ({ value: opt, label: opt })),
                          ]}
                        />
                      ) : (
                        <select
                          value={draft.reasoning_effort ?? ''}
                          onChange={(e) => update('reasoning_effort', e.target.value || null)}
                          disabled={!capabilities.reasoning_effort.supported}
                          title={disabledReason(capabilities.reasoning_effort.supported, capabilities.reasoning_effort.reason)}
                          className={selectClassName}
                        >
                          <option value="">default</option>
                          {effortChoices.map((opt) => (
                            <option key={opt} value={opt}>{opt}</option>
                          ))}
                        </select>
                      )}
                    </div>
                  ) : (
                    <label className="space-y-2">
                      <div className={cn(desktop ? 'desktop-settings-field-label' : 'text-zinc-300')}>Max thinking tokens</div>
                      <input
                        type="number"
                        min={1024}
                        value={draft.fireworks_thinking_budget_tokens ?? ''}
                        onChange={(e) => update('fireworks_thinking_budget_tokens', e.target.value === '' ? null : Number(e.target.value))}
                        onBlur={(e) => update('fireworks_thinking_budget_tokens', Math.max(Number(e.target.value) || minFireworksThinkingBudget, minFireworksThinkingBudget))}
                        disabled={!capabilities.fireworks_thinking_budget_tokens.supported}
                        title={disabledReason(capabilities.fireworks_thinking_budget_tokens.supported, capabilities.fireworks_thinking_budget_tokens.reason)}
                        className={inputClassName}
                      />
                    </label>
                  )}
                </div>
                <p className={cn(desktop ? 'desktop-settings-hint' : 'mt-3 text-[11px] leading-5 text-zinc-500')}>
                  {fireworksMode === 'effort'
                    ? 'Sends reasoning_effort only.'
                    : 'Sends thinking.budget_tokens only.'}
                </p>
              </section>
            ) : showReasoningMaxTokens ? (
              <section className={cn(desktop ? 'desktop-settings-section' : 'premium-panel px-4 py-4')}>
                <span className={cn(desktop ? 'desktop-settings-label' : 'premium-section-label')}>OpenRouter</span>
                <div className="mt-3 grid gap-4 sm:grid-cols-2">
                  <div className="space-y-2">
                    <div className={cn(desktop ? 'desktop-settings-field-label' : 'text-zinc-300')}>Control mode</div>
                    {desktop ? (
                      <DesktopTextOptionGroup
                        ariaLabel="OpenRouter control mode"
                        value={openRouterMode}
                        onChange={(value) => {
                          if (value === 'effort') {
                            updateMany({ reasoning_max_tokens: null });
                          } else {
                            updateMany({ reasoning_max_tokens: draft.reasoning_max_tokens ?? 1024 });
                          }
                        }}
                        options={[
                          { value: 'effort', label: 'Effort' },
                          { value: 'budget', label: 'Budget' },
                        ]}
                      />
                    ) : (
                      <select
                        value={openRouterMode}
                        onChange={(e) => {
                          if (e.target.value === 'effort') {
                            updateMany({ reasoning_max_tokens: null });
                          } else {
                            updateMany({ reasoning_max_tokens: draft.reasoning_max_tokens ?? 1024 });
                          }
                        }}
                        className={selectClassName}
                      >
                        <option value="effort">effort-based</option>
                        <option value="budget">budget-based</option>
                      </select>
                    )}
                  </div>

                  {openRouterMode === 'effort' ? (
                    <div className="space-y-2">
                      <div className={cn(desktop ? 'desktop-settings-field-label' : 'text-zinc-300')}>Thinking effort</div>
                      {desktop ? (
                        <DesktopTextOptionGroup
                          ariaLabel="Thinking effort"
                          value={draft.reasoning_effort ?? ''}
                          onChange={(value) => update('reasoning_effort', value || null)}
                          options={[
                            { value: '', label: 'Default' },
                            ...effortChoices.map((opt) => ({ value: opt, label: opt })),
                          ]}
                        />
                      ) : (
                        <select
                          value={draft.reasoning_effort ?? ''}
                          onChange={(e) => update('reasoning_effort', e.target.value || null)}
                          disabled={!capabilities.reasoning_effort.supported}
                          title={disabledReason(capabilities.reasoning_effort.supported, capabilities.reasoning_effort.reason)}
                          className={selectClassName}
                        >
                          <option value="">default</option>
                          {effortChoices.map((opt) => (
                            <option key={opt} value={opt}>{opt}</option>
                          ))}
                        </select>
                      )}
                    </div>
                  ) : (
                    <label className="space-y-2">
                      <div className={cn(desktop ? 'desktop-settings-field-label' : 'text-zinc-300')}>Max thinking tokens</div>
                      <input
                        type="number"
                        min={1}
                        value={draft.reasoning_max_tokens ?? ''}
                        onChange={(e) => update('reasoning_max_tokens', e.target.value === '' ? null : Number(e.target.value))}
                        disabled={!capabilities.reasoning_max_tokens.supported}
                        title={disabledReason(capabilities.reasoning_max_tokens.supported, capabilities.reasoning_max_tokens.reason)}
                        className={inputClassName}
                      />
                    </label>
                  )}
                </div>
              </section>
            ) : (
              <section className={cn(
                desktop ? 'desktop-settings-section desktop-settings-hint' : 'premium-panel px-4 py-3.5 text-[11px] leading-5 text-zinc-500'
              )}>
                This provider has no separate max thinking token setting.
              </section>
            )}

            <div className={cn(desktop ? 'desktop-settings-actions' : 'flex justify-end gap-2')}>
              <button
                onClick={() => onOpenChange(false)}
                className={cn(desktop ? 'desktop-settings-btn-ghost' : 'premium-subtle-button')}
                type="button"
              >
                Cancel
              </button>
              <button
                onClick={onSave}
                disabled={saving}
                className={cn(desktop ? 'desktop-settings-btn-primary' : 'premium-primary-button')}
                type="button"
              >
                {saving ? 'Saving…' : 'Save'}
              </button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

// Empty string constant to avoid creating new references
const EMPTY_STRING = '';
const missingConversationIds = new Set<string>();

export function markConversationMissing(conversationId: string) {
  missingConversationIds.add(conversationId);
}

export function isConversationMissing(conversationId: string): boolean {
  return missingConversationIds.has(conversationId);
}

const RunMessage = memo(function RunMessage({
  run,
  onRetry,
  canRetry,
}: {
  run: Run;
  onRetry?: (userMessage: string) => void;
  canRetry?: boolean;
}) {
  const isRunning = run.status === 'running';
  const finalAnswer = run.final_answer ? extractAnswer(run.final_answer) : '';
  const userMessage = run.user_message || run.prompt;
  const handleRetryClick = useCallback(() => {
    if (!userMessage || !onRetry) return;
    onRetry(userMessage);
  }, [onRetry, userMessage]);
  const streamingText = useStore((s) => s.streamingText[run.run_id] ?? EMPTY_STRING);
  const streamingThinking = useStore((s) => s.streamingThinking[run.run_id] ?? EMPTY_STRING);

  const displayText = isRunning ? streamingText : finalAnswer;
  const isStreaming = isRunning && streamingText.length > 0;
  const isThinking = isRunning && streamingThinking.length > 0;
  const footerMetrics = getRunFooterMetrics(run);

  return (
    <div className="animate-in fade-in slide-in-from-bottom-2 space-y-5 duration-200">
      <div className="desktop-run">
        <div className="min-w-0 flex-1">
          <div className="desktop-message-card fluxion-card rounded-[1.35rem] border px-6 py-5">
            <span className="whitespace-pre-wrap text-[14px] leading-[1.9] text-zinc-50">
              {run.user_message || run.prompt}
            </span>
          </div>
          <p className="desktop-run-meta mt-2 px-1 text-[11px] text-zinc-500">
            {formatRelativeTime(run.created_at)}
          </p>
        </div>
      </div>

      <div className="desktop-run group/msg">
        <div className="min-w-0 flex-1">
          <div className="desktop-run-stream fluxion-card-strong space-y-4 rounded-[1.35rem] border px-6 py-5">
            <ThinkingPanel
              summary={run.thinking_summary}
              isStreaming={isThinking}
              streamingContent={streamingThinking}
              defaultExpanded={false}
            />

            {isRunning && !displayText && !streamingThinking ? (
              <ShimmerSkeleton />
            ) : isRunning && !displayText && isThinking ? (
              <ThinkingTimer label="Thinking" />
            ) : run.status === 'cancelled' ? (
              <div className="desktop-message-card-cancelled rounded-[1rem] border border-amber-500/16 bg-amber-500/[0.06] px-4 py-3 text-sm text-amber-100/90">
                stopped by user
              </div>
            ) : run.status === 'interrupted' ? (
              <div className="desktop-message-card-cancelled rounded-[1rem] border border-orange-500/16 bg-orange-500/[0.06] px-4 py-3 text-sm text-orange-100/90">
                interrupted by server restart
              </div>
            ) : run.status === 'failed' ? (
              <div className="desktop-message-card-error rounded-[1rem] border border-red-500/16 bg-red-500/[0.06] px-4 py-3 text-sm text-red-200/90">
                [error] {run.error_detail || 'Request failed. Please try again.'}
              </div>
            ) : displayText ? (
              <div className="desktop-run-answer">
                <AnswerMarkdown content={extractAnswer(displayText)} />
                {isStreaming && (
                  <span className="inline-block h-4 w-2 animate-pulse bg-zinc-400 align-[-0.2em] ml-0.5" />
                )}
              </div>
            ) : !isThinking ? (
              <div className="text-sm text-zinc-300">No response.</div>
            ) : null}
          </div>

          <div className="desktop-run-meta mt-2 flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-1 font-mono text-[11px]">
            <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 text-zinc-500">
              <span
                className={cn(
                  'desktop-run-meta-pill rounded-full border border-zinc-800/85 bg-zinc-950/72 px-2.5 py-1',
                  run.status === 'succeeded'
                    ? 'text-emerald-300'
                    : run.status === 'failed'
                      ? 'border-red-500/15 text-red-400/85'
                      : run.status === 'interrupted'
                        ? 'border-orange-500/15 text-orange-300/85'
                      : 'text-zinc-400'
                )}
                data-status={run.status}
              >
                {formatRunStatusLabel(run)}
              </span>
              {run.created_at && (
                <span>{formatRelativeTime(run.created_at)}</span>
              )}
              {footerMetrics.map((metric) => (
                <span key={metric}>{metric}</span>
              ))}
            </div>
            {!isRunning && (
              <MessageActions
                content={finalAnswer || displayText}
                onRetry={onRetry ? handleRetryClick : undefined}
                canRetry={canRetry}
                className="shrink-0 opacity-100 md:opacity-0 md:group-hover/msg:opacity-100"
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
});

function extractActiveMention(value: string, cursor: number): { start: number; end: number; query: string } | null {
  const safeCursor = Math.max(0, Math.min(cursor, value.length));
  const beforeCursor = value.slice(0, safeCursor);
  const tokenStart = Math.max(
    beforeCursor.lastIndexOf(" "),
    beforeCursor.lastIndexOf("\n"),
    beforeCursor.lastIndexOf("\t"),
  ) + 1;
  const token = beforeCursor.slice(tokenStart);
  if (!token.startsWith("@")) return null;
  if (token.length > 1 && token.includes("@", 1)) return null;
  return {
    start: tokenStart,
    end: safeCursor,
    query: token.slice(1),
  };
}

function MentionPicker({
  open,
  loading,
  error,
  entries,
  selectedIndex,
  onSelect,
  desktop,
}: {
  open: boolean;
  loading: boolean;
  error: string | null;
  entries: WorkspaceFileEntry[];
  selectedIndex: number;
  onSelect: (entry: WorkspaceFileEntry) => void;
  desktop?: boolean;
}) {
  const itemRefs = useRef<Array<HTMLButtonElement | null>>([]);

  useEffect(() => {
    if (!open) return;
    const activeItem = itemRefs.current[selectedIndex];
    activeItem?.scrollIntoView({ block: 'nearest' });
  }, [open, selectedIndex, entries]);

  if (!open) return null;

  const statusMessage = loading
    ? 'Searching files…'
    : error
      ? error
      : entries.length === 0
        ? 'No matching files'
        : null;

  if (desktop) {
    return (
      <div
        className="desktop-mention-picker absolute left-0 right-0 bottom-full z-[200] mb-2"
        role="listbox"
        aria-label="Workspace files"
      >
        {statusMessage ? (
          <p
            className={cn(
              'desktop-settings-hint px-2 py-2',
              error && 'desktop-settings-hint-error'
            )}
          >
            {statusMessage}
          </p>
        ) : (
          <div className="desktop-settings-list-panel desktop-mention-picker-list">
            {entries.map((entry, index) => (
              <button
                key={entry.path}
                type="button"
                role="option"
                aria-selected={index === selectedIndex}
                data-active={index === selectedIndex ? 'true' : undefined}
                ref={(node) => {
                  itemRefs.current[index] = node;
                }}
                onMouseDown={(e) => {
                  e.preventDefault();
                  onSelect(entry);
                }}
                className="desktop-settings-list-item font-mono"
              >
                <div className="desktop-settings-list-title truncate">{entry.path}</div>
                <div className="desktop-settings-list-meta truncate">{entry.name}</div>
              </button>
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="ui-panel-strong ui-elevated absolute left-0 right-0 bottom-full z-[200] mb-2 max-h-64 overflow-y-auto rounded-[1rem] border border-white/10">
      {loading ? (
        <div className="px-3 py-2 text-[11px] font-mono text-zinc-300">searching files...</div>
      ) : error ? (
        <div className="px-3 py-2 text-[11px] font-mono text-red-300">{error}</div>
      ) : entries.length === 0 ? (
        <div className="px-3 py-2 text-[11px] font-mono text-zinc-500">no matching files</div>
      ) : (
        entries.map((entry, index) => (
          <button
            key={entry.path}
            type="button"
            ref={(node) => {
              itemRefs.current[index] = node;
            }}
            onMouseDown={(e) => {
              e.preventDefault();
              onSelect(entry);
            }}
            className={cn(
              "ui-transition block w-full px-3 py-2.5 text-left font-mono text-[11px]",
              index === selectedIndex
                ? "bg-cyan-300/[0.08] text-zinc-50"
                : "text-zinc-300 hover:bg-white/[0.045] hover:text-cyan-100"
            )}
          >
            <div className="truncate">{entry.path}</div>
            <div className="truncate text-[10px] text-zinc-500">{entry.name}</div>
          </button>
        ))
      )}
    </div>
  );
}

function conversationTitleFromMessage(message: string, maxLen = 64): string {
  const cleaned = message.trim().replace(/\s+/g, ' ');
  if (!cleaned) return 'New conversation';

  let normalized = cleaned.toLowerCase();
  const fillerPatterns = [
    /^(?:hey|hi|hello|yo|yoo|yup|okay|ok|alright|please)\s+/,
    /^(?:can|could|would|will)\s+you\s+/,
    /^i\s+need\s+you\s+to\s+/,
    /^help\s+me\s+(?:with\s+)?/,
  ];
  for (const pattern of fillerPatterns) {
    normalized = normalized.replace(pattern, '');
  }
  normalized = normalized.replace(/^[ .!?,;:-]+|[ .!?,;:-]+$/g, '');

  const issuePhrase = (value: string) => {
    let next = value.replace(/\bstill\b\s*/g, '').trim();
    next = next.replace(/\b(?:look|looks|feel|feels)\s+/, '');
    if (/\bcramped\b/.test(next)) {
      next = next.replace(/\bcramped\b/, 'too cramped');
    }
    return next;
  };

  const smartTitleFromNormalized = (value: string): string => {
    const patterns: Array<[RegExp, string]> = [
      [/^(?:explain\s+why|why\s+(?:is|are|does|do|did))\s+/, 'Issue: '],
      [/^how\s+(?:do|can|should|would)\s+i\s+/, 'How to '],
      [/^how\s+to\s+/, 'How to '],
      [/^what\s+(?:is|are)\s+/, 'About '],
      [/^explain\s+/, 'About '],
      [/^tell\s+me\s+(?:about\s+)?/, 'About '],
    ];
    for (const [pattern, prefix] of patterns) {
      const match = value.match(pattern);
      if (!match) continue;
      const body = value.slice(match[0].length).trim();
      if (!body) break;
      const content = prefix === 'Issue: ' ? issuePhrase(body) : body;
      return `${prefix}${content ? `${content[0].toUpperCase()}${content.slice(1)}` : content}`;
    }
    return value;
  };

  const smart = smartTitleFromNormalized(normalized) || cleaned;
  const title = smart.replace(/^[ .!?,;:-]+|[ .!?,;:-]+$/g, '');
  const sentenceCased = title ? `${title[0].toUpperCase()}${title.slice(1)}` : 'New conversation';
  if (sentenceCased.length <= maxLen) {
    return sentenceCased;
  }
  return `${sentenceCased.slice(0, maxLen - 3).trim()}...`;
}

export function ConversationView() {
  const navigate = useNavigate();
  const selectedConversationId = useStore((s) => s.selectedConversationId);
  const selectConversation = useStore((s) => s.selectConversation);
  const setRuns = useStore((s) => s.setRuns);
  const updateConversation = useStore((s) => s.updateConversation);
  const addConversation = useStore((s) => s.addConversation);
  const addRun = useStore((s) => s.addRun);
  const updateRun = useStore((s) => s.updateRun);
  const removeRun = useStore((s) => s.removeRun);
  const clearAgentRun = useStore((s) => s.clearAgentRun);
  const setEvents = useStore((s) => s.setEvents);
  const conversation = useSelectedConversation();
  const runs = useConversationRuns(selectedConversationId);
  const terminalState = useConversationTerminal(selectedConversationId);
  const draftTerminalState = useConversationTerminal(DRAFT_TERMINAL_CONVERSATION_ID);
  const initTerminalState = useStore((s) => s.initTerminalState);
  const hasActiveRun = useHasActiveRun();
  const setConversationMode = useStore((s) => s.setConversationMode);
  const updateTerminalState = useStore((s) => s.updateTerminalState);
  const setDesktopOverlayOpen = useStore((s) => s.setDesktopOverlayOpen);
  const draftWorkspacePath = useStore((s) => s.draftWorkspacePath);
  const draftConversationNonce = useStore((s) => s.draftConversationNonce);
  const setDraftWorkspacePath = useStore((s) => s.setDraftWorkspacePath);
  const rememberWorkspacePath = useStore((s) => s.rememberWorkspacePath);
  const beginWorkspaceDraft = useStore((s) => s.beginWorkspaceDraft);
  const [message, setMessage] = useState('');
  const [imageAttachments, setImageAttachments] = useState<ImageAttachment[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [loadingConversationId, setLoadingConversationId] = useState<string | null>(null);
  const [mode, setMode] = useState<ChatMode>('agent');
  const localDesktop = isLocalDesktopApp();
  const [workspacePickerOpen, setWorkspacePickerOpen] = useState(false);
  const [workspacePickerMode, setWorkspacePickerMode] = useState<'draft' | 'new-conversation'>('draft');
  const [mentionResults, setMentionResults] = useState<WorkspaceFileEntry[]>([]);
  const [mentionOpen, setMentionOpen] = useState(false);
  const [mentionLoading, setMentionLoading] = useState(false);
  const [mentionError, setMentionError] = useState<string | null>(null);
  const [mentionSelectedIndex, setMentionSelectedIndex] = useState(0);
  const [activeMention, setActiveMention] = useState<{ start: number; end: number; query: string } | null>(null);
  const [permissionPolicy, setPermissionPolicy] = useState<'strict' | 'relaxed' | 'yolo'>(
    () => (localStorage.getItem('reasoner_permission_policy') as 'strict' | 'relaxed' | 'yolo') || 'strict'
  );
  const [collaborationMode, setCollaborationMode] = useState<'default' | 'plan'>(
    () => (localStorage.getItem('reasoner_collaboration_mode') as 'default' | 'plan') || 'default'
  );
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const verticalMoveColumnRef = useRef<number | null>(null);
  const composerFocusRafRef = useRef<number | null>(null);
  const bottomScrollRafRef = useRef<number | null>(null);
  const pendingWorkspaceShortcutRef = useRef<'workspace-new' | 'workspace-picker' | null>(null);
  const pendingWorkspaceShortcutTimeoutRef = useRef<number | null>(null);
  const lastEscapeAtRef = useRef(0);

  // Model picker state
  const [modelPickerOpen, setModelPickerOpen] = useState(false);
  const [modelStatus, setModelStatus] = useState<ModelStatus | null>(null);
  const [draftModelSelection, setDraftModelSelection] = useState<ConversationModelSelection | null>(null);
  const defaultModelStatusRef = useRef<ModelStatus | null>(null);
  const [reasoningSettingsOpen, setReasoningSettingsOpen] = useState(false);
  const [reasoningSettings, setReasoningSettings] = useState<ReasoningSettingsResponse | null>(null);
  const [reasoningDraft, setReasoningDraft] = useState<ReasoningSettings | null>(null);
  const [reasoningSaving, setReasoningSaving] = useState(false);

  // Usage limits state
  const [usage, setUsage] = useState<UsageInfo>({ limit: -1, used: 0, remaining: -1 });
  const hasLimit = usage.limit > 0;
  const atLimit = hasLimit && usage.remaining <= 0;

  const refreshUsage = useCallback(() => {
    getUsage().then(setUsage).catch(() => {});
  }, []);

  const refreshReasoningSettings = useCallback(() => {
    getReasoningSettings()
      .then((data) => {
        setReasoningSettings(data);
        setReasoningDraft(data.settings);
      })
      .catch(() => {});
  }, []);

  const clearMentionState = useCallback(() => {
    setActiveMention(null);
    setMentionOpen(false);
    setMentionLoading(false);
    setMentionError(null);
    setMentionResults([]);
    setMentionSelectedIndex(0);
  }, []);

  useEffect(() => {
    if (selectedConversationId) return;
    setMessage('');
    setImageAttachments([]);
    clearMentionState();
    window.requestAnimationFrame(() => textareaRef.current?.focus());
  }, [clearMentionState, draftConversationNonce, selectedConversationId]);

  useEffect(() => {
    localStorage.setItem('reasoner_permission_policy', permissionPolicy);
  }, [permissionPolicy]);

  useEffect(() => {
    localStorage.setItem('reasoner_collaboration_mode', collaborationMode);
  }, [collaborationMode]);

  useEffect(() => {
    const conversationId = conversation?.conversation_id;
    const workspacePath = conversation?.workspace_path?.trim();
    if (!conversationId || !workspacePath) return;

    // This effect is only allowed to mirror the workspace for the conversation
    // that is still selected *at effect time*. Passive effects from the previous
    // conversation can otherwise run after New Workspace clears the selection and
    // overwrite the just-picked draft workspace with the old conversation folder.
    if (useStore.getState().selectedConversationId !== conversationId) return;

    setDraftWorkspacePath(workspacePath);
  }, [conversation?.conversation_id, conversation?.workspace_path, setDraftWorkspacePath]);

  useEffect(() => {
    if (!selectedConversationId) {
      return;
    }

    let savedState: Partial<{
      isOpen: boolean;
      dock: 'bottom' | 'right';
      height: number;
      width: number;
    }> = {};

    try {
      savedState = JSON.parse(localStorage.getItem(`reasoner_terminal_state:${selectedConversationId}`) || '{}');
    } catch {
      savedState = {};
    }

    const existingState = useStore.getState().terminalByConversation[selectedConversationId];
    initTerminalState(selectedConversationId, {
      isOpen: existingState?.isOpen ?? savedState.isOpen ?? false,
      dock: 'right',
      height: Number(existingState?.height || savedState.height || 260),
      width: Number(existingState?.width || savedState.width || 420),
    });
  }, [initTerminalState, selectedConversationId]);

  useEffect(() => {
    if (!selectedConversationId || !terminalState) {
      return;
    }

    localStorage.setItem(
      `reasoner_terminal_state:${selectedConversationId}`,
      JSON.stringify({
        isOpen: terminalState.isOpen,
        dock: terminalState.dock,
        height: terminalState.height,
        width: terminalState.width,
      })
    );
  }, [selectedConversationId, terminalState]);

  useEffect(() => {
    setConversationMode(mode);
  }, [mode, setConversationMode]);

  // Fetch model status and usage on mount
  useEffect(() => {
    getModelStatus().then((status) => {
      if (!defaultModelStatusRef.current) defaultModelStatusRef.current = status;
      setModelStatus(status);
    }).catch(() => {});
    refreshUsage();
    refreshReasoningSettings();
  }, [refreshUsage, refreshReasoningSettings]);

  useEffect(() => {
    const selection = getConversationModelSelection(conversation);
    if (selection) {
      setModelStatus((current) => modelStatusFromSelection(selection, current));
      return;
    }
    if (!selectedConversationId && draftModelSelection) {
      setModelStatus((current) => modelStatusFromSelection(draftModelSelection, current));
      return;
    }
    if (defaultModelStatusRef.current) {
      setModelStatus(defaultModelStatusRef.current);
      return;
    }
    void getModelStatus().then((status) => {
      if (!defaultModelStatusRef.current) defaultModelStatusRef.current = status;
      setModelStatus(status);
    }).catch(() => {});
  }, [conversation?.conversation_id, conversation?.metadata, draftModelSelection, selectedConversationId]);

  useEffect(() => {
    if (!modelStatus) return;
    refreshReasoningSettings();
  }, [modelStatus?.provider, modelStatus?.model_name, refreshReasoningSettings]);

  // Stop generation state
  const [pendingMessage, setPendingMessage] = useState('');
  // Track run IDs we already subscribed to in handleSubmit, so
  // loadConversation doesn't open a second EventSource for the same run.
  const subscribedRunRef = useRef<string | null>(null);
  const [pendingRunId, setPendingRunId] = useState<string | null>(null);
  const [pendingIsAgent, setPendingIsAgent] = useState(false);
  const [stoppingRunId, setStoppingRunId] = useState<string | null>(null);
  const [queuedSteers, setQueuedSteers] = useState<string[]>([]);
  const [rewindOpen, setRewindOpen] = useState(false);
  const [rewindLoading, setRewindLoading] = useState(false);
  const [rewindSubmitting, setRewindSubmitting] = useState(false);
  const [rewindCheckpoints, setRewindCheckpoints] = useState<ConversationRewindCheckpoint[]>([]);
  const [rewindSelectedRunId, setRewindSelectedRunId] = useState<string | null>(null);
  const rewindLoadInFlightRef = useRef(false);
  const rewindRestoreInFlightRef = useRef(false);

  // Track any active run (chat or agent) for UI purposes (auto-scroll, completion detection)
  const activeRun = useMemo(() => {
    for (let i = runs.length - 1; i >= 0; i -= 1) {
      if (runs[i].status === 'running') {
        return runs[i];
      }
    }
    return null;
  }, [runs]);
  const activeRunId = activeRun?.run_id ?? null;
  const activeAgentRun = useMemo(() => {
    for (let i = runs.length - 1; i >= 0; i -= 1) {
      if (runs[i].status === 'running' && runs[i].mode === 'agent') {
        return runs[i];
      }
    }
    return null;
  }, [runs]);
  const activeAgentHudState = useAgentRunDetails(activeAgentRun?.run_id ?? null, !!activeAgentRun);
  const activeModelSelection = getConversationModelSelection(conversation) || draftModelSelection;

  // Clear queued steers when agent confirms injection via SSE.
  // Delay the clear so the chip is visible briefly before disappearing.
  const activeAgentState = useStore((s) => activeRunId ? s.agentRunState[activeRunId] : undefined);
  const latestContextRun = useMemo(
    () => [...runs].reverse().find((run) => (
      run.mode === 'agent'
      || !!run.context_usage
      || !!run.context_profile
      || !!run.stored_context
    )),
    [runs],
  );
  const lockedWorkspacePath = (conversation?.workspace_path || '').trim();
  const hasConversationWorkspace = lockedWorkspacePath.length > 0;
  const isWorkspaceLocked = selectedConversationId !== null && !!conversation;
  const effectiveWorkspacePath = isWorkspaceLocked ? lockedWorkspacePath : draftWorkspacePath.trim();
  const anyDialogOpen = (
    workspacePickerOpen
    || modelPickerOpen
    || reasoningSettingsOpen
    || rewindOpen
  );
  useEffect(() => {
    if (!localDesktop) return;
    setDesktopOverlayOpen(anyDialogOpen);
    return () => setDesktopOverlayOpen(false);
  }, [anyDialogOpen, localDesktop, setDesktopOverlayOpen]);
  const latestRunContextUsage = latestContextRun?.context_usage;
  const footerContextUsage = useMemo(() => (
    activeAgentState?.context_usage
    ?? latestRunContextUsage
    ?? undefined
  ), [activeAgentState?.context_usage, latestRunContextUsage]);
  const conversationTokenAndCostTotals = useMemo(() => {
    return runs.reduce(
      (totals, run) => {
        const usage = normalizeTokenUsage(
          run.run_id === activeRunId && activeAgentState?.usage
            ? activeAgentState.usage
            : run.usage
        );
        const cost = run.run_id === activeRunId && activeAgentState?.cost
          ? activeAgentState.cost
          : run.cost;

        totals.inputTokens += usage?.input_tokens ?? 0;
        totals.outputTokens += usage?.output_tokens ?? 0;
        totals.inputCost += inputCostTotal(cost);
        totals.outputCost += outputCostTotal(cost);
        return totals;
      },
      { inputTokens: 0, outputTokens: 0, inputCost: 0, outputCost: 0 },
    );
  }, [runs, activeRunId, activeAgentState?.usage, activeAgentState?.cost]);
  const composerContextWindow = (
    activeAgentState?.context_profile?.context_window
    ?? modelStatus?.context_window
    ?? (latestContextRun?.context_profile as { context_window?: number } | undefined)?.context_window
    ?? footerContextUsage?.context_window
  );
  const composerPromptTokens = footerContextUsage?.prompt_tokens_current_call;
  const composerContextUtilizationPct = (
    typeof composerPromptTokens === 'number'
    && typeof composerContextWindow === 'number'
    && composerContextWindow > 0
      ? (composerPromptTokens / composerContextWindow) * 100
      : null
  );
  const showComposerContextStats = mode === 'agent' && !!composerContextWindow && (
    !!footerContextUsage
    || conversationTokenAndCostTotals.inputTokens + conversationTokenAndCostTotals.outputTokens > 0
    || conversationTokenAndCostTotals.inputCost + conversationTokenAndCostTotals.outputCost > 0
  );
  const injectedSteerCount = activeAgentState?.injectedSteers?.length ?? 0;

  const openRewindPicker = useCallback(async () => {
    if (
      !selectedConversationId
      || hasActiveRun
      || !lockedWorkspacePath
      || rewindLoadInFlightRef.current
      || rewindRestoreInFlightRef.current
    ) {
      return;
    }
    rewindLoadInFlightRef.current = true;
    setRewindLoading(true);
    setRewindSubmitting(false);
    setRewindOpen(true);
    try {
      const response = await listConversationRewindCheckpoints(selectedConversationId);
      setRewindCheckpoints(response.checkpoints);
      setRewindSelectedRunId(response.checkpoints[0]?.run_id ?? null);
    } catch {
      setRewindOpen(false);
      toast.error('Failed to load rewind history');
    } finally {
      setRewindLoading(false);
      rewindLoadInFlightRef.current = false;
    }
  }, [hasActiveRun, lockedWorkspacePath, selectedConversationId]);

  const handleRewindRestore = useCallback(async () => {
    if (
      !selectedConversationId
      || !rewindSelectedRunId
      || rewindSubmitting
      || rewindRestoreInFlightRef.current
    ) {
      return;
    }
    rewindRestoreInFlightRef.current = true;
    setRewindSubmitting(true);
    try {
      const response = await rewindConversation(selectedConversationId, {
        run_id: rewindSelectedRunId,
      });
      for (const rewoundRunId of response.rewound_run_ids) {
        clearAgentRun(rewoundRunId);
        removeRun(rewoundRunId);
      }
      updateConversation(selectedConversationId, response.conversation);
      setRuns(selectedConversationId, response.runs);
      setMessage(response.restored_prompt);
      setImageAttachments([]);
      clearMentionState();
      setQueuedSteers([]);
      setRewindOpen(false);
      requestAnimationFrame(() => {
        const textarea = textareaRef.current;
        if (!textarea || textarea.disabled) return;
        textarea.focus();
        const end = textarea.value.length;
        textarea.setSelectionRange(end, end);
      });
    } catch (error: unknown) {
      const message = (error as { message?: string })?.message || 'Failed to rewind conversation';
      toast.error(message);
    } finally {
      setRewindSubmitting(false);
      rewindRestoreInFlightRef.current = false;
    }
  }, [
    clearAgentRun,
    clearMentionState,
    removeRun,
    rewindSelectedRunId,
    rewindSubmitting,
    selectedConversationId,
    setRuns,
    updateConversation,
  ]);

  const handleRewindOpenChange = useCallback((open: boolean) => {
    setRewindOpen(open);
    if (!open && !rewindRestoreInFlightRef.current) {
      rewindLoadInFlightRef.current = false;
      setRewindLoading(false);
      setRewindCheckpoints([]);
      setRewindSelectedRunId(null);
      lastEscapeAtRef.current = 0;
    }
  }, []);

  useEffect(() => {
    rewindLoadInFlightRef.current = false;
    rewindRestoreInFlightRef.current = false;
    setRewindOpen(false);
    setRewindLoading(false);
    setRewindSubmitting(false);
    setRewindCheckpoints([]);
    setRewindSelectedRunId(null);
    lastEscapeAtRef.current = 0;
  }, [selectedConversationId]);
  useEffect(() => {
    if (injectedSteerCount > 0 && queuedSteers.length > 0) {
      const timer = setTimeout(() => setQueuedSteers([]), 1500);
      return () => clearTimeout(timer);
    }
  }, [injectedSteerCount, queuedSteers.length]);

  // Only track chat (non-agent) runs for useSSE auto-subscribe.
  // Agent runs are managed manually via useAgentSSE.
  const activeChatRunId = useMemo(() => {
    for (let i = runs.length - 1; i >= 0; i -= 1) {
      if (runs[i].status === 'running' && runs[i].mode !== 'agent') {
        return runs[i].run_id;
      }
    }
    return null;
  }, [runs]);

  // Get subscribe/unsubscribe functions from useSSE (chat mode)
  const { subscribe, unsubscribe } = useSSE(activeChatRunId);

  // Get subscribe/unsubscribe functions from useAgentSSE (agent mode)
  const { subscribe: subscribeAgent } = useAgentSSE(null); // Manual subscription, not auto

  const scrollConversationToBottom = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, []);

  const scheduleConversationBottomScroll = useCallback((frames = 18) => {
    if (typeof window === 'undefined') return;
    if (bottomScrollRafRef.current !== null) {
      window.cancelAnimationFrame(bottomScrollRafRef.current);
      bottomScrollRafRef.current = null;
    }

    let framesRemaining = frames;
    const tick = () => {
      scrollConversationToBottom();
      framesRemaining -= 1;
      if (framesRemaining > 0) {
        bottomScrollRafRef.current = window.requestAnimationFrame(tick);
      } else {
        bottomScrollRafRef.current = null;
      }
    };

    bottomScrollRafRef.current = window.requestAnimationFrame(tick);
  }, [scrollConversationToBottom]);

  useEffect(() => () => {
    if (bottomScrollRafRef.current !== null) {
      window.cancelAnimationFrame(bottomScrollRafRef.current);
      bottomScrollRafRef.current = null;
    }
  }, []);

  useEffect(() => {
    if (!selectedConversationId) {
      setLoadingConversationId(null);
      return;
    }

    setLoadingConversationId(selectedConversationId);
    let cancelled = false;

    async function loadConversation() {
      try {
        const data = await getConversation(selectedConversationId!);
        if (cancelled) return;
        updateConversation(selectedConversationId!, data.conversation);
        setRuns(selectedConversationId!, data.runs);

        // Auto-reconnect to any active runs after page reload.
        // Skip if we already subscribed in handleSubmit (prevents double EventSource).
        for (const run of data.runs) {
          if (run.status === 'running') {
            if (run.mode === 'agent') {
              if (subscribedRunRef.current === run.run_id) {
                // Already subscribed from handleSubmit — don't open a second connection
                continue;
              }
              // Reconnect to agent SSE stream with stored token (e.g. after page reload)
              const streamToken = localStorage.getItem(`stream_token:${run.run_id}`) || undefined;
              subscribeAgent(run.run_id, 0, streamToken);
            } else {
              // Reconnect to chat SSE stream
              subscribe(run.run_id);
            }
          }
        }
      } catch (error: unknown) {
        if (cancelled) return;
        // Conversation might not exist anymore after deletes or stale URLs.
        // Clear the stale selected id so draft workspace state keeps working,
        // including @ file mentions in the composer.
        console.error('Failed to load conversation:', error);
        if ((error as { status?: number })?.status === 404) {
          markConversationMissing(selectedConversationId!);
          selectConversation(null);
          setRuns(selectedConversationId!, []);
          navigate('/conversations', { replace: true });
        }
      } finally {
        if (!cancelled) {
          setLoadingConversationId((current) => (
            current === selectedConversationId ? null : current
          ));
        }
      }
    }

    loadConversation();
    return () => {
      cancelled = true;
    };
  }, [navigate, selectConversation, selectedConversationId, setRuns, updateConversation, subscribe, subscribeAgent]);

  const runListKey = useMemo(
    () => runs.map((run) => run.run_id).join('|'),
    [runs],
  );
  const isLoadingSelectedConversation = loadingConversationId === selectedConversationId;

  // Opening a conversation should land on the latest exchange. For long chats
  // the virtualized list first renders from estimated row heights, then corrects
  // height measurements over the next few frames; keep pinning to bottom during
  // that initial measurement window so the scrollbar does not settle mid-thread.
  useLayoutEffect(() => {
    scheduleConversationBottomScroll();
  }, [runListKey, scheduleConversationBottomScroll, selectedConversationId]);

  // Auto-scroll during streaming - watch streaming text length for active run
  const lastStreamLen = useStore((s) => {
    if (!activeRunId) return 0;
    const text = s.streamingText[activeRunId] ?? '';
    const thinking = s.streamingThinking[activeRunId] ?? '';
    return text.length + thinking.length;
  });
  const activeAgentScrollSignal = useStore((s) => {
    if (!activeRunId) return '';
    const agentState = s.agentRunState[activeRunId];
    if (!agentState) return '';
    return [
      agentState.currentStep,
      agentState.steps.length,
      agentState.toolCalls.length,
      agentState.thinkingBuffer.length,
      agentState.answerBuffer.length,
      agentState.agentState,
    ].join(':');
  });

  useEffect(() => {
    if (!scrollRef.current || !activeRunId || !activeAgentRun) return;
    const el = scrollRef.current;
    requestAnimationFrame(() => {
      el.scrollTop = el.scrollHeight;
    });
  }, [activeAgentScrollSignal, activeRunId, activeAgentRun]);

  useEffect(() => {
    if (!scrollRef.current || !activeRunId || activeAgentRun) return;
    const el = scrollRef.current;
    const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 150;
    if (isNearBottom) {
      requestAnimationFrame(() => {
        el.scrollTop = el.scrollHeight;
      });
    }
  }, [lastStreamLen, activeRunId, activeAgentRun]);

  const focusComposer = useCallback(() => {
    const textarea = textareaRef.current;
    if (!textarea || textarea.disabled) return;
    textarea.focus();
    const end = textarea.value.length;
    textarea.setSelectionRange(end, end);
  }, []);

  const scheduleComposerFocus = useCallback(() => {
    if (composerFocusRafRef.current !== null) {
      cancelAnimationFrame(composerFocusRafRef.current);
    }
    composerFocusRafRef.current = requestAnimationFrame(() => {
      composerFocusRafRef.current = requestAnimationFrame(() => {
        focusComposer();
        composerFocusRafRef.current = null;
      });
    });
  }, [focusComposer]);

  /** Retry a message: pre-fill the input with the original user message */
  const handleRetry = useCallback((userMessage: string) => {
    if (hasActiveRun) return;
    clearMentionState();
    setMessage(userMessage);
    requestAnimationFrame(focusComposer);
  }, [clearMentionState, focusComposer, hasActiveRun]);

  const renderRunCard = useCallback((run: Run) => (
    run.mode === 'agent' ? (
      <AgentRunMessage
        key={run.run_id}
        run={run}
        onRetry={handleRetry}
        canRetry={!hasActiveRun}
      />
    ) : (
      <RunMessage
        key={run.run_id}
        run={run}
        onRetry={handleRetry}
        canRetry={!hasActiveRun}
      />
    )
  ), [handleRetry, hasActiveRun]);

  const handleSaveReasoningSettings = useCallback(async () => {
    if (!reasoningDraft) return;
    setReasoningSaving(true);
    try {
      const updated = await updateReasoningSettings(reasoningDraft);
      setReasoningSettings(updated);
      setReasoningDraft(updated.settings);
      setReasoningSettingsOpen(false);
      const status = await getModelStatus();
      setModelStatus(status);
      toast.success('Reasoning settings updated');
    } catch (error: unknown) {
      const message = (error as { message?: string })?.message || 'Failed to update reasoning settings';
      toast.error(message);
    } finally {
      setReasoningSaving(false);
    }
  }, [reasoningDraft]);

  const handleModelStatusChange = useCallback((status: ModelStatus, selection?: ConversationModelSelection | null) => {
    setModelStatus(status);
    if (!selection) return;
    if (!selectedConversationId) {
      setDraftModelSelection(selection);
      return;
    }
    const nextMetadata = {
      ...(conversation?.metadata || {}),
      [CONVERSATION_MODEL_METADATA_KEY]: selection,
    };
    setDraftModelSelection(null);
    updateConversation(selectedConversationId, { metadata: nextMetadata });
    void patchConversation(selectedConversationId, {
      metadata: { [CONVERSATION_MODEL_METADATA_KEY]: selection },
    }).catch(() => {
      toast.error('Failed to save conversation model');
    });
  }, [conversation?.metadata, selectedConversationId, updateConversation]);

  const handleOpenWorkspacePicker = useCallback(async () => {
    if (isWorkspaceLocked) {
      toast.error(
        hasConversationWorkspace
          ? 'This conversation is already bound to its workspace'
          : 'This conversation has no workspace. Create a new workspace thread from the sidebar.'
      );
      return;
    }
    if (isLocalDesktopApp()) {
      const selectedPath = await openNativeWorkspacePicker();
      if (selectedPath) {
        rememberWorkspacePath(selectedPath);
        setDraftWorkspacePath(selectedPath);
      }
      return;
    }
    setWorkspacePickerMode('draft');
    setWorkspacePickerOpen(true);
  }, [
    hasConversationWorkspace,
    isWorkspaceLocked,
    rememberWorkspacePath,
    setDraftWorkspacePath,
  ]);

  const handleSubmit = async () => {
    if ((!message.trim() && imageAttachments.length === 0) || isSubmitting) return;
    if (imageAttachments.length > 0 && !modelStatus?.supports_vision) {
      toast.error('Active model does not support images. Select a vision model.');
      return;
    }

    // If an agent run is active, steer it instead of creating a new run
    if (canSteerActiveRun && activeRunId) {
      if (imageAttachments.length > 0) {
        toast.error('Image paste is only available before starting a run.');
        return;
      }
      const steerMsg = message.trim();
      console.log(`[Steer] Attempting to steer run ${activeRunId}, message: "${steerMsg.substring(0, 50)}..."`);
      setMessage('');
      clearMentionState();
      try {
        await steerAgentRun(activeRunId, steerMsg);
        setQueuedSteers((prev) => [...prev, steerMsg]);
        scheduleComposerFocus();
      } catch (error: unknown) {
        console.error('Steer API failed:', error);
        const errMsg = error instanceof Error ? error.message : String(error);
        const apiError = error as { status?: number; message?: string };
        toast.error(`Steer failed: ${apiError.status || 'N/A'} - ${errMsg}`);
        setMessage(steerMsg);
        scheduleComposerFocus();
      }
      return;
    }

    if (hasActiveRun) return; // Non-agent active run, block

    let conversationId = selectedConversationId;

    if (!conversationId && !effectiveWorkspacePath) {
      toast.error('Choose a workspace first');
      setWorkspacePickerOpen(true);
      return;
    }

    const attachmentsToSend = imageAttachments.map(({ name, mime_type, data_url }) => ({
      name,
      mime_type,
      data_url,
    }));
    const messageToSend = message.trim() || 'Please analyze the attached image.';
    setIsSubmitting(true);
    setPendingMessage(messageToSend);
    setMessage('');
    setImageAttachments([]);
    clearMentionState();
    setPendingIsAgent(mode === 'agent');

    // Track whether we need to navigate after setup (deferred to prevent
    // useEffect from re-subscribing while handleSubmit is still in flight)
    let needsNavigate = false;

    try {
      // Create conversation if needed
      if (!conversationId) {
        const response = await createConversation({
          workspace_path: effectiveWorkspacePath,
          metadata: activeModelSelection
            ? { [CONVERSATION_MODEL_METADATA_KEY]: activeModelSelection }
            : undefined,
        });
        conversationId = response.conversation_id;
        rememberWorkspacePath(effectiveWorkspacePath);
        const newConversation: Conversation = {
          conversation_id: conversationId,
          created_at: new Date().toISOString(),
          title: conversationTitleFromMessage(messageToSend),
          summary: '',
          workspace_path: effectiveWorkspacePath,
          status: 'active',
          metadata: activeModelSelection
            ? { [CONVERSATION_MODEL_METADATA_KEY]: activeModelSelection }
            : {},
        };
        addConversation(newConversation);
        setRuns(conversationId, []);
        if (draftTerminalState?.isOpen) {
          let attachedSessions = draftTerminalState.sessions ?? [];
          try {
            const attached = await attachDraftTerminalSessions(conversationId, {
              workspace_path: effectiveWorkspacePath,
            });
            attachedSessions = attached.sessions;
          } catch {
            toast.error('Draft terminal could not attach to the new conversation');
          }
          const bufferBySessionId = Object.fromEntries(
            attachedSessions.map((session) => [
              session.session_id,
              session.replay_buffer || draftTerminalState.bufferBySessionId[session.session_id] || '',
            ]),
          );
          const activeSessionId = attachedSessions.find(
            (item) => item.session_id === draftTerminalState.activeSessionId
          )?.session_id ?? attachedSessions[0]?.session_id ?? null;
          const activeSession = activeSessionId
            ? attachedSessions.find((item) => item.session_id === activeSessionId) ?? null
            : null;
          initTerminalState(conversationId, {
            isOpen: true,
            dock: draftTerminalState.dock,
            width: draftTerminalState.width,
            height: draftTerminalState.height,
            activeToolTabId: draftTerminalState.activeToolTabId,
            browserTabs: draftTerminalState.browserTabs,
            sessions: attachedSessions,
            activeSessionId,
            session: activeSession,
            bufferBySessionId,
            buffer: activeSessionId ? (bufferBySessionId[activeSessionId] ?? '') : '',
            connected: false,
            status: attachedSessions.length > 0 ? 'running' : 'idle',
          });
          localStorage.setItem(
            `reasoner_terminal_state:${conversationId}`,
            JSON.stringify({
              isOpen: true,
              dock: draftTerminalState.dock,
              height: draftTerminalState.height,
              width: draftTerminalState.width,
            })
          );
          selectConversation(conversationId);
          updateTerminalState(DRAFT_TERMINAL_CONVERSATION_ID, {
            isOpen: false,
            sessions: [],
            activeSessionId: null,
            activeToolTabId: null,
            browserTabs: [],
            session: null,
            buffer: '',
            bufferBySessionId: {},
            connected: false,
            status: 'idle',
          });
        }
        needsNavigate = true;
      } else if (!conversation?.title || conversation.title === 'New conversation') {
        updateConversation(conversationId, {
          title: conversationTitleFromMessage(messageToSend),
        });
      }

      if (mode === 'agent') {
        // Agent mode: use agent API
        const response = await createAgentRun(
          {
            query: messageToSend,
            image_attachments: attachmentsToSend,
            conversation_id: conversationId!,
            max_steps: 1000,
            workspace_path: effectiveWorkspacePath || undefined,
            filesystem_enabled: !!effectiveWorkspacePath,
            permission_policy: permissionPolicy,
            collaboration_mode: collaborationMode,
            capabilities: {
              web: true,
              filesystem: !!effectiveWorkspacePath,
              command: !!effectiveWorkspacePath,
              python: false,
            },
          },
          activeModelSelection,
        );

        setPendingRunId(response.run_id);

        // Store stream token for reconnection after page refresh
        localStorage.setItem(`stream_token:${response.run_id}`, response.stream_token);

        // Subscribe to agent SSE stream with auth token BEFORE navigate
        // to prevent loadConversation from opening a duplicate connection
        subscribedRunRef.current = response.run_id;
        subscribeAgent(response.run_id, 0, response.stream_token);

        const run: Run = {
          run_id: response.run_id,
          created_at: new Date().toISOString(),
          status: 'running',
          mode: 'agent',
          profile: 'agent',
          prompt: messageToSend,
          user_message: messageToSend,
          conversation_id: conversationId!,
          conversation_summary: conversation?.summary || '',
        };

        addRun(conversationId!, run);
        setEvents(response.run_id, []);
        setIsSubmitting(false);

        // Navigate AFTER subscription so the useEffect guard works
        if (needsNavigate) {
          navigate(`/conversations/${conversationId}`);
        }
      } else {
        // Chat mode: use regular conversation API
        const response = await createConversationRun(
          conversationId!,
          {
            message: messageToSend,
            image_attachments: attachmentsToSend,
          },
          activeModelSelection,
        );

        setPendingRunId(response.run_id);

        // CRITICAL: Subscribe to SSE IMMEDIATELY after getting run_id
        // This prevents race condition where events are emitted before frontend subscribes
        subscribe(response.run_id);

        const run: Run = {
          run_id: response.run_id,
          created_at: new Date().toISOString(),
          status: 'running',
          mode: 'system',
          profile: 'lmstudio',
          prompt: messageToSend,
          user_message: messageToSend,
          conversation_id: conversationId!,
          conversation_summary: conversation?.summary || '',
        };

        addRun(conversationId!, run);
        setEvents(response.run_id, []);
        setIsSubmitting(false);

        // Navigate AFTER subscription for chat mode too
        if (needsNavigate) {
          navigate(`/conversations/${conversationId}`);
        }
      }
    } catch (error: unknown) {
      console.error('Failed to create run:', error);
      const apiError = error as { status?: number; message?: string };
      const errMsg = error instanceof Error ? error.message : String(error);
      if (apiError.status === 429) {
        toast.error('Message limit reached. You\'ve used all your free messages.');
        refreshUsage();
      } else {
        toast.error(`Send failed: ${apiError.status || 'N/A'} - ${errMsg}`);
      }
      // Restore message on error
      setMessage(messageToSend);
      setImageAttachments(attachmentsToSend.map((attachment, index) => ({
        ...attachment,
        id: `${Date.now()}-${index}`,
      })));
      clearMentionState();
      setPendingMessage('');
      setPendingRunId(null);
      setPendingIsAgent(false);
      setIsSubmitting(false);
      scheduleComposerFocus();
      return;
    }

    scheduleComposerFocus();

    // Refresh usage after successful send
    refreshUsage();
  };

  const handlePlanImplementationStarted = useCallback((implementation: {
    run_id: string;
    stream_token?: string;
  }) => {
    if (!selectedConversationId) return;
    setCollaborationMode('default');
    setPendingRunId(implementation.run_id);
    if (implementation.stream_token) {
      localStorage.setItem(`stream_token:${implementation.run_id}`, implementation.stream_token);
    }
    subscribedRunRef.current = implementation.run_id;
    subscribeAgent(implementation.run_id, 0, implementation.stream_token);
    const run: Run = {
      run_id: implementation.run_id,
      created_at: new Date().toISOString(),
      status: 'running',
      mode: 'agent',
      profile: 'agent',
      prompt: 'Implement approved plan',
      user_message: 'Implement approved plan',
      conversation_id: selectedConversationId,
      conversation_summary: conversation?.summary || '',
    };
    addRun(selectedConversationId, run);
    setEvents(implementation.run_id, []);
  }, [addRun, conversation?.summary, selectedConversationId, setEvents, subscribeAgent]);

  // Handle stream completion - clear pending state.
  // Guard: only fire when we have a selected conversation (prevents false
  // triggers when selectedConversationId is still null during new-convo creation,
  // which causes activeRunId to be null → premature clear of isSubmitting).
  useEffect(() => {
    if (!selectedConversationId || !pendingRunId) return;
    if (activeRunId !== pendingRunId) {
      // The run we started is no longer active (completed or failed)
      setPendingMessage('');
      setPendingRunId(null);
      setPendingIsAgent(false);
      setIsSubmitting(false);
      setStoppingRunId(null);
      clearMentionState();
      setQueuedSteers([]);
      subscribedRunRef.current = null;
    }
  }, [clearMentionState, selectedConversationId, activeRunId, pendingRunId]);

  useEffect(() => {
    if (!stoppingRunId) return;
    const timeout = window.setTimeout(() => {
      void getAgentRunStatus(stoppingRunId)
        .then((status) => {
          if (!['cancelled', 'succeeded', 'failed', 'interrupted'].includes(status.status)) return;
          const terminalStatus = status.status as 'cancelled' | 'succeeded' | 'failed' | 'interrupted';
          updateRun(stoppingRunId, {
            status: terminalStatus,
            error_detail:
              terminalStatus === 'cancelled'
                ? 'Stopped by user'
                : terminalStatus === 'interrupted'
                  ? status.error_message || 'Run interrupted by server restart'
                  : undefined,
          });
          useStore.getState().updateAgentState(stoppingRunId, {
            isActive: false,
            agentState:
              terminalStatus === 'cancelled'
                ? 'cancelled'
                : terminalStatus === 'interrupted'
                  ? 'interrupted'
                : terminalStatus === 'succeeded'
                  ? 'complete'
                  : 'error',
          });
          localStorage.removeItem(`stream_token:${stoppingRunId}`);
          setStoppingRunId(null);
        })
        .catch(() => {
          setStoppingRunId(null);
        });
    }, 5000);
    return () => window.clearTimeout(timeout);
  }, [stoppingRunId, updateRun]);

  const handleStop = async () => {
    const runIdToStop = pendingRunId ?? activeRunId;
    if (!runIdToStop || stoppingRunId === runIdToStop) return;

    const runToStop = runs.find((run) => run.run_id === runIdToStop);
    const isAgentRun = pendingIsAgent || runToStop?.mode === 'agent';
    setStoppingRunId(runIdToStop);

    try {
      if (isAgentRun) {
        await cancelAgentRun(runIdToStop);
        updateRun(runIdToStop, {
          status: 'cancelled',
          error_detail: 'Stopped by user',
        });
        useStore.getState().updateAgentState(runIdToStop, {
          isActive: false,
          agentState: 'cancelled',
        });
        localStorage.removeItem(`stream_token:${runIdToStop}`);
      } else {
        await abortRun(runIdToStop);
        unsubscribe();
      }

      if (!isAgentRun && pendingMessage) {
        setMessage(pendingMessage);
      }
      if (pendingRunId === runIdToStop) {
        setPendingRunId(null);
        setPendingMessage('');
        setPendingIsAgent(false);
        setIsSubmitting(false);
      }
      clearMentionState();
      scheduleComposerFocus();
    } catch (error) {
      console.error('Failed to abort run:', error);
      toast.error('Failed to stop generation.');
    } finally {
      setStoppingRunId((current) => (current === runIdToStop ? null : current));
    }
  };

  const isGenerating = !!pendingRunId || !!activeRunId;
  const canSteerActiveRun = !!activeRunId && activeRun?.mode === 'agent';
  // Auto-resize textarea
  const resizeTextarea = useCallback(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    ta.style.height = Math.min(ta.scrollHeight, 200) + 'px';
  }, []);

  const handleMentionSelect = useCallback((entry: WorkspaceFileEntry) => {
    const mention = activeMention;
    if (!mention) return;
    const nextMessage = `${message.slice(0, mention.start)}${entry.path}${message.slice(mention.end)}`;
    const nextCursor = mention.start + entry.path.length;
    setMessage(nextMessage);
    setMentionOpen(false);
    setMentionError(null);
    setMentionResults([]);
    setActiveMention(null);
    requestAnimationFrame(() => {
      resizeTextarea();
      const textarea = textareaRef.current;
      if (!textarea) return;
      textarea.focus();
      textarea.setSelectionRange(nextCursor, nextCursor);
    });
  }, [activeMention, message, resizeTextarea]);

  const syncMentionState = useCallback((value: string, selectionStart: number | null) => {
    if (mode !== 'agent' || !effectiveWorkspacePath) {
      setActiveMention(null);
      setMentionOpen(false);
      setMentionError(null);
      return;
    }
    const mention = extractActiveMention(value, selectionStart ?? value.length);
    const mentionChanged = Boolean(
      mention
      && (
        !activeMention
        || mention.query !== activeMention.query
        || mention.start !== activeMention.start
        || mention.end !== activeMention.end
      )
    );
    setActiveMention((prev) => {
      if (!mention && !prev) return prev;
      if (!mention || !prev) return mention;
      if (mention.query === prev.query && mention.start === prev.start && mention.end === prev.end) return prev;
      return mention;
    });
    if (!mention) {
      setMentionOpen(false);
      setMentionLoading(false);
      setMentionError(null);
      return;
    }
    setMentionOpen(true);
    if (mentionChanged) {
      setMentionSelectedIndex(0);
      setMentionLoading(true);
      setMentionError(null);
    }
  }, [activeMention, effectiveWorkspacePath, mode]);

  const handleMessageChange = useCallback((e: ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value;
    verticalMoveColumnRef.current = null;
    // Enforce character limit
    if (value.length <= MAX_INPUT_CHARS) {
      setMessage(value);
      syncMentionState(value, e.target.selectionStart);
    }
    // Resize on next frame after state update
    requestAnimationFrame(resizeTextarea);
  }, [resizeTextarea, syncMentionState]);

  const removeImageAttachment = useCallback((id?: string) => {
    setImageAttachments((prev) => prev.filter((attachment) => attachment.id !== id));
  }, []);

  const handlePaste = useCallback((e: ClipboardEvent<HTMLTextAreaElement>) => {
    const files = Array.from(e.clipboardData.files).filter((file) => (
      file.type === 'image/png' || file.type === 'image/jpeg' || file.type === 'image/webp'
    ));
    if (!files.length) return;

    e.preventDefault();
    if (hasActiveRun) {
      toast.error('Image paste is only available before starting a run.');
      return;
    }
    if (!modelStatus?.supports_vision) {
      toast.error('Active model does not support images. Select a vision model.');
      return;
    }

    const remaining = MAX_IMAGE_ATTACHMENTS - imageAttachments.length;
    if (remaining <= 0) {
      toast.error(`You can attach up to ${MAX_IMAGE_ATTACHMENTS} images.`);
      return;
    }

    files.slice(0, remaining).forEach((file) => {
      if (file.size > MAX_IMAGE_BYTES) {
        toast.error(`${file.name || 'image'} is larger than 20MB.`);
        return;
      }
      const reader = new FileReader();
      reader.onload = () => {
        const dataUrl = String(reader.result || '');
        setImageAttachments((prev) => [
          ...prev,
          {
            id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
            name: file.name || `screenshot-${prev.length + 1}.${file.type.split('/')[1] || 'png'}`,
            mime_type: file.type,
            data_url: dataUrl,
          },
        ].slice(0, MAX_IMAGE_ATTACHMENTS));
      };
      reader.readAsDataURL(file);
    });
  }, [hasActiveRun, imageAttachments.length, modelStatus?.supports_vision]);

  const handleTextareaSelection = useCallback(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    verticalMoveColumnRef.current = null;
    syncMentionState(textarea.value, textarea.selectionStart);
  }, [syncMentionState]);

  const syncTextareaState = useCallback((textarea: HTMLTextAreaElement) => {
    setMessage(textarea.value);
    syncMentionState(textarea.value, textarea.selectionStart);
    requestAnimationFrame(resizeTextarea);
  }, [resizeTextarea, syncMentionState]);

  const handleMentionKeyDown = useCallback((e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (mentionOpen) {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setMentionSelectedIndex((prev) => (
          mentionResults.length ? (prev + 1) % mentionResults.length : 0
        ));
        return true;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        setMentionSelectedIndex((prev) => (
          mentionResults.length ? (prev - 1 + mentionResults.length) % mentionResults.length : 0
        ));
        return true;
      }
      if (e.key === 'Enter' && !e.metaKey && !e.ctrlKey) {
        const entry = mentionResults[mentionSelectedIndex];
        if (entry) {
          e.preventDefault();
          handleMentionSelect(entry);
          return true;
        }
      }
      if (e.key === 'Escape') {
        e.preventDefault();
        setMentionOpen(false);
        return true;
      }
    }
    return false;
  }, [handleMentionSelect, mentionOpen, mentionResults, mentionSelectedIndex]);

  const handleComposerCommandKeyDown = useCallback((e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      handleSubmit();
      return true;
    }
    if (e.key === '1' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      setMode('agent');
      return true;
    }
    if (e.key === '2' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      setMode('chat');
      return true;
    }
    return false;
  }, [handleSubmit]);

  const handleComposerEditingShortcut = useCallback((e: KeyboardEvent<HTMLTextAreaElement>) => {
    const textarea = e.currentTarget;
    if (textarea.disabled || e.nativeEvent.isComposing) return false;

    const isMac = isApplePlatform();
    const key = e.key;
    const normalizedKey = key.length === 1 ? key.toLowerCase() : key;
    const hasModifiers = e.metaKey || e.altKey || e.shiftKey || e.ctrlKey;
    if (!hasModifiers) {
      verticalMoveColumnRef.current = null;
      return false;
    }

    const text = textarea.value;
    const selectionStart = textarea.selectionStart;
    const selectionEnd = textarea.selectionEnd;
    const selectionCollapsed = selectionStart === selectionEnd;
    const collapseTo = (position: number) => {
      textarea.setSelectionRange(position, position);
      verticalMoveColumnRef.current = null;
      syncMentionState(textarea.value, textarea.selectionStart);
    };

    if (e.ctrlKey && !e.metaKey && !e.altKey && !e.shiftKey) {
      if (!isMac && normalizedKey === 'f') {
        return false;
      }

      switch (normalizedKey) {
        case 'a':
          e.preventDefault();
          collapseTo(getLineStart(text, selectionStart));
          return true;
        case 'e':
          e.preventDefault();
          collapseTo(getLineEnd(text, selectionEnd));
          return true;
        case 'b':
          e.preventDefault();
          collapseTo(selectionCollapsed ? Math.max(0, selectionStart - 1) : selectionStart);
          return true;
        case 'f':
          e.preventDefault();
          collapseTo(selectionCollapsed ? Math.min(text.length, selectionEnd + 1) : selectionEnd);
          return true;
        case 'p': {
          e.preventDefault();
          const nextPosition = moveVertical(text, selectionStart, -1, verticalMoveColumnRef.current);
          verticalMoveColumnRef.current = selectionStart - getLineStart(text, selectionStart);
          textarea.setSelectionRange(nextPosition, nextPosition);
          syncMentionState(textarea.value, textarea.selectionStart);
          return true;
        }
        case 'n': {
          e.preventDefault();
          const nextPosition = moveVertical(text, selectionEnd, 1, verticalMoveColumnRef.current);
          verticalMoveColumnRef.current = selectionEnd - getLineStart(text, selectionEnd);
          textarea.setSelectionRange(nextPosition, nextPosition);
          syncMentionState(textarea.value, textarea.selectionStart);
          return true;
        }
        case 'k':
          e.preventDefault();
          if (hasTextSelection(textarea)) {
            replaceTextareaRange(textarea, '', selectionStart, selectionEnd, 'start');
          } else {
            replaceTextareaRange(textarea, '', selectionStart, getLineEnd(text, selectionStart), 'start');
          }
          verticalMoveColumnRef.current = null;
          syncTextareaState(textarea);
          return true;
        case 'u':
          e.preventDefault();
          if (hasTextSelection(textarea)) {
            replaceTextareaRange(textarea, '', selectionStart, selectionEnd, 'start');
          } else {
            replaceTextareaRange(textarea, '', getLineStart(text, selectionStart), selectionStart, 'start');
          }
          verticalMoveColumnRef.current = null;
          syncTextareaState(textarea);
          return true;
        case 'w':
          e.preventDefault();
          if (hasTextSelection(textarea)) {
            replaceTextareaRange(textarea, '', selectionStart, selectionEnd, 'start');
          } else {
            replaceTextareaRange(textarea, '', moveWordLeft(text, selectionStart), selectionStart, 'start');
          }
          verticalMoveColumnRef.current = null;
          syncTextareaState(textarea);
          return true;
        default:
          verticalMoveColumnRef.current = null;
          return false;
      }
    }

    if (isMac && e.altKey && !e.metaKey && !e.ctrlKey && !e.shiftKey) {
      if (normalizedKey === 'b') {
        e.preventDefault();
        collapseTo(moveWordLeft(text, selectionStart));
        return true;
      }
      if (normalizedKey === 'f') {
        e.preventDefault();
        collapseTo(moveWordRight(text, selectionEnd));
        return true;
      }
      if (normalizedKey === 'Backspace') {
        e.preventDefault();
        if (hasTextSelection(textarea)) {
          replaceTextareaRange(textarea, '', selectionStart, selectionEnd, 'start');
        } else {
          replaceTextareaRange(textarea, '', moveWordLeft(text, selectionStart), selectionStart, 'start');
        }
        verticalMoveColumnRef.current = null;
        syncTextareaState(textarea);
        return true;
      }
    }

    if (isMac && e.metaKey && !e.ctrlKey && !e.altKey && !e.shiftKey && normalizedKey === 'Backspace') {
      e.preventDefault();
      if (hasTextSelection(textarea)) {
        replaceTextareaRange(textarea, '', selectionStart, selectionEnd, 'start');
      } else {
        replaceTextareaRange(textarea, '', getLineStart(text, selectionStart), selectionStart, 'start');
      }
      verticalMoveColumnRef.current = null;
      syncTextareaState(textarea);
      return true;
    }

    verticalMoveColumnRef.current = null;
    return false;
  }, [syncMentionState, syncTextareaState]);

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (handleMentionKeyDown(e)) return;
    if (handleComposerCommandKeyDown(e)) return;
    handleComposerEditingShortcut(e);
  };

  const openWorkspacePickerForNewConversation = useCallback(async () => {
    if (hasActiveRun) return;
    if (isLocalDesktopApp()) {
      const selectedPath = await openNativeWorkspacePicker();
      const normalized = selectedPath?.trim();
      if (normalized) {
        beginWorkspaceDraft(normalized);
        navigate('/conversations', { replace: true });
      }
      return;
    }
    setWorkspacePickerMode('new-conversation');
    setWorkspacePickerOpen(true);
  }, [
    beginWorkspaceDraft,
    hasActiveRun,
    navigate,
  ]);

  const startWorkspaceDraftConversation = useCallback((workspacePath: string) => {
    if (hasActiveRun) return;
    const normalized = workspacePath.trim();
    if (!normalized) {
      openWorkspacePickerForNewConversation();
      return;
    }
    beginWorkspaceDraft(normalized);
    navigate('/conversations', { replace: true });
  }, [
    beginWorkspaceDraft,
    hasActiveRun,
    navigate,
    openWorkspacePickerForNewConversation,
  ]);

  const clearPendingWorkspaceShortcut = useCallback(() => {
    pendingWorkspaceShortcutRef.current = null;
    if (pendingWorkspaceShortcutTimeoutRef.current !== null) {
      window.clearTimeout(pendingWorkspaceShortcutTimeoutRef.current);
      pendingWorkspaceShortcutTimeoutRef.current = null;
    }
  }, []);

  const armPendingWorkspaceShortcut = useCallback((action: 'workspace-new' | 'workspace-picker') => {
    pendingWorkspaceShortcutRef.current = action;
    if (pendingWorkspaceShortcutTimeoutRef.current !== null) {
      window.clearTimeout(pendingWorkspaceShortcutTimeoutRef.current);
    }
    pendingWorkspaceShortcutTimeoutRef.current = window.setTimeout(() => {
      pendingWorkspaceShortcutRef.current = null;
      pendingWorkspaceShortcutTimeoutRef.current = null;
    }, 1500);
  }, []);

  useEffect(() => {
    const handleWindowKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.defaultPrevented || event.isComposing) return;
      const lowerKey = event.key.toLowerCase();

      if (
        lowerKey === 'escape'
        && !event.metaKey
        && !event.ctrlKey
        && !event.altKey
        && !event.shiftKey
        && !event.repeat
      ) {
        if (
          !mentionOpen
          && !anyDialogOpen
          && !hasActiveRun
          && !!selectedConversationId
          && !!lockedWorkspacePath
        ) {
          const now = Date.now();
          if (now - lastEscapeAtRef.current <= 800) {
            event.preventDefault();
            lastEscapeAtRef.current = 0;
            void openRewindPicker();
            return;
          }
          lastEscapeAtRef.current = now;
        } else {
          lastEscapeAtRef.current = 0;
        }
      } else if (lastEscapeAtRef.current !== 0) {
        lastEscapeAtRef.current = 0;
      }

      const pendingWorkspaceShortcut = pendingWorkspaceShortcutRef.current;
      if (pendingWorkspaceShortcut) {
        if (event.metaKey || event.ctrlKey || event.altKey) {
          clearPendingWorkspaceShortcut();
          return;
        }
        if (lowerKey === 'escape') {
          clearPendingWorkspaceShortcut();
          return;
        }
        if (lowerKey === 'n') {
          event.preventDefault();
          clearPendingWorkspaceShortcut();
          if (hasActiveRun) return;
          if (effectiveWorkspacePath) {
            startWorkspaceDraftConversation(effectiveWorkspacePath);
          } else {
            openWorkspacePickerForNewConversation();
          }
          return;
        }
        if (lowerKey === 'w') {
          event.preventDefault();
          clearPendingWorkspaceShortcut();
          openWorkspacePickerForNewConversation();
          return;
        }
        clearPendingWorkspaceShortcut();
      }

      if ((event.metaKey || event.ctrlKey) && !event.shiftKey && !event.altKey && lowerKey === 'k') {
        if (isTextInputElement(event.target)) return;
        event.preventDefault();
        armPendingWorkspaceShortcut('workspace-new');
        return;
      }

      if (event.key !== '/' || event.metaKey || event.ctrlKey || event.altKey || event.shiftKey) return;
      if (isTextInputElement(event.target)) return;
      const textarea = textareaRef.current;
      if (!textarea || textarea.disabled) return;
      event.preventDefault();
      focusComposer();
    };

    window.addEventListener('keydown', handleWindowKeyDown);
    return () => window.removeEventListener('keydown', handleWindowKeyDown);
  }, [
    anyDialogOpen,
    armPendingWorkspaceShortcut,
    clearPendingWorkspaceShortcut,
    effectiveWorkspacePath,
    focusComposer,
    hasActiveRun,
    lockedWorkspacePath,
    mentionOpen,
    openRewindPicker,
    selectedConversationId,
    openWorkspacePickerForNewConversation,
    startWorkspaceDraftConversation,
  ]);

  useEffect(() => {
    return () => {
      if (composerFocusRafRef.current !== null) {
        cancelAnimationFrame(composerFocusRafRef.current);
      }
      if (pendingWorkspaceShortcutTimeoutRef.current !== null) {
        window.clearTimeout(pendingWorkspaceShortcutTimeoutRef.current);
      }
      lastEscapeAtRef.current = 0;
    };
  }, []);

  // Reset textarea height when message is cleared (after submit)
  useEffect(() => {
    if (!message && textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  }, [message]);

  useEffect(() => {
    if (mode !== 'agent' || !effectiveWorkspacePath || !activeMention) {
      clearMentionState();
      return;
    }

    let cancelled = false;
    setMentionLoading(true);
    const timer = window.setTimeout(() => {
      searchWorkspaceFiles(effectiveWorkspacePath, activeMention.query, MENTION_RESULT_LIMIT)
        .then((response) => {
          if (cancelled) return;
          setMentionResults(response.entries);
          setMentionSelectedIndex(0);
          setMentionError(null);
          setMentionOpen(true);
        })
        .catch((error: unknown) => {
          if (cancelled) return;
          setMentionResults([]);
          setMentionError((error as { message?: string })?.message || 'file search failed');
          setMentionOpen(true);
        })
        .finally(() => {
          if (!cancelled) {
            setMentionLoading(false);
          }
        });
    }, 120);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [activeMention, clearMentionState, effectiveWorkspacePath, mode]);

  const rewindDialog = (
    <Dialog open={rewindOpen} onOpenChange={handleRewindOpenChange}>
      <DialogContent className="max-w-xl border-zinc-800 bg-zinc-950 text-zinc-100">
        <DialogHeader>
          <DialogTitle className="font-mono text-sm text-zinc-100">rewind conversation</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <p className="font-mono text-[12px] leading-6 text-zinc-500">
            Rewind the active branch to before a prior prompt, then restore that prompt into the composer.
          </p>
          <div className="max-h-[22rem] space-y-2 overflow-y-auto pr-1">
            {rewindLoading ? (
              <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 px-3 py-3 font-mono text-[12px] text-zinc-500">
                loading…
              </div>
            ) : rewindCheckpoints.length === 0 ? (
              <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 px-3 py-3 font-mono text-[12px] text-zinc-500">
                No rewind points available for this conversation yet.
              </div>
            ) : (
              rewindCheckpoints.map((checkpoint) => {
                const selected = checkpoint.run_id === rewindSelectedRunId;
                return (
                  <button
                    key={checkpoint.run_id}
                    type="button"
                    onClick={() => setRewindSelectedRunId(checkpoint.run_id)}
                    className={cn(
                      'w-full rounded-xl border px-3 py-3 text-left ui-transition',
                      selected
                        ? 'border-cyan-500/35 bg-cyan-500/[0.08] text-zinc-100'
                        : 'border-zinc-800 bg-zinc-900/60 text-zinc-300 hover:border-zinc-700 hover:bg-zinc-900'
                    )}
                  >
                    <div className="truncate font-mono text-[12px] leading-6">
                      {checkpoint.user_message}
                    </div>
                    <div className="mt-1 font-mono text-[11px] text-zinc-500">
                      {formatRelativeTime(checkpoint.created_at)}
                    </div>
                  </button>
                );
              })
            )}
          </div>
          <div className="flex items-center justify-end gap-2 font-mono text-[12px]">
            <button
              type="button"
              onClick={() => setRewindOpen(false)}
              className="rounded-lg border border-zinc-800 px-3 py-2 text-zinc-400 hover:border-zinc-700 hover:text-zinc-200"
              disabled={rewindSubmitting}
            >
              cancel
            </button>
            <button
              type="button"
              onClick={() => void handleRewindRestore()}
              disabled={!rewindSelectedRunId || rewindLoading || rewindSubmitting}
              className={cn(
                'rounded-lg border px-3 py-2 ui-transition',
                !rewindSelectedRunId || rewindLoading || rewindSubmitting
                  ? 'cursor-not-allowed border-zinc-800 text-zinc-600'
                  : 'border-cyan-500/35 text-cyan-100 hover:bg-cyan-500/[0.08]'
              )}
            >
              {rewindSubmitting ? 'rewinding…' : 'rewind'}
            </button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );

  const imageAttachmentsRow =
    imageAttachments.length > 0 ? (
      <div className="flex flex-wrap gap-1.5 px-1 text-[12px]">
        {imageAttachments.map((attachment, index) => (
          <button
            key={attachment.id || index}
            type="button"
            onClick={() => removeImageAttachment(attachment.id)}
            className="rounded-md border border-white/10 bg-white/[0.04] px-2 py-0.5 text-zinc-400 hover:border-cyan-400/25 hover:text-zinc-200"
            title="Remove image"
          >
            Image {index + 1} ×
          </button>
        ))}
      </div>
    ) : null;

  const terminalAvailable = localDesktop && mode === 'agent';
  const activeTerminalState = selectedConversationId ? terminalState : draftTerminalState;
  const terminalOpen = terminalAvailable && !!activeTerminalState?.isOpen;

  const handleTerminalToggle = useCallback(() => {
    if (mode !== 'agent' || !localDesktop) return;
    if (!effectiveWorkspacePath) {
      toast.error(
        selectedConversationId
          ? 'Create or open a workspace conversation first'
          : 'Select a workspace first'
      );
      if (!selectedConversationId) {
        setWorkspacePickerOpen(true);
      }
      return;
    }
    const terminalKey = selectedConversationId || DRAFT_TERMINAL_CONVERSATION_ID;
    updateTerminalState(terminalKey, {
      isOpen: !activeTerminalState?.isOpen,
    });
  }, [
    activeTerminalState?.isOpen,
    effectiveWorkspacePath,
    localDesktop,
    mode,
    selectedConversationId,
    updateTerminalState,
  ]);

  const agentOptionsRow = (
    <AgentComposerOptions
      mode={mode}
      isWorkspaceLocked={isWorkspaceLocked}
      hasConversationWorkspace={hasConversationWorkspace}
      effectiveWorkspacePath={effectiveWorkspacePath}
      draftWorkspacePath={draftWorkspacePath}
      onDraftWorkspacePathChange={setDraftWorkspacePath}
      onBrowseWorkspace={() => {
        setWorkspacePickerMode('draft');
        handleOpenWorkspacePicker();
      }}
      permissionPolicy={permissionPolicy}
      onPermissionPolicyChange={setPermissionPolicy}
      collaborationMode={collaborationMode}
      onCollaborationModeChange={setCollaborationMode}
    />
  );

  const desktopWorkspaceLabel = useMemo(() => {
    if (mode !== 'agent') return null;
    const path = isWorkspaceLocked ? effectiveWorkspacePath : draftWorkspacePath;
    const trimmed = path.trim();
    if (!trimmed) return 'No folder';
    return trimmed.split('/').filter(Boolean).pop() || trimmed;
  }, [mode, isWorkspaceLocked, effectiveWorkspacePath, draftWorkspacePath]);

  const desktopWorkspaceTitle = useMemo(() => {
    if (mode !== 'agent') return undefined;
    const path = isWorkspaceLocked ? effectiveWorkspacePath : draftWorkspacePath;
    return path.trim() || undefined;
  }, [mode, isWorkspaceLocked, effectiveWorkspacePath, draftWorkspacePath]);

  const desktopComposerControls = (
    <DesktopComposerControls
      mode={mode}
      modelStatus={modelStatus}
      onModelClick={() => setModelPickerOpen(true)}
      onReasoningClick={() => setReasoningSettingsOpen(true)}
      showTerminal={terminalAvailable}
      terminalOpen={terminalOpen}
      onTerminalClick={handleTerminalToggle}
      isWorkspaceLocked={isWorkspaceLocked}
      hasConversationWorkspace={hasConversationWorkspace}
      effectiveWorkspacePath={effectiveWorkspacePath}
      draftWorkspacePath={draftWorkspacePath}
      onDraftWorkspacePathChange={setDraftWorkspacePath}
      onBrowseWorkspace={() => {
        setWorkspacePickerMode('draft');
        handleOpenWorkspacePicker();
      }}
      permissionPolicy={permissionPolicy}
      onPermissionPolicyChange={setPermissionPolicy}
      collaborationMode={collaborationMode}
      onCollaborationModeChange={setCollaborationMode}
    />
  );

  const agentContextStatsRow = (
    <AgentContextFooter
      show={showComposerContextStats}
      composerContextUtilizationPct={composerContextUtilizationPct ?? null}
      composerPromptTokens={composerPromptTokens ?? null}
      composerContextWindow={composerContextWindow ?? null}
      conversationInputTokens={conversationTokenAndCostTotals.inputTokens}
      conversationOutputTokens={conversationTokenAndCostTotals.outputTokens}
      conversationInputCost={conversationTokenAndCostTotals.inputCost}
      conversationOutputCost={conversationTokenAndCostTotals.outputCost}
      formatContextTokens={formatContextTokens}
      formatCost={formatAgentCost}
    />
  );

  const mentionPickerNode = (
    <MentionPicker
      open={mentionOpen}
      loading={mentionLoading}
      error={mentionError}
      entries={mentionResults}
      selectedIndex={mentionSelectedIndex}
      onSelect={handleMentionSelect}
      desktop={localDesktop}
    />
  );

  const limitHintNode = hasLimit ? (
    <p
      className={cn(
        'text-[11px]',
        atLimit ? 'text-red-400/80' : usage.remaining <= 3 ? 'text-amber-400' : 'text-zinc-600'
      )}
    >
      {atLimit ? 'No messages left' : `${usage.remaining} messages left`}
    </p>
  ) : null;

  const sharedComposerProps = {
    textareaRef,
    message,
    atLimit,
    isSubmitting,
    isGenerating,
    canSteerActiveRun,
    hasActiveRun,
    stoppingRunId,
    messageLength: message.length,
    maxLength: MAX_INPUT_CHARS,
    onChange: handleMessageChange,
    onPaste: handlePaste,
    onKeyDown: handleKeyDown,
    onSelect: handleTextareaSelection,
    onClick: handleTextareaSelection,
    onSubmit: handleSubmit,
    onStop: handleStop,
    mentionPicker: mentionPickerNode,
    attachmentsRow: imageAttachmentsRow,
  };
  const handleEmptyDesktopDrag = (event: ReactMouseEvent<HTMLDivElement>) => {
    if (localDesktop) {
      void startWindowDrag(event);
    }
  };

  if (!conversation && runs.length === 0) {
    return (
      <div className="flex h-full flex-col">
        {localDesktop ? (
          <DesktopChrome title="New conversation" mergeTitlebar />
        ) : (
          <ConversationToolbar
            conversationTitle="New conversation"
            mode={mode}
            onModeChange={setMode}
            modelStatus={modelStatus}
            onModelClick={() => setModelPickerOpen(true)}
            onReasoningClick={() => setReasoningSettingsOpen(true)}
          />
        )}
        <ModelPicker
          open={modelPickerOpen}
          onOpenChange={setModelPickerOpen}
          modelStatus={modelStatus}
          onModelStatusChange={handleModelStatusChange}
          activeSelection={activeModelSelection}
        />
        <ReasoningSettingsDialog
          open={reasoningSettingsOpen}
          onOpenChange={setReasoningSettingsOpen}
          settingsResponse={reasoningSettings}
          draft={reasoningDraft}
          onDraftChange={setReasoningDraft}
          onSave={handleSaveReasoningSettings}
          saving={reasoningSaving}
        />
        <WorkspacePickerDialog
          open={workspacePickerOpen}
          onOpenChange={setWorkspacePickerOpen}
          value={draftWorkspacePath}
          onSelect={(workspacePath) => {
            if (workspacePickerMode === 'new-conversation') {
              startWorkspaceDraftConversation(workspacePath);
              return;
            }
            rememberWorkspacePath(workspacePath);
            setDraftWorkspacePath(workspacePath);
          }}
        />
        <div
          data-tauri-drag-region={localDesktop ? true : undefined}
          onMouseDown={handleEmptyDesktopDrag}
          className={cn(
            'flex min-h-0 flex-1 flex-col overflow-y-auto',
            localDesktop && 'desktop-empty-drag-surface'
          )}
        >
          <EmptyState
            mode={mode}
            workspacePath={effectiveWorkspacePath}
            modelStatus={modelStatus}
            onSuggestionClick={(text) => setMessage(text)}
          />
        </div>
        {localDesktop ? (
          <DesktopInputDock
            mode={mode}
            onModeChange={setMode}
            workspaceLabel={desktopWorkspaceLabel}
            workspaceTitle={desktopWorkspaceTitle}
            queuedSteers={[]}
            activeAgentRun={null}
            activeAgentHudState={null}
            showAgentHud={false}
            controlsRow={desktopComposerControls}
            placeholder={
              mode === 'agent' ? 'Ask the agent…' : 'Ask a question…'
            }
            {...sharedComposerProps}
            metaRow={agentContextStatsRow}
            limitHint={limitHintNode}
            disabled={isSubmitting || atLimit || (hasActiveRun && !canSteerActiveRun)}
          />
        ) : (
          <Composer
            {...sharedComposerProps}
            placeholder={
              mode === 'agent' ? 'Ask the coding agent...' : 'Ask a question...'
            }
            disabled={isSubmitting || atLimit || (hasActiveRun && !canSteerActiveRun)}
            agentOptionsRow={agentOptionsRow}
            contextStatsRow={agentContextStatsRow}
          />
        )}
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      {localDesktop ? (
        <DesktopChrome
          title={conversation?.title || 'Conversation'}
          mergeTitlebar
        />
      ) : (
        <ConversationToolbar
          conversationTitle={conversation?.title || 'Conversation'}
          mode={mode}
          onModeChange={setMode}
          modelStatus={modelStatus}
          onModelClick={() => setModelPickerOpen(true)}
          onReasoningClick={() => setReasoningSettingsOpen(true)}
        />
      )}
      <ModelPicker
        open={modelPickerOpen}
        onOpenChange={setModelPickerOpen}
        modelStatus={modelStatus}
        onModelStatusChange={handleModelStatusChange}
        activeSelection={activeModelSelection}
      />
      <ReasoningSettingsDialog
        open={reasoningSettingsOpen}
        onOpenChange={setReasoningSettingsOpen}
        settingsResponse={reasoningSettings}
        draft={reasoningDraft}
        onDraftChange={setReasoningDraft}
        onSave={handleSaveReasoningSettings}
        saving={reasoningSaving}
      />
      <WorkspacePickerDialog
        open={workspacePickerOpen}
        onOpenChange={setWorkspacePickerOpen}
        value={draftWorkspacePath}
        onSelect={(workspacePath) => {
          if (workspacePickerMode === 'new-conversation') {
            startWorkspaceDraftConversation(workspacePath);
            return;
          }
          rememberWorkspacePath(workspacePath);
          setDraftWorkspacePath(workspacePath);
        }}
      />
      {rewindDialog}

      <div className="relative flex min-h-0 flex-1 flex-col">
        <div className="flex-1 overflow-y-auto px-4 py-6" ref={scrollRef}>
          <div className="desktop-thread-column w-full">
            {isLoadingSelectedConversation && runs.length === 0 ? (
              <div className="flex min-h-[45vh] items-center justify-center">
                <div className="flex items-center gap-3 rounded-full border border-white/[0.08] bg-white/[0.035] px-4 py-2 text-[13px] text-zinc-400">
                  <span className="h-2 w-2 animate-pulse rounded-full bg-cyan-300/80" />
                  Loading conversation…
                </div>
              </div>
            ) : runs.length === 0 ? (
              <div className="flex min-h-[45vh] items-center justify-center text-[13px] text-zinc-500">
                No messages in this conversation.
              </div>
            ) : (
              <VirtualizedConversationRunList
                runs={runs}
                scrollContainerRef={scrollRef}
                renderRun={renderRunCard}
              />
            )}
          </div>
        </div>

        <ScrollToBottom
          scrollRef={scrollRef}
          isStreaming={!!activeRunId}
          className={cn(
            'left-1/2 -translate-x-1/2',
            localDesktop ? 'bottom-[calc(var(--desktop-dock-height)+1rem)]' : (
              activeAgentHudState?.isActive ? 'bottom-44' : 'bottom-32'
            )
          )}
        />

        {!localDesktop && activeAgentRun && activeAgentHudState?.isActive ? (
          <AgentLiveHUD
            runId={activeAgentRun.run_id}
            runCreatedAt={activeAgentRun.created_at}
            agentState={activeAgentHudState}
            onImplementationStarted={handlePlanImplementationStarted}
          />
        ) : null}

        <div className="flex-shrink-0">
          {localDesktop ? (
            <DesktopInputDock
              mode={mode}
              onModeChange={setMode}
              workspaceLabel={desktopWorkspaceLabel}
              workspaceTitle={desktopWorkspaceTitle}
              queuedSteers={queuedSteers}
              activeAgentRun={activeAgentRun}
              activeAgentHudState={activeAgentHudState ?? null}
              showAgentHud={!!activeAgentHudState?.isActive}
              onImplementationStarted={handlePlanImplementationStarted}
              controlsRow={desktopComposerControls}
              placeholder={
                atLimit
                  ? 'Message limit reached'
                  : hasActiveRun
                    ? 'Steer the agent…'
                    : mode === 'agent'
                      ? 'Ask the agent…'
                      : 'Ask a follow-up question…'
              }
              {...sharedComposerProps}
              metaRow={agentContextStatsRow}
              limitHint={limitHintNode}
              disabled={isSubmitting || atLimit}
            />
          ) : (
            <>
              {queuedSteers.length > 0 ? (
                <div className="mb-2 flex flex-wrap gap-1.5 px-4">
                  {queuedSteers.map((msg, i) => (
                    <span
                      key={i}
                      className="inline-flex items-center gap-1 rounded-md border border-amber-500/20 bg-amber-500/[0.08] px-2 py-1 text-[12px] text-amber-200/90"
                    >
                      <span className="text-amber-500/60">Queued:</span>{' '}
                      {msg.length > 40 ? `${msg.slice(0, 40)}…` : msg}
                    </span>
                  ))}
                </div>
              ) : null}
              <Composer
                {...sharedComposerProps}
                placeholder={
                  atLimit
                    ? 'Message limit reached'
                    : hasActiveRun
                      ? 'Steer the agent...'
                      : mode === 'agent'
                        ? 'Ask the coding agent...'
                        : 'Ask a follow-up question...'
                }
                disabled={isSubmitting || atLimit}
                agentOptionsRow={
                  <>
                    {agentOptionsRow}
                    {limitHintNode}
                  </>
                }
                contextStatsRow={agentContextStatsRow}
              />
            </>
          )}
        </div>
      </div>
    </div>
  );
}
