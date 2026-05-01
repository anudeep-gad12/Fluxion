// Conversation view - simple chat interface

import { useEffect, useMemo, useRef, useState, useCallback, memo } from 'react';
import type { KeyboardEvent, ChangeEvent, ClipboardEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { AnswerMarkdown, extractAnswer } from '@/components/AnswerMarkdown';
import { ThinkingPanel } from '@/components/ThinkingPanel';
import { AgentRunMessage } from '@/components/AgentRunMessage';
import { MessageActions } from '@/components/MessageActions';
import { ShimmerSkeleton, ThinkingTimer } from '@/components/StreamingIndicator';
import { ScrollToBottom } from '@/components/ScrollToBottom';
import { IntegratedTerminal } from '@/components/IntegratedTerminal';
import { WorkspacePickerDialog } from '@/components/WorkspacePickerDialog';
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
  selectModel,
  selectCustomProvider,
  updateReasoningSettings,
  getUsage,
  steerAgentRun,
  searchWorkspaceFiles,
} from '@/api/client';
import type {
  LocalModel,
  ModelStatus,
  RegistryModelPreset,
  RegistryModelsResponse,
  CustomProviderRequest,
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
import { cn, formatRelativeTime } from '@/lib/utils';
import type { Run, Conversation, ImageAttachment } from '@/types';

/** Maximum characters allowed in the input textarea (~2000 tokens) */
const MAX_INPUT_CHARS = 8000;
const MENTION_RESULT_LIMIT = 20;
const MAX_IMAGE_ATTACHMENTS = 8;
const MAX_IMAGE_BYTES = 20 * 1024 * 1024;

/** Mode: 'chat' for regular conversation, 'agent' for agent */
type ChatMode = 'chat' | 'agent';

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
  const [loading, setLoading] = useState(false);
  const [switching, setSwitching] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [customProvider, setCustomProvider] = useState<CustomProviderRequest>({
    name: 'custom',
    base_url: 'http://localhost:1234/v1',
    api_key: '',
    model: '',
    context_window: 32768,
    max_output_tokens: 8192,
    supports_tools: true,
    supports_reasoning: false,
    supports_vision: false,
    input_cost_per_million: null,
    cached_input_cost_per_million: null,
    output_cost_per_million: null,
  });

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    setError(null);
    Promise.all([
      listRegistryModels().catch(() => null),
      listLocalModels().catch(() => []),
    ]).then(([registry, local]) => {
      setRegistryData(registry);
      setLocalModels(local as LocalModel[]);
    }).finally(() => setLoading(false));
  }, [open]);

  const handleSelectRegistry = async (modelId: string) => {
    setSwitching(modelId);
    setError(null);
    try {
      // Stop local model if running
      if (modelStatus?.provider === 'local') {
        await stopLocalModel();
      }
      await selectModel(modelId);
      const status = await getModelStatus();
      onModelStatusChange(status);
      onOpenChange(false);
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
      await startLocalModel(model.path);
      const status = await getModelStatus();
      onModelStatusChange(status);
      onOpenChange(false);
    } catch {
      setError(`Failed to start model. Check logs/${model.model_type === 'mlx' ? 'mlx' : 'llama'}.log`);
    } finally {
      setSwitching(null);
    }
  };

  const handleSelectCustom = async () => {
    if (!customProvider.base_url.trim() || !customProvider.model.trim()) {
      setError('Custom provider needs base URL and model slug');
      return;
    }
    setSwitching('custom');
    setError(null);
    try {
      await selectCustomProvider({
        ...customProvider,
        base_url: customProvider.base_url.trim(),
        api_key: customProvider.api_key?.trim() || undefined,
        model: customProvider.model.trim(),
      });
      const status = await getModelStatus();
      onModelStatusChange(status);
      onOpenChange(false);
    } catch {
      setError('Failed to switch custom provider');
    } finally {
      setSwitching(null);
    }
  };

  // Flatten registry models by provider, only show available providers
  const registryProviders = registryData
    ? Object.entries(registryData.providers)
        .filter(([, info]) => info.available && info.models.length > 0)
    : [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogHeader>
        <DialogTitle className="font-mono text-sm">Select Model</DialogTitle>
      </DialogHeader>
      <DialogContent>
        {error && (
          <p className="text-xs text-red-400 mb-2 font-mono">{error}</p>
        )}
        <div className="space-y-1 max-h-80 overflow-y-auto">
          {loading ? (
            <p className="text-xs text-zinc-600 font-mono px-3 py-2">Loading models...</p>
          ) : (
            <>
              {/* Registry models by provider */}
              {registryProviders.map(([providerName, info]) => (
                <div key={providerName}>
                  <p className="text-[10px] text-zinc-600 font-mono px-3 pt-2 pb-1 uppercase">
                    {providerName}
                  </p>
                  {info.models.map((model: RegistryModelPreset) => {
                    const isActive = registryData?.active_model_id === model.model_id
                      || modelStatus?.model_name === model.display_name
                      || modelStatus?.model_name === model.model_id;
                    return (
                      <button
                        key={model.model_id}
                        onClick={() => handleSelectRegistry(model.aliases[0] || model.model_id)}
                        disabled={!!switching}
                        className={cn(
                          'w-full text-left px-3 py-1.5 text-xs font-mono transition-colors',
                          isActive
                            ? 'text-zinc-200 bg-zinc-800'
                            : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50',
                          switching === model.model_id && 'opacity-50',
                        )}
                      >
                        <div className="flex justify-between items-center">
                          <span className="truncate mr-2">{model.display_name}</span>
                          <span className="text-zinc-600 flex-shrink-0">
                            {model.input_cost_per_million != null && model.output_cost_per_million != null
                              ? `$${model.input_cost_per_million}/$${model.output_cost_per_million}M · `
                              : ''}
                            {model.supports_vision ? 'vision · ' : ''}
                            {Math.round(model.context_window / 1024)}k
                          </span>
                        </div>
                      </button>
                    );
                  })}
                </div>
              ))}

              {/* Local GGUF models */}
              {localModels.filter(m => m.model_type === 'gguf').length > 0 && (
                <>
                  <div className="border-t border-zinc-800 my-1" />
                  <p className="text-[10px] text-zinc-600 font-mono px-3 pt-2 pb-1 uppercase">
                    local
                  </p>
                  {localModels.filter(m => m.model_type === 'gguf').map((model) => {
                    const isActive =
                      modelStatus?.provider === 'local' &&
                      modelStatus.model_name === model.name.replace(/.*\//, '').replace(/\.gguf$/, '');
                    return (
                      <button
                        key={model.path}
                        onClick={() => handleSelectLocal(model)}
                        disabled={!!switching}
                        className={cn(
                          'w-full text-left px-3 py-1.5 text-xs font-mono transition-colors',
                          isActive
                            ? 'text-zinc-200 bg-zinc-800'
                            : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50',
                          switching === model.path && 'opacity-50',
                        )}
                      >
                        <div className="flex justify-between items-center">
                          <span className="truncate mr-2">{model.name}</span>
                          <span className="text-zinc-600 flex-shrink-0">{model.size_display}</span>
                        </div>
                      </button>
                    );
                  })}
                </>
              )}

              {/* MLX models */}
              {localModels.filter(m => m.model_type === 'mlx').length > 0 && (
                <>
                  <div className="border-t border-zinc-800 my-1" />
                  <p className="text-[10px] text-zinc-600 font-mono px-3 pt-2 pb-1 uppercase">
                    mlx
                  </p>
                  {localModels.filter(m => m.model_type === 'mlx').map((model) => {
                    const isActive =
                      modelStatus?.provider === 'local' &&
                      modelStatus.model_name === model.name.replace(/.*\//, '');
                    return (
                      <button
                        key={model.path}
                        onClick={() => handleSelectLocal(model)}
                        disabled={!!switching}
                        className={cn(
                          'w-full text-left px-3 py-1.5 text-xs font-mono transition-colors',
                          isActive
                            ? 'text-zinc-200 bg-zinc-800'
                            : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50',
                          switching === model.path && 'opacity-50',
                        )}
                      >
                        <div className="flex justify-between items-center">
                          <span className="truncate mr-2">{model.name}</span>
                          <span className="text-zinc-600 flex-shrink-0">{model.size_display}</span>
                        </div>
                      </button>
                    );
                  })}
                </>
              )}

              <div className="border-t border-zinc-800 my-2" />
              <div className="px-3 py-2 space-y-2">
                <p className="text-[10px] text-zinc-600 font-mono uppercase">
                  custom openai-compatible
                </p>
                <input
                  value={customProvider.base_url}
                  onChange={(e) => setCustomProvider((p) => ({ ...p, base_url: e.target.value }))}
                  placeholder="http://localhost:1234/v1"
                  className="w-full bg-zinc-950 border border-zinc-800 px-2 py-1 text-xs font-mono text-zinc-300"
                />
                <input
                  value={customProvider.model}
                  onChange={(e) => setCustomProvider((p) => ({ ...p, model: e.target.value }))}
                  placeholder="model slug"
                  className="w-full bg-zinc-950 border border-zinc-800 px-2 py-1 text-xs font-mono text-zinc-300"
                />
                <input
                  value={customProvider.api_key || ''}
                  onChange={(e) => setCustomProvider((p) => ({ ...p, api_key: e.target.value }))}
                  placeholder="api key (optional for local)"
                  type="password"
                  className="w-full bg-zinc-950 border border-zinc-800 px-2 py-1 text-xs font-mono text-zinc-300"
                />
                <div className="grid grid-cols-2 gap-2">
                  <input
                    value={customProvider.context_window}
                    onChange={(e) => setCustomProvider((p) => ({ ...p, context_window: Number(e.target.value) || 32768 }))}
                    type="number"
                    min={4096}
                    className="w-full bg-zinc-950 border border-zinc-800 px-2 py-1 text-xs font-mono text-zinc-300"
                  />
                  <input
                    value={customProvider.max_output_tokens}
                    onChange={(e) => setCustomProvider((p) => ({ ...p, max_output_tokens: Number(e.target.value) || 8192 }))}
                    type="number"
                    min={1024}
                    className="w-full bg-zinc-950 border border-zinc-800 px-2 py-1 text-xs font-mono text-zinc-300"
                  />
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <input
                    value={customProvider.input_cost_per_million ?? ''}
                    onChange={(e) => setCustomProvider((p) => ({
                      ...p,
                      input_cost_per_million: e.target.value === '' ? null : Number(e.target.value),
                    }))}
                    type="number"
                    min={0}
                    step="0.01"
                    placeholder="$ input/M"
                    className="w-full bg-zinc-950 border border-zinc-800 px-2 py-1 text-xs font-mono text-zinc-300"
                  />
                  <input
                    value={customProvider.cached_input_cost_per_million ?? ''}
                    onChange={(e) => setCustomProvider((p) => ({
                      ...p,
                      cached_input_cost_per_million: e.target.value === '' ? null : Number(e.target.value),
                    }))}
                    type="number"
                    min={0}
                    step="0.01"
                    placeholder="$ cache/M"
                    className="w-full bg-zinc-950 border border-zinc-800 px-2 py-1 text-xs font-mono text-zinc-300"
                  />
                  <input
                    value={customProvider.output_cost_per_million ?? ''}
                    onChange={(e) => setCustomProvider((p) => ({
                      ...p,
                      output_cost_per_million: e.target.value === '' ? null : Number(e.target.value),
                    }))}
                    type="number"
                    min={0}
                    step="0.01"
                    placeholder="$ output/M"
                    className="w-full bg-zinc-950 border border-zinc-800 px-2 py-1 text-xs font-mono text-zinc-300"
                  />
                </div>
                <button
                  onClick={handleSelectCustom}
                  disabled={!!switching}
                  className="text-xs font-mono text-cyan-400 hover:text-cyan-300 disabled:text-zinc-600"
                >
                  {switching === 'custom' ? '[connecting...]' : '[use custom provider]'}
                </button>
              </div>
            </>
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
  const showReasoningEffort = !isFireworks && capabilities?.reasoning_effort.supported;
  const showReasoningMaxTokens = providerFamily === 'openrouter' && capabilities?.reasoning_max_tokens.supported;
  const fireworksMode = draft?.fireworks_reasoning_mode ?? 'effort';
  const openRouterMode = draft?.reasoning_max_tokens == null ? 'effort' : 'budget';
  const minFireworksThinkingBudget = 1024;

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
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogHeader>
        <DialogTitle className="font-mono text-sm">Reasoning Settings</DialogTitle>
      </DialogHeader>
      <DialogContent>
        {!draft || !capabilities ? (
          <p className="text-xs text-zinc-500 font-mono">Loading reasoning settings...</p>
        ) : (
          <div className="space-y-4 font-mono text-xs">
            <div className="text-zinc-500">
              <div>{modelName}</div>
              <div className="uppercase text-[10px] mt-1">{providerFamily}</div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <label className="space-y-1">
                <div className="text-zinc-400">max output</div>
                <input
                  type="number"
                  min={1}
                  value={draft.max_output_tokens ?? ''}
                  onChange={(e) => update('max_output_tokens', e.target.value === '' ? null : Number(e.target.value))}
                  className="w-full bg-zinc-950 border border-zinc-800 px-2 py-1 text-zinc-200"
                />
              </label>
              {showReasoningEffort && !showReasoningMaxTokens && (
                <label className="space-y-1">
                  <div className="text-zinc-400">thinking effort</div>
                  <select
                    value={draft.reasoning_effort ?? ''}
                    onChange={(e) => update('reasoning_effort', e.target.value || null)}
                    disabled={!capabilities.reasoning_effort.supported}
                    title={disabledReason(capabilities.reasoning_effort.supported, capabilities.reasoning_effort.reason)}
                    className="w-full bg-zinc-950 border border-zinc-800 px-2 py-1 text-zinc-200 disabled:text-zinc-600"
                  >
                    <option value="">default</option>
                    {(capabilities.reasoning_effort.options.length ? capabilities.reasoning_effort.options : ['low', 'medium', 'high']).map((opt) => (
                      <option key={opt} value={opt}>{opt}</option>
                    ))}
                  </select>
                </label>
              )}
            </div>

            {isFireworks ? (
              <div className="border-t border-zinc-800 pt-3 space-y-3">
                <div className="text-zinc-500 uppercase text-[10px]">Fireworks controls</div>
                <div className="grid grid-cols-2 gap-3">
                  <label className="space-y-1">
                    <div className="text-zinc-400">control</div>
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
                      className="w-full bg-zinc-950 border border-zinc-800 px-2 py-1 text-zinc-200 disabled:text-zinc-600"
                    >
                      <option value="effort">effort-based</option>
                      <option value="thinking">budget-based</option>
                    </select>
                  </label>

                  {fireworksMode === 'effort' ? (
                    <label className="space-y-1">
                      <div className="text-zinc-400">thinking effort</div>
                      <select
                        value={draft.reasoning_effort ?? ''}
                        onChange={(e) => update('reasoning_effort', e.target.value || null)}
                        disabled={!capabilities.reasoning_effort.supported}
                        title={disabledReason(capabilities.reasoning_effort.supported, capabilities.reasoning_effort.reason)}
                        className="w-full bg-zinc-950 border border-zinc-800 px-2 py-1 text-zinc-200 disabled:text-zinc-600"
                      >
                        <option value="">default</option>
                        {(capabilities.reasoning_effort.options.length ? capabilities.reasoning_effort.options : ['low', 'medium', 'high']).map((opt) => (
                          <option key={opt} value={opt}>{opt}</option>
                        ))}
                      </select>
                    </label>
                  ) : (
                    <label className="space-y-1">
                      <div className="text-zinc-400">max thinking tokens</div>
                      <input
                        type="number"
                        min={1024}
                        value={draft.fireworks_thinking_budget_tokens ?? ''}
                        onChange={(e) => update('fireworks_thinking_budget_tokens', e.target.value === '' ? null : Number(e.target.value))}
                        onBlur={(e) => update('fireworks_thinking_budget_tokens', Math.max(Number(e.target.value) || minFireworksThinkingBudget, minFireworksThinkingBudget))}
                        disabled={!capabilities.fireworks_thinking_budget_tokens.supported}
                        title={disabledReason(capabilities.fireworks_thinking_budget_tokens.supported, capabilities.fireworks_thinking_budget_tokens.reason)}
                        className="w-full bg-zinc-950 border border-zinc-800 px-2 py-1 text-zinc-200 disabled:text-zinc-600"
                      />
                    </label>
                  )}
                </div>

                <div className="text-[11px] text-zinc-600">
                  {fireworksMode === 'effort'
                    ? 'Sends reasoning_effort only.'
                    : 'Sends thinking.budget_tokens only.'}
                </div>
              </div>
            ) : (
              showReasoningMaxTokens ? (
                <div className="border-t border-zinc-800 pt-3 space-y-3">
                  <div className="text-zinc-500 uppercase text-[10px]">OpenRouter controls</div>
                  <div className="grid grid-cols-2 gap-3">
                    <label className="space-y-1">
                      <div className="text-zinc-400">control</div>
                      <select
                        value={openRouterMode}
                        onChange={(e) => {
                          if (e.target.value === 'effort') {
                            updateMany({ reasoning_max_tokens: null });
                          } else {
                            updateMany({ reasoning_max_tokens: draft.reasoning_max_tokens ?? 1024 });
                          }
                        }}
                        className="w-full bg-zinc-950 border border-zinc-800 px-2 py-1 text-zinc-200"
                      >
                        <option value="effort">effort-based</option>
                        <option value="budget">budget-based</option>
                      </select>
                    </label>

                    {openRouterMode === 'effort' ? (
                      <label className="space-y-1">
                        <div className="text-zinc-400">thinking effort</div>
                        <select
                          value={draft.reasoning_effort ?? ''}
                          onChange={(e) => update('reasoning_effort', e.target.value || null)}
                          disabled={!capabilities.reasoning_effort.supported}
                          title={disabledReason(capabilities.reasoning_effort.supported, capabilities.reasoning_effort.reason)}
                          className="w-full bg-zinc-950 border border-zinc-800 px-2 py-1 text-zinc-200 disabled:text-zinc-600"
                        >
                          <option value="">default</option>
                          {(capabilities.reasoning_effort.options.length ? capabilities.reasoning_effort.options : ['low', 'medium', 'high']).map((opt) => (
                            <option key={opt} value={opt}>{opt}</option>
                          ))}
                        </select>
                      </label>
                    ) : (
                      <label className="space-y-1">
                        <div className="text-zinc-400">max thinking tokens</div>
                        <input
                          type="number"
                          min={1}
                          value={draft.reasoning_max_tokens ?? ''}
                          onChange={(e) => update('reasoning_max_tokens', e.target.value === '' ? null : Number(e.target.value))}
                          disabled={!capabilities.reasoning_max_tokens.supported}
                          title={disabledReason(capabilities.reasoning_max_tokens.supported, capabilities.reasoning_max_tokens.reason)}
                          className="w-full bg-zinc-950 border border-zinc-800 px-2 py-1 text-zinc-200 disabled:text-zinc-600"
                        />
                      </label>
                    )}
                  </div>
                </div>
              ) : null
            )}

            {!isFireworks && !showReasoningMaxTokens && (
              <div className="text-[11px] text-zinc-600">
                This provider has no separate max thinking token setting.
              </div>
            )}

            <div className="flex justify-end gap-2">
              <button
                onClick={() => onOpenChange(false)}
                className="px-3 py-1 text-zinc-500 hover:text-zinc-300"
              >
                cancel
              </button>
              <button
                onClick={onSave}
                disabled={saving}
                className="px-3 py-1 bg-zinc-200 text-zinc-900 disabled:opacity-60"
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

const RunMessage = memo(function RunMessage({
  run,
  onShowTrace,
  onRetry,
  canRetry,
}: {
  run: Run;
  onShowTrace: () => void;
  onRetry?: () => void;
  canRetry?: boolean;
}) {
  const isRunning = run.status === 'running';
  const finalAnswer = run.final_answer ? extractAnswer(run.final_answer) : '';
  // Use stable selectors - return constant empty string if not found
  const streamingText = useStore((s) => s.streamingText[run.run_id] ?? EMPTY_STRING);
  const streamingThinking = useStore((s) => s.streamingThinking[run.run_id] ?? EMPTY_STRING);

  // Use streaming text while running, final answer when complete
  const displayText = isRunning ? streamingText : finalAnswer;
  const isStreaming = isRunning && streamingText.length > 0;

  // Determine if we're in thinking phase (streaming thinking but no answer yet)
  const isThinking = isRunning && streamingThinking.length > 0;

  return (
    <div className="space-y-4 animate-in fade-in slide-in-from-bottom-2">
      {/* User message */}
      <div className="flex gap-3">
        <div className="flex-shrink-0 w-7 h-7 bg-zinc-700 flex items-center justify-center mt-0.5">
          <span className="text-xs font-mono text-zinc-300">U</span>
        </div>
        <div className="flex-1 min-w-0">
          <div className="bg-zinc-800/50 border border-zinc-800 px-4 py-3">
            <span className="text-zinc-100 whitespace-pre-wrap text-sm leading-relaxed">
              {run.user_message || run.prompt}
            </span>
          </div>
          <p className="text-[11px] text-zinc-600 mt-1.5 px-1">
            {formatRelativeTime(run.created_at)}
          </p>
        </div>
      </div>

      {/* AI response */}
      <div className="flex gap-3 group/msg">
        <div className="flex-shrink-0 w-7 h-7 bg-zinc-800 border border-zinc-700 flex items-center justify-center mt-0.5">
          <span className="text-xs font-mono text-zinc-400">AI</span>
        </div>
        <div className="flex-1 min-w-0">
          <div className="py-2">
            {/* Thinking Panel - shows while thinking or after completion with thinking data */}
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
              <div className="text-sm text-zinc-400">
                [error] {run.error_detail || 'Request failed. Please try again.'}
              </div>
            ) : displayText ? (
              <div>
                <AnswerMarkdown content={extractAnswer(displayText)} />
                {isStreaming && (
                  <span className="inline-block w-2 h-4 bg-zinc-400 animate-pulse ml-0.5" />
                )}
              </div>
            ) : !isThinking ? (
              <div className="text-sm text-zinc-600">No response.</div>
            ) : null}
          </div>

          <div className="mt-2 flex flex-wrap items-center gap-3 font-mono text-xs">
            <button
              onClick={onShowTrace}
              className="text-zinc-600 hover:text-zinc-300 transition-colors"
            >
              [details]
            </button>
            <span className={cn(
              run.status === 'succeeded'
                ? 'text-emerald-600'
                : run.status === 'failed'
                  ? 'text-red-500/70'
                  : 'text-zinc-600'
            )}>
              [{run.status}]
            </span>
            <span className="text-zinc-700">{run.mode || 'chat'}</span>
            {/* Copy / Retry actions - visible on hover */}
            {!isRunning && (
              <MessageActions
                content={finalAnswer || displayText}
                onRetry={onRetry}
                canRetry={canRetry}
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
  entries,
  selectedIndex,
  onSelect,
}: {
  open: boolean;
  loading: boolean;
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
    <div className="absolute left-0 right-0 bottom-full mb-2 border border-zinc-800 bg-zinc-950 shadow-2xl z-20 max-h-64 overflow-y-auto">
      {loading ? (
        <div className="px-3 py-2 text-xs font-mono text-zinc-500">searching files...</div>
      ) : entries.length === 0 ? (
        <div className="px-3 py-2 text-xs font-mono text-zinc-500">no matching files</div>
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
              "block w-full px-3 py-2 text-left font-mono text-xs transition-colors",
              index === selectedIndex
                ? "bg-zinc-800 text-zinc-100"
                : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200"
            )}
          >
            <div className="truncate">{entry.path}</div>
            <div className="truncate text-[10px] text-zinc-600">{entry.name}</div>
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
    <div className="w-full max-w-xl font-mono text-center space-y-6">
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

      <div className="grid grid-cols-3 gap-px border border-zinc-900 bg-zinc-900 text-left">
        <div className="bg-background px-3 py-2">
          <div className="text-[10px] uppercase text-zinc-700">mode</div>
          <div className="truncate text-xs text-zinc-500">{mode}</div>
        </div>
        <div className="bg-background px-3 py-2">
          <div className="text-[10px] uppercase text-zinc-700">workspace</div>
          <div className={cn("truncate text-xs", workspacePath.trim() ? "text-zinc-500" : "text-zinc-700")}>
            {workspaceName}
          </div>
        </div>
        <div className="bg-background px-3 py-2">
          <div className="text-[10px] uppercase text-zinc-700">{provider}</div>
          <div className="truncate text-xs text-zinc-500">{model}</div>
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
  const setRuns = useStore((s) => s.setRuns);
  const updateConversation = useStore((s) => s.updateConversation);
  const addConversation = useStore((s) => s.addConversation);
  const addRun = useStore((s) => s.addRun);
  const removeRun = useStore((s) => s.removeRun);
  const setEvents = useStore((s) => s.setEvents);
  const selectRun = useStore((s) => s.selectRun);
  const setDetailPanelOpen = useStore((s) => s.setDetailPanelOpen);
  const conversation = useSelectedConversation();
  const runs = useConversationRuns(selectedConversationId);
  const terminalState = useConversationTerminal(selectedConversationId);
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
  const [mentionResults, setMentionResults] = useState<WorkspaceFileEntry[]>([]);
  const [mentionOpen, setMentionOpen] = useState(false);
  const [mentionLoading, setMentionLoading] = useState(false);
  const [mentionSelectedIndex, setMentionSelectedIndex] = useState(0);
  const [activeMention, setActiveMention] = useState<{ start: number; end: number; query: string } | null>(null);
  const [permissionPolicy, setPermissionPolicy] = useState<'strict' | 'relaxed' | 'yolo'>(
    () => (localStorage.getItem('reasoner_permission_policy') as 'strict' | 'relaxed' | 'yolo') || 'strict'
  );
  const [isDesktop, setIsDesktop] = useState(
    () => typeof window !== 'undefined' && window.innerWidth >= 768
  );
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Model picker state
  const [modelPickerOpen, setModelPickerOpen] = useState(false);
  const [modelStatus, setModelStatus] = useState<ModelStatus | null>(null);
  const [modelSelectEnabled, setModelSelectEnabled] = useState(false);
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
    const handleResize = () => setIsDesktop(window.innerWidth >= 768);
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // Fetch model status, config, and usage on mount
  useEffect(() => {
    getModelStatus().then(setModelStatus).catch(() => {});
    fetch('/api/config')
      .then((r) => r.json())
      .then((data) => setModelSelectEnabled(data.local_models_enabled ?? false))
      .catch(() => {});
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

  // Track any active run (chat or agent) for UI purposes (auto-scroll, completion detection)
  const activeRunId = useMemo(() => {
    for (let i = runs.length - 1; i >= 0; i -= 1) {
      if (runs[i].status === 'running') {
        return runs[i].run_id;
      }
    }
    return null;
  }, [runs]);

  // Clear queued steers when agent confirms injection via SSE.
  // Delay the clear so the chip is visible briefly before disappearing.
  const activeAgentState = useStore((s) => activeRunId ? s.agentRunState[activeRunId] : undefined);
  const latestContextRun = useMemo(
    () => [...runs].reverse().find((run) => run.mode === 'agent' || !!run.stored_context),
    [runs],
  );
  const lockedWorkspacePath = (conversation?.workspace_path || '').trim();
  const hasConversationWorkspace = lockedWorkspacePath.length > 0;
  const isWorkspaceLocked = selectedConversationId !== null;
  const effectiveWorkspacePath = isWorkspaceLocked ? lockedWorkspacePath : draftWorkspacePath.trim();
  const latestRunStoredContext = latestContextRun?.stored_context as
    | { stored_tokens?: number; utilization_pct?: number; context_window?: number }
    | undefined;
  const footerStoredContext = useMemo(() => {
    return (
      activeAgentState?.stored_context
      ?? latestRunStoredContext
      ?? undefined
    );
  }, [activeAgentState?.stored_context, latestRunStoredContext]);
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
    footerStoredContext?.context_window
    ?? activeAgentState?.context_profile?.context_window
    ?? (latestContextRun?.context_profile as { context_window?: number } | undefined)?.context_window
    ?? modelStatus?.context_window
  );
  const showComposerContextStats = mode === 'agent' && !!composerContextWindow && (
    !!footerStoredContext || conversationRawTokens > 0
  );
  const injectedSteerCount = activeAgentState?.injectedSteers?.length ?? 0;
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
      } catch (error) {
        // Conversation might not exist (deleted) - silently ignore
        console.error('Failed to load conversation:', error);
      }
    }

    loadConversation();
  }, [selectedConversationId, setRuns, updateConversation, subscribe, subscribeAgent]);

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
    if (!scrollRef.current || !activeRunId) return;
    const el = scrollRef.current;
    // Only auto-scroll if user is near the bottom (within 150px)
    const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 150;
    if (isNearBottom) {
      requestAnimationFrame(() => {
        el.scrollTop = el.scrollHeight;
      });
    }
  }, [lastStreamLen, activeAgentScrollSignal, activeRunId]);

  const handleShowTrace = useCallback((runId: string) => {
    selectRun(runId);
    setDetailPanelOpen(true);
  }, [selectRun, setDetailPanelOpen]);

  /** Retry a message: pre-fill the input with the original user message */
  const handleRetry = useCallback((userMessage: string) => {
    if (hasActiveRun) return;
    clearMentionState();
    setMessage(userMessage);
    // Focus the textarea so user can edit before sending
    requestAnimationFrame(() => textareaRef.current?.focus());
  }, [clearMentionState, hasActiveRun]);

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
      setMessage('');
      clearMentionState();
      try {
        await steerAgentRun(activeRunId, steerMsg);
        setQueuedSteers((prev) => [...prev, steerMsg]);
      } catch {
        toast.error('Failed to queue steering message');
        setMessage(steerMsg);
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
          max_steps: 25,
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
      if (apiError.status === 429) {
        toast.error('Message limit reached. You\'ve used all your free messages.');
        refreshUsage();
      } else {
        toast.error('Failed to send message. Please try again.');
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
      return;
    }

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
    } catch (error) {
      console.error('Failed to abort run:', error);
      toast.error('Failed to stop generation.');
      // Even if abort fails, clean up UI state
      setPendingRunId(null);
      setPendingMessage('');
      setPendingIsAgent(false);
      setIsSubmitting(false);
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (mentionOpen) {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setMentionSelectedIndex((prev) => (
          mentionResults.length ? (prev + 1) % mentionResults.length : 0
        ));
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        setMentionSelectedIndex((prev) => (
          mentionResults.length ? (prev - 1 + mentionResults.length) % mentionResults.length : 0
        ));
        return;
      }
      if (e.key === 'Enter' && !e.metaKey && !e.ctrlKey) {
        const entry = mentionResults[mentionSelectedIndex];
        if (entry) {
          e.preventDefault();
          handleMentionSelect(entry);
          return;
        }
      }
      if (e.key === 'Escape') {
        e.preventDefault();
        setMentionOpen(false);
        return;
      }
    }

    // Cmd/Ctrl + Enter to send
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      handleSubmit();
      return;
    }
    // Cmd/Ctrl + 1 for Agent mode
    if (e.key === '1' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      setMode('agent');
      return;
    }
    // Cmd/Ctrl + 2 for Chat mode
    if (e.key === '2' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      setMode('chat');
      return;
    }
  };

  // Determine if we should show Stop button (active run we started)
  const isGenerating = !!pendingRunId;
  const terminalAvailable = !!selectedConversationId && mode === 'agent' && isDesktop;

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
      return;
    }
    const mention = extractActiveMention(value, selectionStart ?? value.length);
    setActiveMention(mention);
    if (!mention) {
      setMentionOpen(false);
    }
  }, [effectiveWorkspacePath, mode]);

  const handleMessageChange = useCallback((e: ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value;
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
    syncMentionState(textarea.value, textarea.selectionStart);
  }, [syncMentionState]);

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
          setMentionOpen(true);
        })
        .catch(() => {
          if (cancelled) return;
          setMentionResults([]);
          setMentionOpen(false);
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

  if (!conversation && runs.length === 0) {
    return (
      <div className="h-full flex flex-col">
        {/* Status bar */}
        <div className="border-b border-zinc-800 px-3 sm:px-4 py-2 flex items-center justify-between bg-transparent font-mono text-xs">
          <div className="flex items-center gap-3">
            {modelSelectEnabled ? (
              <button
                onClick={() => setModelPickerOpen(true)}
                className="text-zinc-600 hover:text-zinc-400 transition-colors"
                title="Switch model"
              >
                {modelStatus?.model_name || 'model'}
                {modelStatus?.context_window ? (
                  <span className="text-zinc-700 ml-1">({Math.round(modelStatus.context_window / 1024)}k)</span>
                ) : null}
                {modelStatus?.provider === 'local' && (
                  <span className="text-zinc-700 ml-1">(local)</span>
                )}
              </button>
            ) : (
              <span className="text-zinc-600">{modelStatus?.model_name || 'model'}{modelStatus?.context_window ? ` (${Math.round(modelStatus.context_window / 1024)}k)` : ''}</span>
            )}
            <span className="text-zinc-700">|</span>
            <button
              onClick={() => setReasoningSettingsOpen(true)}
              className="text-zinc-600 hover:text-zinc-400 transition-colors"
              title="Open reasoning settings"
            >
              reasoning
            </button>
            {mode === 'agent' && isDesktop && (
              <>
                <span className="text-zinc-700">|</span>
                <button
                  onClick={() => void handleOpenTerminal()}
                  className="text-zinc-600 hover:text-zinc-400 transition-colors"
                  title={effectiveWorkspacePath ? 'Open integrated terminal' : 'Select or open a workspace conversation first'}
                >
                  terminal
                </button>
              </>
            )}
          </div>
          <button
            onClick={() => navigate('/benchmarks')}
            className="text-zinc-600 hover:text-zinc-300 transition-colors"
            title="View GAIA benchmark results"
          >
            [benchmarks]
          </button>
        </div>
        {modelSelectEnabled && (
          <ModelPicker
            open={modelPickerOpen}
            onOpenChange={setModelPickerOpen}
            modelStatus={modelStatus}
            onModelStatusChange={setModelStatus}
          />
        )}
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
            rememberWorkspacePath(workspacePath);
            setDraftWorkspacePath(workspacePath);
          }}
        />

        <div className="flex-1 flex flex-col items-center justify-center text-zinc-400 gap-4 sm:gap-6 px-3 sm:px-4 md:px-6 overflow-y-auto min-h-0">
          <EmptyStatePulse
            mode={mode}
            workspacePath={effectiveWorkspacePath}
            modelStatus={modelStatus}
          />
        </div>
        <div className="p-3 pb-[max(1rem,env(safe-area-inset-bottom))] sm:p-4 sm:pb-[max(1rem,env(safe-area-inset-bottom))] flex-shrink-0 space-y-2">
          {/* Prompt area */}
          <div className="relative border border-zinc-700 bg-zinc-900 focus-within:border-zinc-500 transition-colors">
            <div className="flex items-start p-3 gap-2">
              <span className="text-zinc-500 font-mono text-sm mt-0.5 select-none">&gt;</span>
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
                className="flex-1 bg-transparent border-none outline-none resize-none text-sm font-mono text-zinc-100 placeholder:text-zinc-600"
                disabled={isSubmitting || hasActiveRun}
                style={{ maxHeight: '200px' }}
              />
            </div>
            <MentionPicker
              open={mentionOpen}
              loading={mentionLoading}
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
                  className="border border-zinc-800 bg-zinc-900 px-2 py-0.5 text-zinc-500 hover:text-zinc-200"
                  title="Remove image"
                >
                  image {index + 1} ×
                </button>
              ))}
            </div>
          )}
          {/* Toolbar */}
          <div className="flex items-center justify-between px-1">
            <div className="flex items-center gap-3 font-mono text-xs">
              <button
                onClick={() => setMode('agent')}
                className={cn(
                  'transition-colors',
                  mode === 'agent' ? 'text-zinc-200' : 'text-zinc-600 hover:text-zinc-400'
                )}
              >
                agent
              </button>
              <button
                onClick={() => setMode('chat')}
                className={cn(
                  'transition-colors',
                  mode === 'chat' ? 'text-zinc-200' : 'text-zinc-600 hover:text-zinc-400'
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
                        hasConversationWorkspace ? 'text-zinc-400' : 'text-zinc-700'
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
                        className="w-40 sm:w-56 bg-transparent border-none outline-none text-xs font-mono text-zinc-400 placeholder:text-zinc-700"
                        title="Workspace path for filesystem and bash tools"
                      />
                      <button
                        onClick={handleOpenWorkspacePicker}
                        className="text-zinc-600 hover:text-zinc-300 transition-colors"
                        title="Browse local folders"
                      >
                        browse
                      </button>
                    </>
                  )}
                  <select
                    value={permissionPolicy}
                    onChange={(e) => setPermissionPolicy(e.target.value as 'strict' | 'relaxed' | 'yolo')}
                    className="bg-transparent border-none outline-none text-xs font-mono text-zinc-500 cursor-pointer"
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
                  className="text-zinc-500 hover:text-zinc-300 transition-colors"
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
                      : 'text-zinc-400 hover:text-zinc-200'
                  )}
                  title={hasActiveRun ? 'Active run in progress' : undefined}
                >
                  {isSubmitting ? 'sending...' : 'send'}
                </button>
              )}
            </div>
            <div className="flex items-center gap-3 font-mono text-xs text-zinc-600">
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
      <div className="border-b border-zinc-800 px-3 sm:px-4 md:px-6 py-2 flex items-center justify-between font-mono text-xs">
        <div className="flex items-center gap-3 truncate mr-4">
          {modelSelectEnabled ? (
            <>
              <button
                onClick={() => setModelPickerOpen(true)}
                className="text-zinc-600 hover:text-zinc-400 transition-colors flex-shrink-0"
                title="Switch model"
              >
                {modelStatus?.model_name || 'model'}
                {modelStatus?.context_window ? (
                  <span className="text-zinc-700 ml-1">({Math.round(modelStatus.context_window / 1024)}k)</span>
                ) : null}
                {modelStatus?.provider === 'local' && (
                  <span className="text-zinc-700 ml-1">(local)</span>
                )}
              </button>
              <span className="text-zinc-700">|</span>
            </>
          ) : (
            <>
              <span className="text-zinc-600 flex-shrink-0">{modelStatus?.model_name || 'model'}{modelStatus?.context_window ? ` (${Math.round(modelStatus.context_window / 1024)}k)` : ''}</span>
              <span className="text-zinc-700">|</span>
            </>
          )}
          <button
            onClick={() => setReasoningSettingsOpen(true)}
            className="text-zinc-600 hover:text-zinc-400 transition-colors flex-shrink-0"
            title="Open reasoning settings"
          >
            reasoning
          </button>
          <span className="text-zinc-700">|</span>
          <span className="text-zinc-600 truncate">
            {conversation?.title || 'conversation'}
          </span>
        </div>
        <button
          onClick={() => navigate('/benchmarks')}
          className="text-zinc-600 hover:text-zinc-300 transition-colors flex-shrink-0"
          title="View GAIA benchmark results"
        >
          [benchmarks]
        </button>
      </div>
      {modelSelectEnabled && (
        <ModelPicker
          open={modelPickerOpen}
          onOpenChange={setModelPickerOpen}
          modelStatus={modelStatus}
          onModelStatusChange={setModelStatus}
        />
      )}
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
          rememberWorkspacePath(workspacePath);
          setDraftWorkspacePath(workspacePath);
        }}
      />

      <div className="flex-1 overflow-y-auto px-3 sm:px-4 md:px-6 py-4 sm:py-5 md:py-6" ref={scrollRef}>
        <div className="space-y-8">
          {runs.map((run) =>
            run.mode === 'agent' ? (
              <AgentRunMessage
                key={run.run_id}
                run={run}
                onShowTrace={() => handleShowTrace(run.run_id)}
                onRetry={() => handleRetry(run.user_message || run.prompt)}
                canRetry={!hasActiveRun}
              />
            ) : (
              <RunMessage
                key={run.run_id}
                run={run}
                onShowTrace={() => handleShowTrace(run.run_id)}
                onRetry={() => handleRetry(run.user_message || run.prompt)}
                canRetry={!hasActiveRun}
              />
            )
          )}
        </div>
      </div>

      {/* Scroll-to-bottom pill */}
      <ScrollToBottom
        scrollRef={scrollRef}
        isStreaming={!!activeRunId}
        className={cn(
          "left-1/2 -translate-x-1/2",
          terminalAvailable && terminalState?.isOpen
            ? "bottom-[calc(1.5rem+var(--terminal-height,260px))]"
            : "bottom-28"
        )}
      />

      {terminalAvailable && selectedConversationId && (
        <div style={{ ['--terminal-height' as string]: `${terminalState?.height ?? 260}px` }}>
          <IntegratedTerminal
            conversationId={selectedConversationId}
            workspacePath={effectiveWorkspacePath}
            active={terminalAvailable}
          />
        </div>
      )}

      <div className="p-3 pb-[max(1rem,env(safe-area-inset-bottom))] sm:p-4 sm:pb-[max(1rem,env(safe-area-inset-bottom))] flex-shrink-0 space-y-2">
        {/* Queued steering messages */}
        {queuedSteers.length > 0 && (
          <div className="flex flex-wrap gap-1.5 px-1">
            {queuedSteers.map((msg, i) => (
              <span
                key={i}
                className="inline-flex items-center gap-1 px-2 py-0.5 text-[11px] font-mono bg-amber-500/10 text-amber-400/80 border border-amber-500/20"
              >
                <span className="text-amber-500/50">queued:</span> {msg.length > 40 ? msg.slice(0, 40) + '...' : msg}
              </span>
            ))}
          </div>
        )}
        {/* Prompt area */}
        <div className="relative border border-zinc-700 bg-zinc-900 focus-within:border-zinc-500 transition-colors">
          <div className="flex items-start p-3 gap-2">
            <span className="text-zinc-500 font-mono text-sm mt-0.5 select-none">&gt;</span>
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
              className="flex-1 bg-transparent border-none outline-none resize-none text-sm font-mono text-zinc-100 placeholder:text-zinc-600"
              disabled={isSubmitting || atLimit}
              style={{ maxHeight: '200px' }}
            />
          </div>
          <MentionPicker
            open={mentionOpen}
            loading={mentionLoading}
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
                className="border border-zinc-800 bg-zinc-900 px-2 py-0.5 text-zinc-500 hover:text-zinc-200"
                title="Remove image"
              >
                image {index + 1} ×
              </button>
            ))}
          </div>
        )}
        {/* Toolbar */}
        <div className="flex items-center justify-between px-1">
          <div className="flex items-center gap-3 font-mono text-xs">
            <button
              onClick={() => setMode('agent')}
              className={cn(
                'transition-colors',
                mode === 'agent' ? 'text-zinc-200' : 'text-zinc-600 hover:text-zinc-400'
              )}
            >
              agent
            </button>
            <button
              onClick={() => setMode('chat')}
              className={cn(
                'transition-colors',
                mode === 'chat' ? 'text-zinc-200' : 'text-zinc-600 hover:text-zinc-400'
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
                      hasConversationWorkspace ? 'text-zinc-400' : 'text-zinc-700'
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
                      className="w-40 sm:w-56 bg-transparent border-none outline-none text-xs font-mono text-zinc-400 placeholder:text-zinc-700"
                      title="Workspace path for filesystem and bash tools"
                    />
                    <button
                      onClick={handleOpenWorkspacePicker}
                      className="text-zinc-600 hover:text-zinc-300 transition-colors"
                      title="Browse local folders"
                    >
                      browse
                    </button>
                  </>
                )}
                <select
                  value={permissionPolicy}
                  onChange={(e) => setPermissionPolicy(e.target.value as 'strict' | 'relaxed' | 'yolo')}
                  className="bg-transparent border-none outline-none text-xs font-mono text-zinc-500 cursor-pointer"
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
                className="text-zinc-500 hover:text-zinc-300 transition-colors"
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
                  className="text-zinc-500 hover:text-zinc-300 transition-colors"
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
                      : 'text-zinc-400 hover:text-zinc-200'
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
                  ctx {footerStoredContext ? `${Math.round(footerStoredContext.utilization_pct ?? 0)}%` : '—'}
                </span>
                <span className="text-zinc-600">
                  {footerStoredContext && composerContextWindow
                    ? `${formatContextTokens(footerStoredContext.stored_tokens ?? 0)}/${formatContextTokens(composerContextWindow)}`
                    : '—'}
                </span>
                <span className="text-zinc-500">
                  raw {conversationRawTokens > 0 ? formatContextTokens(conversationRawTokens) : '—'}
                </span>
              </>
            )}
          </div>
          <div className="flex items-center gap-3 font-mono text-xs text-zinc-600">
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
  );
}
