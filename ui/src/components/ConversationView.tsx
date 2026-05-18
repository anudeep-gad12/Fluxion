// Conversation view - simple chat interface

import { useEffect, useMemo, useRef, useState, useCallback, memo } from 'react';
import type { KeyboardEvent, ChangeEvent, ClipboardEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { AnswerMarkdown, extractAnswer } from '@/components/AnswerMarkdown';
import { ThinkingPanel } from '@/components/ThinkingPanel';
import { AgentRunMessage } from '@/components/AgentRunMessage';
import { AgentLiveHUD } from '@/components/AgentLiveHUD';
import { MessageActions } from '@/components/MessageActions';
import { ShimmerSkeleton, ThinkingTimer } from '@/components/StreamingIndicator';
import { ScrollToBottom } from '@/components/ScrollToBottom';
import { IntegratedTerminal } from '@/components/IntegratedTerminal';
import { WorkspacePickerDialog } from '@/components/WorkspacePickerDialog';
import { VirtualizedConversationRunList } from '@/components/VirtualizedConversationRunList';
import {
  createConversation,
  createConversationRun,
  getConversation,
  abortRun,
  createAgentRun,
  cancelAgentRun,
  listLocalModels,
  startLocalModel,
  stopLocalModel,
  getModelStatus,
  getReasoningSettings,
  listRegistryModels,
  listProviderKeys,
  saveProviderKey,
  clearProviderKey,
  selectModel,
  updateReasoningSettings,
  getUsage,
  steerAgentRun,
  searchWorkspaceFiles,
  listConversationRewindCheckpoints,
  rewindConversation,
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
import {
  Dialog,
  DialogHeader,
  DialogTitle,
  DialogContent,
} from '@/components/ui/dialog';
import { useConversationRuns, useSelectedConversation, useStore, useHasActiveRun, useConversationTerminal } from '@/hooks/useStore';
import { useSSE } from '@/hooks/useSSE';
import { useAgentSSE } from '@/hooks/useAgentSSE';
import { useAgentRunDetails } from '@/hooks/useAgentRunDetails';
import { formatAgentCost, formatAgentTokens } from '@/lib/agentLiveState';
import { cn, formatRelativeTime } from '@/lib/utils';
import type { Run, Conversation, ImageAttachment } from '@/types';

/** Maximum characters allowed in the input textarea (~2000 tokens) */
const MAX_INPUT_CHARS = 8000;
const MENTION_RESULT_LIMIT = 20;
const MAX_IMAGE_ATTACHMENTS = 8;
const MAX_IMAGE_BYTES = 20 * 1024 * 1024;

/** Mode: 'chat' for regular conversation, 'agent' for agent */
type ChatMode = 'chat' | 'agent';

function formatRunStatusLabel(run: Run): string {
  if (run.status === 'succeeded') return 'done';
  if (run.status === 'failed') return 'failed';
  return 'running';
}

function getRunFooterMetrics(run: Run): string[] {
  const metrics: string[] = [];

  if (typeof run.usage?.total_tokens === 'number' && run.usage.total_tokens > 0) {
    metrics.push(`${formatAgentTokens(run.usage.total_tokens)} tok`);
  }
  if (run.usage && (
    typeof run.usage.input_tokens === 'number'
    || typeof run.usage.output_tokens === 'number'
  )) {
    metrics.push(
      `in ${formatAgentTokens(run.usage.input_tokens ?? 0)} / out ${formatAgentTokens(run.usage.output_tokens ?? 0)}`
    );
  }
  if (run.cost && typeof run.cost.total_cost === 'number' && run.usage?.total_tokens) {
    metrics.push(`est ${formatAgentCost(run.cost.total_cost)}`);
  } else if (run.usage) {
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

function isApplePlatform(): boolean {
  if (typeof navigator === 'undefined') return false;
  return /(Mac|iPhone|iPad|iPod)/i.test(navigator.platform || navigator.userAgent);
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

/** Model picker component shown in the status bar */
function ModelPicker({
  open,
  onOpenChange,
  modelStatus,
  onModelStatusChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  modelStatus: ModelStatus | null;
  onModelStatusChange: (status: ModelStatus) => void;
}) {
  const [registryData, setRegistryData] = useState<RegistryModelsResponse | null>(null);
  const [localModels, setLocalModels] = useState<LocalModel[]>([]);
  const [providerKeys, setProviderKeys] = useState<ProviderKeyStatus[]>([]);
  const [providerKeyDrafts, setProviderKeyDrafts] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [switching, setSwitching] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const pickerLoadSeqRef = useRef(0);

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
      return;
    }
    setLoading(true);
    setError(null);
    void refreshPickerData();
  }, [open, refreshPickerData]);

  const handleSelectRegistry = async (modelId: string) => {
    setSwitching(modelId);
    setError(null);
    try {
      if (modelStatus?.provider === 'local') {
        await stopLocalModel();
      }
      const selected = await selectModel(modelId);
      onModelStatusChange({
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
      });
      onOpenChange(false);
      void getModelStatus().then(onModelStatusChange).catch(() => {});
    } catch {
      setError('Failed to switch model');
    } finally {
      setSwitching(null);
    }
  };

  const handleSelectLocal = async (model: LocalModel) => {
    setSwitching(model.path);
    setError(null);
    try {
      const started = await startLocalModel(model.path);
      onModelStatusChange({
        provider: 'local',
        model_name: started.model_name,
        base_url: modelStatus?.base_url ?? null,
        local_running: true,
        context_window: modelStatus?.context_window ?? 0,
        max_output_tokens: modelStatus?.max_output_tokens ?? 0,
        effective_input_budget: modelStatus?.effective_input_budget ?? 0,
        supports_tools: modelStatus?.supports_tools ?? true,
        supports_reasoning: modelStatus?.supports_reasoning ?? false,
        supports_vision: modelStatus?.supports_vision ?? false,
        provider_family: 'local',
        reasoning_capabilities: null,
        source: 'local',
      });
      onOpenChange(false);
      void getModelStatus().then(onModelStatusChange).catch(() => {});
    } catch {
      setError(`Failed to start model. Check logs/${model.model_type === 'mlx' ? 'mlx' : 'llama'}.log`);
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
        .filter(([providerName, info]) => (
          providerName !== 'local' && info.available && info.models.length > 0
        ))
    : [];

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
  ].filter((section) => section.models.length > 0);

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      className="max-h-[90vh] max-w-6xl"
    >
      <DialogHeader>
        <DialogTitle>Select model</DialogTitle>
      </DialogHeader>
      <DialogContent className="space-y-4 overflow-hidden">
        {error && (
          <p className="rounded-xl border border-red-500/20 bg-red-500/[0.08] px-3 py-2 text-xs font-mono text-red-300">{error}</p>
        )}
        <div className="max-h-[72vh] space-y-4 overflow-y-auto pr-1">
          {loading && (
            <p className="px-3 py-3 font-mono text-xs text-zinc-300">Loading models...</p>
          )}
          {registryProviders.map(([providerName, info]) => (
                <section key={providerName} className="premium-panel overflow-hidden">
                  <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
                    <div>
                      <p className="premium-section-label">{providerName}</p>
                      <p className="mt-1 text-[12px] text-zinc-500">{info.models.length} cloud preset{info.models.length !== 1 ? 's' : ''}</p>
                    </div>
                  </div>
                  <div className="p-2">
                    {info.models.map((model: RegistryModelPreset) => {
                      const alias = model.aliases[0] || model.model_id;
                      const isActive = registryData?.active_model_id === model.model_id
                        || modelStatus?.model_name === model.display_name
                        || modelStatus?.model_name === model.model_id;
                      const isBusy = switching === alias || switching === model.model_id;
                      return (
                        <button
                          key={model.model_id}
                          onClick={() => handleSelectRegistry(alias)}
                          disabled={!!switching}
                          className={cn(
                            'ui-transition mb-1 block w-full rounded-[1rem] border px-4 py-3 text-left last:mb-0',
                            isActive
                              ? 'border-cyan-300/30 bg-cyan-300/[0.075] text-zinc-50'
                              : 'border-transparent bg-transparent text-zinc-300 hover:border-white/10 hover:bg-white/[0.045] hover:text-cyan-100',
                            isBusy && 'opacity-60',
                          )}
                        >
                          <div className="flex items-start justify-between gap-4">
                            <div className="min-w-0">
                              <div className="truncate text-[13px] font-semibold tracking-[-0.02em] text-inherit">{model.display_name}</div>
                              <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-zinc-500">
                                <span>{Math.round(model.context_window / 1024)}k ctx</span>
                                {model.supports_vision && <span>vision</span>}
                                {model.input_cost_per_million != null && model.output_cost_per_million != null && (
                                  <span>${model.input_cost_per_million}/$${model.output_cost_per_million}M</span>
                                )}
                              </div>
                            </div>
                            {isActive && (
                              <span className="rounded-full border border-cyan-300/26 bg-cyan-300/[0.10] px-2 py-0.5 text-[10px] uppercase tracking-[0.16em] text-cyan-100">
                                active
                              </span>
                            )}
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </section>
              ))}

              {providerSections.map((section) => (
                <section key={section.key} className="premium-panel overflow-hidden">
                  <div className="border-b border-white/10 px-4 py-3">
                    <p className="premium-section-label">{section.label}</p>
                    <p className="mt-1 text-[12px] text-zinc-500">{section.models.length} local runtime{section.models.length !== 1 ? 's' : ''}</p>
                  </div>
                  <div className="p-2">
                    {section.models.map((model) => {
                      const isActive = modelStatus?.provider === 'local' && (
                        section.key === 'local-gguf'
                          ? modelStatus.model_name === model.name.replace(/.*\//, '').replace(/\.gguf$/, '')
                          : modelStatus.model_name === model.name.replace(/.*\//, '')
                      );
                      const isBusy = switching === model.path;
                      return (
                        <button
                          key={model.path}
                          onClick={() => handleSelectLocal(model)}
                          disabled={!!switching}
                          className={cn(
                            'ui-transition mb-1 block w-full rounded-[1rem] border px-4 py-3 text-left last:mb-0',
                            isActive
                              ? 'border-cyan-300/30 bg-cyan-300/[0.075] text-zinc-50'
                              : 'border-transparent text-zinc-300 hover:border-white/10 hover:bg-white/[0.045] hover:text-cyan-100',
                            isBusy && 'opacity-60',
                          )}
                        >
                          <div className="flex items-start justify-between gap-4">
                            <div className="min-w-0">
                              <div className="truncate text-[13px] font-semibold tracking-[-0.02em] text-inherit">{model.name}</div>
                              <div className="mt-1 text-[11px] text-zinc-500">{model.size_display}</div>
                            </div>
                            {isActive && (
                              <span className="rounded-full border border-cyan-300/26 bg-cyan-300/[0.10] px-2 py-0.5 text-[10px] uppercase tracking-[0.16em] text-cyan-100">
                                active
                              </span>
                            )}
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </section>
              ))}

          <section className="premium-panel overflow-hidden">
                <div className="border-b border-white/10 px-4 py-3">
                  <p className="premium-section-label">provider api keys</p>
                  <p className="mt-1 text-[12px] text-zinc-500">Persisted for cloud providers and loaded into runtime on startup.</p>
                </div>
                <div className="space-y-3 p-3">
                  {providerKeys.map((providerKey) => {
                    const busy = switching === `provider-key:${providerKey.provider}`;
                    return (
                      <div
                        key={providerKey.provider}
                        className="rounded-[1rem] border border-white/10 bg-white/[0.025] px-3.5 py-3"
                      >
                        <div className="mb-3 flex items-start justify-between gap-3 text-[11px] font-mono">
                          <div className="min-w-0">
                            <div className="uppercase text-zinc-300">{providerKey.provider}</div>
                            <div className="mt-1 truncate text-zinc-500">{providerKey.api_key_env}</div>
                          </div>
                          <div className="shrink-0 rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-1 text-[10px] uppercase tracking-[0.16em] text-zinc-400">
                            {providerKey.has_key ? `saved · ${providerKey.source}` : 'not set'}
                          </div>
                        </div>
                        <div className="flex flex-col gap-2 sm:flex-row">
                          <input
                            value={providerKeyDrafts[providerKey.provider] || ''}
                            onChange={(e) => setProviderKeyDrafts((drafts) => ({
                              ...drafts,
                              [providerKey.provider]: e.target.value,
                            }))}
                            placeholder={providerKey.has_key ? 'update api key' : 'enter api key'}
                            type="password"
                            className="premium-field flex-1"
                          />
                          <div className="flex gap-2">
                            <button
                              onClick={() => handleSaveProviderKey(providerKey.provider)}
                              disabled={!!switching}
                              className="premium-primary-button"
                              type="button"
                            >
                              {busy ? 'saving...' : 'save'}
                            </button>
                            <button
                              onClick={() => handleClearProviderKey(providerKey.provider)}
                              disabled={!!switching || !providerKey.has_key}
                              className="premium-subtle-button"
                              type="button"
                            >
                              clear
                            </button>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
          </section>
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
  const showReasoningEffort = !isFireworks && capabilities?.reasoning_effort.supported;
  const showReasoningMaxTokens = providerFamily === 'openrouter' && capabilities?.reasoning_max_tokens.supported;
  const fireworksMode = draft?.fireworks_reasoning_mode ?? 'effort';
  const openRouterMode = draft?.reasoning_max_tokens == null ? 'effort' : 'budget';
  const minFireworksThinkingBudget = 1024;
  const inputClassName = 'premium-field';
  const selectClassName = 'premium-field appearance-none';

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
          <p className="text-xs font-mono text-zinc-200">Loading reasoning settings...</p>
        ) : (
          <div className="space-y-4 font-mono text-xs">
            <section className="premium-panel px-4 py-3.5">
              <div className="premium-section-label">active model</div>
              <div className="mt-2 text-sm text-zinc-100">{modelName}</div>
              <div className="mt-1 text-[11px] uppercase tracking-[0.16em] text-zinc-500">{providerFamily}</div>
            </section>

            <section className="premium-panel px-4 py-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <label className="space-y-2">
                  <div>
                    <div className="text-zinc-300">max output</div>
                    <div className="mt-1 text-[11px] leading-5 text-zinc-500">Upper bound for answer tokens.</div>
                  </div>
                  <input
                    type="number"
                    min={1}
                    value={draft.max_output_tokens ?? ''}
                    onChange={(e) => update('max_output_tokens', e.target.value === '' ? null : Number(e.target.value))}
                    className={inputClassName}
                  />
                </label>
                {showReasoningEffort && !showReasoningMaxTokens && (
                  <label className="space-y-2">
                    <div>
                      <div className="text-zinc-300">thinking effort</div>
                      <div className="mt-1 text-[11px] leading-5 text-zinc-500">Provider-managed reasoning depth.</div>
                    </div>
                    <select
                      value={draft.reasoning_effort ?? ''}
                      onChange={(e) => update('reasoning_effort', e.target.value || null)}
                      disabled={!capabilities.reasoning_effort.supported}
                      title={disabledReason(capabilities.reasoning_effort.supported, capabilities.reasoning_effort.reason)}
                      className={selectClassName}
                    >
                      <option value="">default</option>
                      {(capabilities.reasoning_effort.options.length ? capabilities.reasoning_effort.options : ['low', 'medium', 'high']).map((opt) => (
                        <option key={opt} value={opt}>{opt}</option>
                      ))}
                    </select>
                  </label>
                )}
              </div>
            </section>

            {isFireworks ? (
              <section className="premium-panel px-4 py-4">
                <div className="premium-section-label">Fireworks controls</div>
                <div className="mt-4 grid gap-4 sm:grid-cols-2">
                  <label className="space-y-2">
                    <div className="text-zinc-300">control mode</div>
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
                  </label>

                  {fireworksMode === 'effort' ? (
                    <label className="space-y-2">
                      <div className="text-zinc-300">thinking effort</div>
                      <select
                        value={draft.reasoning_effort ?? ''}
                        onChange={(e) => update('reasoning_effort', e.target.value || null)}
                        disabled={!capabilities.reasoning_effort.supported}
                        title={disabledReason(capabilities.reasoning_effort.supported, capabilities.reasoning_effort.reason)}
                        className={selectClassName}
                      >
                        <option value="">default</option>
                        {(capabilities.reasoning_effort.options.length ? capabilities.reasoning_effort.options : ['low', 'medium', 'high']).map((opt) => (
                          <option key={opt} value={opt}>{opt}</option>
                        ))}
                      </select>
                    </label>
                  ) : (
                    <label className="space-y-2">
                      <div className="text-zinc-300">max thinking tokens</div>
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
                <p className="mt-3 text-[11px] leading-5 text-zinc-500">
                  {fireworksMode === 'effort'
                    ? 'Sends reasoning_effort only.'
                    : 'Sends thinking.budget_tokens only.'}
                </p>
              </section>
            ) : showReasoningMaxTokens ? (
              <section className="premium-panel px-4 py-4">
                <div className="premium-section-label">OpenRouter controls</div>
                <div className="mt-4 grid gap-4 sm:grid-cols-2">
                  <label className="space-y-2">
                    <div className="text-zinc-300">control mode</div>
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
                  </label>

                  {openRouterMode === 'effort' ? (
                    <label className="space-y-2">
                      <div className="text-zinc-300">thinking effort</div>
                      <select
                        value={draft.reasoning_effort ?? ''}
                        onChange={(e) => update('reasoning_effort', e.target.value || null)}
                        disabled={!capabilities.reasoning_effort.supported}
                        title={disabledReason(capabilities.reasoning_effort.supported, capabilities.reasoning_effort.reason)}
                        className={selectClassName}
                      >
                        <option value="">default</option>
                        {(capabilities.reasoning_effort.options.length ? capabilities.reasoning_effort.options : ['low', 'medium', 'high']).map((opt) => (
                          <option key={opt} value={opt}>{opt}</option>
                        ))}
                      </select>
                    </label>
                  ) : (
                    <label className="space-y-2">
                      <div className="text-zinc-300">max thinking tokens</div>
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
              <section className="premium-panel px-4 py-3.5 text-[11px] leading-5 text-zinc-500">
                This provider has no separate max thinking token setting.
              </section>
            )}

            <div className="flex justify-end gap-2">
              <button
                onClick={() => onOpenChange(false)}
                className="premium-subtle-button"
                type="button"
              >
                cancel
              </button>
              <button
                onClick={onSave}
                disabled={saving}
                className="premium-primary-button"
                type="button"
              >
                {saving ? 'saving...' : 'save'}
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
      <div className="flex gap-4">
        <div className="w-11 flex-shrink-0 pt-1.5">
          <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-zinc-500">you</span>
        </div>
        <div className="min-w-0 flex-1">
          <div className="fluxion-card rounded-[1.35rem] border px-6 py-5">
            <span className="whitespace-pre-wrap text-[14px] leading-[1.9] text-zinc-50">
              {run.user_message || run.prompt}
            </span>
          </div>
          <p className="mt-2 px-1 text-[11px] text-zinc-500">
            {formatRelativeTime(run.created_at)}
          </p>
        </div>
      </div>

      <div className="group/msg flex gap-4">
        <div className="w-11 flex-shrink-0 pt-1.5">
          <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-zinc-500">reply</span>
        </div>
        <div className="min-w-0 flex-1">
          <div className="fluxion-card-strong rounded-[1.35rem] border px-6 py-5">
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
            ) : run.status === 'failed' ? (
              <div className="rounded-[1rem] border border-red-500/16 bg-red-500/[0.06] px-4 py-3 text-sm text-red-200/90">
                [error] {run.error_detail || 'Request failed. Please try again.'}
              </div>
            ) : displayText ? (
              <div>
                <AnswerMarkdown content={extractAnswer(displayText)} />
                {isStreaming && (
                  <span className="inline-block h-4 w-2 animate-pulse bg-zinc-400 align-[-0.2em] ml-0.5" />
                )}
              </div>
            ) : !isThinking ? (
              <div className="text-sm text-zinc-300">No response.</div>
            ) : null}
          </div>

          <div className="mt-2 flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-1 font-mono text-[11px]">
            <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 text-zinc-500">
              <span className={cn(
                'rounded-full border border-zinc-800/85 bg-zinc-950/72 px-2.5 py-1',
                run.status === 'succeeded'
                  ? 'text-emerald-300'
                  : run.status === 'failed'
                    ? 'border-red-500/15 text-red-400/85'
                    : 'text-zinc-400'
              )}>
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
}: {
  open: boolean;
  loading: boolean;
  error: string | null;
  entries: WorkspaceFileEntry[];
  selectedIndex: number;
  onSelect: (entry: WorkspaceFileEntry) => void;
}) {
  const itemRefs = useRef<Array<HTMLButtonElement | null>>([]);

  useEffect(() => {
    if (!open) return;
    const activeItem = itemRefs.current[selectedIndex];
    activeItem?.scrollIntoView({ block: 'nearest' });
  }, [open, selectedIndex, entries]);

  if (!open) return null;

  return (
    <div className="ui-panel-strong ui-elevated absolute left-0 right-0 bottom-full z-50 mb-2 max-h-64 overflow-y-auto rounded-[1rem] border border-white/10">
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

function EmptyStatePulse({
  mode,
  workspacePath,
  modelStatus,
}: {
  mode: ChatMode;
  workspacePath: string;
  modelStatus: ModelStatus | null;
}) {
  const workspaceName = workspacePath.trim()
    ? workspacePath.trim().split('/').filter(Boolean).pop() || workspacePath.trim()
    : 'no workspace';
  const provider = modelStatus?.provider || 'provider';
  const model = modelStatus?.model_name || 'model';

  return (
    <div className="w-full max-w-xl space-y-6 text-center">
      <div className="relative mx-auto h-20 w-80 max-w-full overflow-hidden opacity-80">
        <svg
          viewBox="0 0 320 80"
          aria-hidden="true"
          className="absolute inset-0 h-full w-full text-zinc-800"
        >
          <path
            d="M8 48 C 52 8, 92 72, 136 38 S 224 12, 312 42"
            fill="none"
            stroke="currentColor"
            strokeWidth="1"
          />
          <path
            d="M8 52 C 58 26, 91 54, 140 34 S 232 62, 312 26"
            fill="none"
            stroke="currentColor"
            strokeWidth="1"
            opacity="0.45"
          />
        </svg>
        <div className="fluxion-trace absolute left-0 top-0 h-full w-28 bg-gradient-to-r from-transparent via-zinc-500/20 to-transparent" />
      </div>

      <div className="grid grid-cols-3 gap-px overflow-hidden rounded-[1.2rem] border border-white/10 bg-white/10 text-left">
        <div className="bg-black/35 px-3 py-3">
          <div className="text-[10px] uppercase tracking-[0.18em] text-zinc-500">mode</div>
          <div className="truncate pt-1 text-[12px] text-zinc-200">{mode}</div>
        </div>
        <div className="bg-black/35 px-3 py-3">
          <div className="text-[10px] uppercase tracking-[0.18em] text-zinc-500">workspace</div>
          <div className={cn("truncate pt-1 text-[12px]", workspacePath.trim() ? "text-zinc-200" : "text-zinc-400")}>
            {workspaceName}
          </div>
        </div>
        <div className="bg-black/35 px-3 py-3">
          <div className="text-[10px] uppercase tracking-[0.18em] text-zinc-500">{provider}</div>
          <div className="truncate pt-1 text-[12px] text-zinc-200">{model}</div>
        </div>
      </div>
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
  const removeRun = useStore((s) => s.removeRun);
  const clearAgentRun = useStore((s) => s.clearAgentRun);
  const setEvents = useStore((s) => s.setEvents);
  const conversation = useSelectedConversation();
  const runs = useConversationRuns(selectedConversationId);
  const terminalState = useConversationTerminal(selectedConversationId);
  const initTerminalState = useStore((s) => s.initTerminalState);
  const hasActiveRun = useHasActiveRun();
  const updateTerminalState = useStore((s) => s.updateTerminalState);
  const draftWorkspacePath = useStore((s) => s.draftWorkspacePath);
  const setDraftWorkspacePath = useStore((s) => s.setDraftWorkspacePath);
  const rememberWorkspacePath = useStore((s) => s.rememberWorkspacePath);
  const [message, setMessage] = useState('');
  const [imageAttachments, setImageAttachments] = useState<ImageAttachment[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [mode, setMode] = useState<ChatMode>('agent');
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
  const [viewportWidth, setViewportWidth] = useState(
    () => (typeof window !== 'undefined' ? window.innerWidth : 1440)
  );
  const isDesktop = viewportWidth >= 768;
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const verticalMoveColumnRef = useRef<number | null>(null);
  const composerFocusRafRef = useRef<number | null>(null);
  const pendingWorkspaceShortcutRef = useRef<'workspace-new' | 'workspace-picker' | null>(null);
  const pendingWorkspaceShortcutTimeoutRef = useRef<number | null>(null);
  const lastEscapeAtRef = useRef(0);

  // Model picker state
  const [modelPickerOpen, setModelPickerOpen] = useState(false);
  const [modelStatus, setModelStatus] = useState<ModelStatus | null>(null);
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
    localStorage.setItem('reasoner_permission_policy', permissionPolicy);
  }, [permissionPolicy]);

  useEffect(() => {
    if (conversation?.workspace_path) {
      setDraftWorkspacePath(conversation.workspace_path);
    }
  }, [conversation?.workspace_path, setDraftWorkspacePath]);

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

    initTerminalState(selectedConversationId, {
      isOpen: savedState.isOpen ?? false,
      dock: savedState.dock === 'bottom' ? 'bottom' : 'right',
      height: Number(savedState.height || 260),
      width: Number(savedState.width || 420),
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
    const handleResize = () => setViewportWidth(window.innerWidth);
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // Fetch model status and usage on mount
  useEffect(() => {
    getModelStatus().then(setModelStatus).catch(() => {});
    refreshUsage();
    refreshReasoningSettings();
  }, [refreshUsage, refreshReasoningSettings]);

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
  const [queuedSteers, setQueuedSteers] = useState<string[]>([]);
  const [rewindOpen, setRewindOpen] = useState(false);
  const [rewindLoading, setRewindLoading] = useState(false);
  const [rewindSubmitting, setRewindSubmitting] = useState(false);
  const [rewindCheckpoints, setRewindCheckpoints] = useState<ConversationRewindCheckpoint[]>([]);
  const [rewindSelectedRunId, setRewindSelectedRunId] = useState<string | null>(null);
  const rewindLoadInFlightRef = useRef(false);
  const rewindRestoreInFlightRef = useRef(false);

  // Track any active run (chat or agent) for UI purposes (auto-scroll, completion detection)
  const activeRunId = useMemo(() => {
    for (let i = runs.length - 1; i >= 0; i -= 1) {
      if (runs[i].status === 'running') {
        return runs[i].run_id;
      }
    }
    return null;
  }, [runs]);
  const activeAgentRun = useMemo(() => {
    for (let i = runs.length - 1; i >= 0; i -= 1) {
      if (runs[i].status === 'running' && runs[i].mode === 'agent') {
        return runs[i];
      }
    }
    return null;
  }, [runs]);
  const activeAgentHudState = useAgentRunDetails(activeAgentRun?.run_id ?? null, !!activeAgentRun);

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
  const latestRunContextUsage = latestContextRun?.context_usage;
  const footerContextUsage = useMemo(() => (
    activeAgentState?.context_usage
    ?? latestRunContextUsage
    ?? undefined
  ), [activeAgentState?.context_usage, latestRunContextUsage]);
  const conversationRawTokens = useMemo(() => {
    return runs.reduce((total, run) => {
      if (run.run_id === activeRunId && activeAgentState?.usage?.total_tokens !== undefined) {
        return total + activeAgentState.usage.total_tokens;
      }
      const runUsage = run.usage as { total_tokens?: number } | undefined;
      return total + (runUsage?.total_tokens ?? 0);
    }, 0);
  }, [runs, activeRunId, activeAgentState?.usage?.total_tokens]);
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
    !!footerContextUsage || conversationRawTokens > 0
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
  const {
    subscribe: subscribeAgent,
    unsubscribe: unsubscribeAgent,
  } = useAgentSSE(null); // Manual subscription, not auto

  useEffect(() => {
    if (!selectedConversationId) return;

    async function loadConversation() {
      try {
        const data = await getConversation(selectedConversationId!);
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
      }
    }

    loadConversation();
  }, [navigate, selectConversation, selectedConversationId, setRuns, updateConversation, subscribe, subscribeAgent]);

  // Scroll on new runs
  useEffect(() => {
    if (!scrollRef.current) return;
    scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [runs.length]);

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

  const handleOpenWorkspacePicker = useCallback(() => {
    if (isWorkspaceLocked) {
      toast.error(
        hasConversationWorkspace
          ? 'This conversation is already bound to its workspace'
          : 'This conversation has no workspace. Create a new workspace thread from the sidebar.'
      );
      return;
    }
    setWorkspacePickerMode('draft');
    setWorkspacePickerOpen(true);
  }, [hasConversationWorkspace, isWorkspaceLocked]);

  const handleOpenTerminal = useCallback(async () => {
    if (mode !== 'agent' || !isDesktop) return;
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

    let conversationId = selectedConversationId;
    if (!conversationId) {
      const response = await createConversation({
        title: 'Terminal',
        workspace_path: effectiveWorkspacePath,
      });
      conversationId = response.conversation_id;
      const newConversation: Conversation = {
        conversation_id: conversationId,
        created_at: new Date().toISOString(),
        title: 'Terminal',
        summary: '',
        workspace_path: effectiveWorkspacePath,
        status: 'active',
        metadata: {},
      };
      addConversation(newConversation);
      setRuns(conversationId, []);
      navigate(`/conversations/${conversationId}`);
    }

    updateTerminalState(conversationId, { isOpen: true });
  }, [
    addConversation,
    isDesktop,
    mode,
    navigate,
    selectedConversationId,
    setRuns,
    effectiveWorkspacePath,
    updateTerminalState,
  ]);

  const handleSubmit = async () => {
    if ((!message.trim() && imageAttachments.length === 0) || isSubmitting) return;
    if (imageAttachments.length > 0 && !modelStatus?.supports_vision) {
      toast.error('Active model does not support images. Select a vision model.');
      return;
    }

    // If an agent run is active, steer it instead of creating a new run
    if (hasActiveRun && activeRunId) {
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
        const response = await createConversation({ workspace_path: effectiveWorkspacePath });
        conversationId = response.conversation_id;
        rememberWorkspacePath(effectiveWorkspacePath);
        const newConversation: Conversation = {
          conversation_id: conversationId,
          created_at: new Date().toISOString(),
          title: conversationTitleFromMessage(messageToSend),
          summary: '',
          workspace_path: effectiveWorkspacePath,
          status: 'active',
          metadata: {},
        };
        addConversation(newConversation);
        setRuns(conversationId, []);
        needsNavigate = true;
      } else if (!conversation?.title || conversation.title === 'New conversation') {
        updateConversation(conversationId, {
          title: conversationTitleFromMessage(messageToSend),
        });
      }

      if (mode === 'agent') {
        // Agent mode: use agent API
        const response = await createAgentRun({
          query: messageToSend,
          image_attachments: attachmentsToSend,
          conversation_id: conversationId!,
          max_steps: 1000,
          workspace_path: effectiveWorkspacePath || undefined,
          filesystem_enabled: !!effectiveWorkspacePath,
          permission_policy: permissionPolicy,
          capabilities: {
            web: true,
            filesystem: !!effectiveWorkspacePath,
            bash: !!effectiveWorkspacePath,
            python: false,
          },
        });

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
        const response = await createConversationRun(conversationId!, {
          message: messageToSend,
          image_attachments: attachmentsToSend,
        });

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
      clearMentionState();
      setQueuedSteers([]);
      subscribedRunRef.current = null;
    }
  }, [clearMentionState, selectedConversationId, activeRunId, pendingRunId]);

  const handleStop = async () => {
    if (!pendingRunId) return;

    try {
      if (pendingIsAgent) {
        // 1. Unsubscribe from agent stream
        unsubscribeAgent();

        // 2. Call agent cancel endpoint
        await cancelAgentRun(pendingRunId);
      } else {
        // 1. Unsubscribe from the stream
        unsubscribe();

        // 2. Call backend abort endpoint
        await abortRun(pendingRunId);
      }

      // 3. Remove the optimistic run from store
      removeRun(pendingRunId);

      // 4. Restore user message
      setMessage(pendingMessage);
      clearMentionState();

      // 5. Reset state
      setPendingRunId(null);
      setPendingMessage('');
      setPendingIsAgent(false);
      setIsSubmitting(false);
      scheduleComposerFocus();
    } catch (error) {
      console.error('Failed to abort run:', error);
      toast.error('Failed to stop generation.');
      // Even if abort fails, clean up UI state
      setPendingRunId(null);
      setPendingMessage('');
      setPendingIsAgent(false);
      setIsSubmitting(false);
      scheduleComposerFocus();
    }
  };

  // Determine if we should show Stop button (active run we started)
  const isGenerating = !!pendingRunId;
  const terminalAvailable = !!selectedConversationId && mode === 'agent' && isDesktop;
  const preferredTerminalDock = terminalState?.dock ?? 'bottom';
  const canRightDockTerminal = viewportWidth >= 1200;
  const rightTerminalOpen = terminalAvailable
    && !!terminalState?.isOpen
    && preferredTerminalDock === 'right'
    && canRightDockTerminal;
  const bottomTerminalOpen = terminalAvailable && !!terminalState?.isOpen && !rightTerminalOpen;

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

  const openWorkspacePickerForNewConversation = useCallback(() => {
    setWorkspacePickerMode('new-conversation');
    setWorkspacePickerOpen(true);
  }, []);

  const startWorkspaceDraftConversation = useCallback((workspacePath: string) => {
    if (hasActiveRun) return;
    const normalized = workspacePath.trim();
    if (!normalized) {
      openWorkspacePickerForNewConversation();
      return;
    }
    selectConversation(null);
    rememberWorkspacePath(normalized);
    setDraftWorkspacePath(normalized);
    navigate('/conversations');
  }, [
    hasActiveRun,
    navigate,
    openWorkspacePickerForNewConversation,
    rememberWorkspacePath,
    selectConversation,
    setDraftWorkspacePath,
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

  if (!conversation && runs.length === 0) {
    return (
      <div className="h-full flex flex-col">
        {/* Status bar */}
        <div className="fluxion-topbar border-b px-3 py-2.5 sm:px-4 flex items-center justify-between font-mono text-[11px]">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => setModelPickerOpen(true)}
              className="ui-transition text-zinc-300 hover:text-cyan-100"
              title="Switch model"
            >
              {modelStatus?.model_name || 'model'}
              {modelStatus?.context_window ? (
                <span className="ml-1 text-zinc-500">({Math.round(modelStatus.context_window / 1024)}k)</span>
              ) : null}
              {modelStatus?.provider === 'local' && (
                <span className="ml-1 text-zinc-500">(local)</span>
              )}
            </button>
            <span className="text-zinc-700">|</span>
            <button
              onClick={() => setReasoningSettingsOpen(true)}
              className="ui-transition text-zinc-300 hover:text-cyan-100"
              title="Open reasoning settings"
            >
              reasoning
            </button>
            {mode === 'agent' && isDesktop && (
              <>
                <span className="text-zinc-700">|</span>
                <button
                  onClick={() => void handleOpenTerminal()}
                  className="ui-transition text-zinc-300 hover:text-cyan-100"
                  title={effectiveWorkspacePath ? 'Open integrated terminal' : 'Select or open a workspace conversation first'}
                >
                  terminal
                </button>
              </>
            )}
          </div>
        </div>
        <ModelPicker
          open={modelPickerOpen}
          onOpenChange={setModelPickerOpen}
          modelStatus={modelStatus}
          onModelStatusChange={setModelStatus}
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
        <div className="flex-1 flex flex-col items-center justify-center gap-4 overflow-y-auto px-3 text-zinc-300 sm:gap-6 sm:px-4 md:px-6 min-h-0">
          <EmptyStatePulse
            mode={mode}
            workspacePath={effectiveWorkspacePath}
            modelStatus={modelStatus}
          />
        </div>
        <div className="flex-shrink-0 space-y-3 p-3 pb-[max(1rem,env(safe-area-inset-bottom))] sm:p-4 sm:pb-[max(1rem,env(safe-area-inset-bottom))]">
          {/* Prompt area */}
          <div className="fluxion-composer ui-transition relative z-30 overflow-visible rounded-[1.2rem] border px-1">
            <div className="flex items-start gap-3 p-4">
              <span className="mt-0.5 select-none font-mono text-sm text-cyan-200/80">&gt;</span>
              <textarea
                ref={textareaRef}
                placeholder={mode === 'agent' ? 'Ask the coding agent...' : 'Ask a question...'}
                value={message}
                onChange={handleMessageChange}
                onPaste={handlePaste}
                onKeyDown={handleKeyDown}
                onSelect={handleTextareaSelection}
                onClick={handleTextareaSelection}
                rows={2}
                className="flex-1 resize-none border-none bg-transparent text-[14px] leading-[1.9] text-zinc-50 outline-none placeholder:text-zinc-500"
                disabled={isSubmitting || hasActiveRun}
                style={{ maxHeight: '200px' }}
              />
            </div>
            <MentionPicker
              open={mentionOpen}
              loading={mentionLoading}
              error={mentionError}
              entries={mentionResults}
              selectedIndex={mentionSelectedIndex}
              onSelect={handleMentionSelect}
            />
          </div>
          {imageAttachments.length > 0 && (
            <div className="flex flex-wrap gap-1.5 px-1 font-mono text-[11px]">
              {imageAttachments.map((attachment, index) => (
                <button
                  key={attachment.id || index}
                  type="button"
                  onClick={() => removeImageAttachment(attachment.id)}
                  className="rounded-lg border border-zinc-700 bg-zinc-900 px-2 py-0.5 text-zinc-300 hover:border-cyan-500/30 hover:text-cyan-100"
                  title="Remove image"
                >
                  image {index + 1} ×
                </button>
              ))}
            </div>
          )}
          {/* Toolbar */}
          <div className="flex items-center justify-between px-1.5">
            <div className="flex items-center gap-3 font-mono text-[11px]">
              <button
                onClick={() => setMode('agent')}
                className={cn(
                  'transition-colors',
                  mode === 'agent' ? 'text-cyan-100' : 'text-zinc-500 hover:text-cyan-100'
                )}
              >
                agent
              </button>
              <button
                onClick={() => setMode('chat')}
                className={cn(
                  'transition-colors',
                  mode === 'chat' ? 'text-cyan-100' : 'text-zinc-500 hover:text-cyan-100'
                )}
              >
                chat
              </button>
              {mode === 'agent' && (
                <>
                  {isWorkspaceLocked ? (
                    <span
                      className={cn(
                        'max-w-52 truncate text-xs font-mono',
                        hasConversationWorkspace ? 'text-zinc-300' : 'text-zinc-600'
                      )}
                      title={
                        hasConversationWorkspace
                          ? effectiveWorkspacePath
                          : 'This conversation has no workspace. Create a new workspace thread from the sidebar.'
                      }
                    >
                      {hasConversationWorkspace ? effectiveWorkspacePath : 'no workspace'}
                    </span>
                  ) : (
                    <>
                      <input
                        value={draftWorkspacePath}
                        onChange={(e) => setDraftWorkspacePath(e.target.value)}
                        placeholder="/path/to/repo"
                        className="w-40 sm:w-56 bg-transparent border-none outline-none text-[11px] font-mono text-zinc-300 placeholder:text-zinc-600"
                        title="Workspace path for filesystem and bash tools"
                      />
                      <button
                        onClick={() => {
                          setWorkspacePickerMode('draft');
                          handleOpenWorkspacePicker();
                        }}
                        className="ui-transition text-zinc-400 hover:text-cyan-100"
                        title="Browse local folders"
                      >
                        browse
                      </button>
                    </>
                  )}
                  <select
                    value={permissionPolicy}
                    onChange={(e) => setPermissionPolicy(e.target.value as 'strict' | 'relaxed' | 'yolo')}
                    className="bg-transparent border-none outline-none text-[11px] font-mono text-zinc-300 cursor-pointer"
                    title="Tool permission policy"
                  >
                    <option value="strict">strict</option>
                    <option value="relaxed">relaxed</option>
                    <option value="yolo">yolo</option>
                  </select>
                </>
              )}
              <span className="text-zinc-700">|</span>
              {mode === 'agent' && isDesktop && (
                <button
                  onClick={() => void handleOpenTerminal()}
                  className="ui-transition text-zinc-300 hover:text-cyan-100"
                  title={effectiveWorkspacePath ? 'Open integrated terminal' : 'Select or open a workspace conversation first'}
                >
                  terminal
                </button>
              )}
              {mode === 'agent' && isDesktop && <span className="text-zinc-700">|</span>}
              {isGenerating ? (
                <button onClick={handleStop} className="text-red-400 hover:text-red-300 transition-colors">
                  stop
                </button>
              ) : (
                <button
                  onClick={handleSubmit}
                  disabled={!message.trim() || isSubmitting || hasActiveRun}
                  className={cn(
                    'transition-colors',
                    !message.trim() || isSubmitting || hasActiveRun
                  ? 'text-zinc-700 cursor-not-allowed'
                      : 'text-cyan-100 hover:text-white'
                  )}
                  title={hasActiveRun ? 'Active run in progress' : undefined}
                >
                  {isSubmitting ? 'sending...' : 'send'}
                </button>
              )}
            </div>
            <div className="flex items-center gap-3 font-mono text-[11px] text-zinc-500">
              <span className="hidden md:inline">⌘+Enter send</span>
              <span className={message.length > MAX_INPUT_CHARS * 0.9 ? 'text-zinc-400' : ''}>
                {message.length.toLocaleString()}/{MAX_INPUT_CHARS.toLocaleString()}
              </span>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
        <div className="fluxion-topbar flex items-center justify-between border-b px-3 py-2.5 font-mono text-[11px] sm:px-4 md:px-6">
        <div className="flex items-center gap-3 truncate mr-4">
          <button
            type="button"
            onClick={() => setModelPickerOpen(true)}
            className="ui-transition flex-shrink-0 text-zinc-300 hover:text-cyan-100"
            title="Switch model"
          >
            {modelStatus?.model_name || 'model'}
            {modelStatus?.context_window ? (
              <span className="ml-1 text-zinc-600">({Math.round(modelStatus.context_window / 1024)}k)</span>
            ) : null}
            {modelStatus?.provider === 'local' && (
              <span className="ml-1 text-zinc-600">(local)</span>
            )}
          </button>
          <span className="text-zinc-700">|</span>
          <button
            onClick={() => setReasoningSettingsOpen(true)}
            className="ui-transition flex-shrink-0 text-zinc-300 hover:text-cyan-100"
            title="Open reasoning settings"
          >
            reasoning
          </button>
          <span className="text-zinc-700">|</span>
          <span className="truncate text-zinc-500">
            {conversation?.title || 'conversation'}
          </span>
        </div>
      </div>
      <ModelPicker
        open={modelPickerOpen}
        onOpenChange={setModelPickerOpen}
        modelStatus={modelStatus}
        onModelStatusChange={setModelStatus}
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

      <div className="flex min-h-0 flex-1">
        <div className="relative flex min-h-0 min-w-0 flex-1 flex-col">
          <div className="flex-1 overflow-y-auto px-4 py-6 sm:px-6 md:px-8 md:py-8" ref={scrollRef}>
            <div className="w-full max-w-[62rem]">
              <VirtualizedConversationRunList
                runs={runs}
                scrollContainerRef={scrollRef}
                renderRun={renderRunCard}
              />
            </div>
          </div>

          {/* Scroll-to-bottom pill */}
          <ScrollToBottom
            scrollRef={scrollRef}
            isStreaming={!!activeRunId}
            className={cn(
              "left-1/2 -translate-x-1/2",
              bottomTerminalOpen
                ? "bottom-[calc(6rem+var(--terminal-height,260px))]"
                : activeAgentHudState?.isActive
                  ? "bottom-40"
                  : "bottom-28"
            )}
          />

          {activeAgentRun && activeAgentHudState?.isActive && (
            <AgentLiveHUD
              runId={activeAgentRun.run_id}
              runCreatedAt={activeAgentRun.created_at}
              agentState={activeAgentHudState}
            />
          )}

          {terminalAvailable && selectedConversationId && bottomTerminalOpen && (
            <div style={{ ['--terminal-height' as string]: `${terminalState?.height ?? 260}px` }}>
              <IntegratedTerminal
                key={`${selectedConversationId}-bottom`}
                conversationId={selectedConversationId}
                workspacePath={effectiveWorkspacePath}
                active={terminalAvailable}
                dock="bottom"
              />
            </div>
          )}

          <div className="flex-shrink-0 space-y-3 p-3 pb-[max(1rem,env(safe-area-inset-bottom))] sm:p-4 sm:pb-[max(1rem,env(safe-area-inset-bottom))]">
            {/* Queued steering messages */}
            {queuedSteers.length > 0 && (
              <div className="flex flex-wrap gap-1.5 px-1">
                {queuedSteers.map((msg, i) => (
                  <span
                    key={i}
                    className="inline-flex items-center gap-1 rounded-full border border-amber-500/18 bg-amber-500/[0.08] px-2.5 py-1 text-[11px] font-mono text-amber-300/85"
                  >
                    <span className="text-amber-500/50">queued:</span> {msg.length > 40 ? msg.slice(0, 40) + '...' : msg}
                  </span>
                ))}
              </div>
            )}
            {/* Prompt area */}
            <div className="fluxion-composer ui-transition relative z-30 overflow-visible rounded-[1.2rem] border px-1">
              <div className="flex items-start gap-3 p-4">
                <span className="mt-0.5 select-none font-mono text-sm text-cyan-200/80">&gt;</span>
                <textarea
                  ref={textareaRef}
                  placeholder={atLimit ? 'Message limit reached' : hasActiveRun ? 'Steer the agent...' : mode === 'agent' ? 'Ask the coding agent...' : 'Ask a follow-up question...'}
                  value={message}
                  onChange={handleMessageChange}
                  onPaste={handlePaste}
                  onKeyDown={handleKeyDown}
                  onSelect={handleTextareaSelection}
                  onClick={handleTextareaSelection}
                  rows={2}
                  className="flex-1 resize-none border-none bg-transparent text-[14px] leading-[1.9] text-zinc-50 outline-none placeholder:text-zinc-500"
                  disabled={isSubmitting || atLimit}
                  style={{ maxHeight: '200px' }}
                />
              </div>
              <MentionPicker
                open={mentionOpen}
                loading={mentionLoading}
                error={mentionError}
                entries={mentionResults}
                selectedIndex={mentionSelectedIndex}
                onSelect={handleMentionSelect}
              />
            </div>
            {imageAttachments.length > 0 && (
              <div className="flex flex-wrap gap-1.5 px-1 font-mono text-[11px]">
                {imageAttachments.map((attachment, index) => (
                  <button
                    key={attachment.id || index}
                    type="button"
                    onClick={() => removeImageAttachment(attachment.id)}
                      className="rounded-lg border border-zinc-800 bg-zinc-950 px-2 py-0.5 text-zinc-300 hover:border-cyan-500/30 hover:text-cyan-100"
                    title="Remove image"
                  >
                    image {index + 1} ×
                  </button>
                ))}
              </div>
            )}
            {/* Toolbar */}
            <div className="flex items-center justify-between px-1.5">
              <div className="flex items-center gap-3 font-mono text-[11px]">
                <button
                  onClick={() => setMode('agent')}
                  className={cn(
                    'transition-colors',
                    mode === 'agent' ? 'text-cyan-100' : 'text-zinc-500 hover:text-cyan-100'
                  )}
                >
                  agent
                </button>
                <button
                  onClick={() => setMode('chat')}
                  className={cn(
                    'transition-colors',
                    mode === 'chat' ? 'text-cyan-100' : 'text-zinc-500 hover:text-cyan-100'
                  )}
                >
                  chat
                </button>
                {mode === 'agent' && (
                  <>
                    {isWorkspaceLocked ? (
                      <span
                        className={cn(
                          'max-w-52 truncate text-xs font-mono',
                          hasConversationWorkspace ? 'text-zinc-300' : 'text-zinc-600'
                        )}
                        title={
                          hasConversationWorkspace
                            ? effectiveWorkspacePath
                            : 'This conversation has no workspace. Create a new workspace thread from the sidebar.'
                        }
                      >
                        {hasConversationWorkspace ? effectiveWorkspacePath : 'no workspace'}
                      </span>
                    ) : (
                      <>
                        <input
                          value={draftWorkspacePath}
                          onChange={(e) => setDraftWorkspacePath(e.target.value)}
                          placeholder="/path/to/repo"
                          className="w-40 sm:w-56 bg-transparent border-none outline-none text-[11px] font-mono text-zinc-300 placeholder:text-zinc-600"
                          title="Workspace path for filesystem and bash tools"
                        />
                        <button
                          onClick={handleOpenWorkspacePicker}
                          className="ui-transition text-zinc-400 hover:text-cyan-100"
                          title="Browse local folders"
                        >
                          browse
                        </button>
                      </>
                    )}
                    <select
                      value={permissionPolicy}
                      onChange={(e) => setPermissionPolicy(e.target.value as 'strict' | 'relaxed' | 'yolo')}
                      className="bg-transparent border-none outline-none text-[11px] font-mono text-zinc-300 cursor-pointer"
                      title="Tool permission policy"
                    >
                      <option value="strict">strict</option>
                      <option value="relaxed">relaxed</option>
                      <option value="yolo">yolo</option>
                      </select>
                    </>
                  )}
                  <button
                    onClick={() => setReasoningSettingsOpen(true)}
                    className="ui-transition text-zinc-300 hover:text-cyan-100"
                    title="Configure reasoning settings"
                  >
                    reasoning
                  </button>
                  {terminalAvailable && selectedConversationId && (
                    <button
                      onClick={() => {
                        if (!effectiveWorkspacePath) {
                          toast.error(selectedConversationId ? 'Create or open a workspace conversation first' : 'Select a workspace first');
                          if (!selectedConversationId) {
                            setWorkspacePickerOpen(true);
                          }
                          return;
                        }
                        updateTerminalState(selectedConversationId, { isOpen: !terminalState?.isOpen });
                      }}
                      className="ui-transition text-zinc-300 hover:text-cyan-100"
                      title={
                        effectiveWorkspacePath
                          ? (terminalState?.isOpen ? 'Collapse terminal' : 'Open terminal')
                          : 'Select or open a workspace conversation first'
                      }
                    >
                      {terminalState?.isOpen ? 'terminal−' : 'terminal+'}
                    </button>
                  )}
                  <span className="text-zinc-700">|</span>
                  {isGenerating ? (
                    <button onClick={handleStop} className="text-red-400 hover:text-red-300 transition-colors">
                      stop
                    </button>
                ) : (
                  <button
                    onClick={handleSubmit}
                    disabled={!message.trim() || isSubmitting || atLimit}
                    className={cn(
                      'transition-colors',
                      !message.trim() || isSubmitting || atLimit
                        ? 'text-zinc-700 cursor-not-allowed'
                        : hasActiveRun
                          ? 'text-amber-400/80 hover:text-amber-300'
                          : 'text-cyan-100 hover:text-white'
                    )}
                    title={atLimit ? 'Message limit reached' : hasActiveRun ? 'Send steering message to agent' : undefined}
                  >
                    {isSubmitting ? 'sending...' : atLimit ? 'limit reached' : hasActiveRun ? 'steer' : 'send'}
                  </button>
                )}
                {showComposerContextStats && (
                  <>
                    <span className="text-zinc-700">|</span>
                    <span className="text-zinc-500">
                      ctx {composerContextUtilizationPct !== null ? `${Math.round(composerContextUtilizationPct)}%` : '—'}
                    </span>
                    <span className="text-zinc-500">
                      {typeof composerPromptTokens === 'number' && composerContextWindow
                        ? `${formatContextTokens(composerPromptTokens)}/${formatContextTokens(composerContextWindow)}`
                        : '—'}
                    </span>
                    <span className="text-zinc-500">
                      raw {conversationRawTokens > 0 ? formatContextTokens(conversationRawTokens) : '—'}
                    </span>
                  </>
                )}
              </div>
              <div className="flex items-center gap-3 font-mono text-[11px] text-zinc-500">
                {hasLimit && (
                  <span className={cn(
                    atLimit ? 'text-red-500/70' : usage.remaining <= 3 ? 'text-amber-500' : ''
                  )}>
                    {atLimit ? 'no messages left' : `${usage.remaining} left`}
                  </span>
                )}
                <span className="hidden md:inline">⌘+Enter send</span>
                <span className={message.length > MAX_INPUT_CHARS * 0.9 ? 'text-zinc-400' : ''}>
                  {message.length.toLocaleString()}/{MAX_INPUT_CHARS.toLocaleString()}
                </span>
              </div>
            </div>
          </div>
        </div>
        {terminalAvailable && selectedConversationId && rightTerminalOpen && (
          <IntegratedTerminal
            key={`${selectedConversationId}-right`}
            conversationId={selectedConversationId}
            workspacePath={effectiveWorkspacePath}
            active={terminalAvailable}
            dock="right"
          />
        )}
      </div>
    </div>
  );
}
