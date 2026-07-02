/**
 * Model picker dialog (provider rail + model catalog + auth/key management).
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import {
  cancelChatGPTLogin,
  cancelGrokLogin,
  clearProviderKey,
  getChatGPTLoginUrl,
  listLocalModels,
  listProviderKeys,
  listRegistryModels,
  logoutChatGPT,
  logoutGrok,
  saveProviderKey,
  selectModel,
  startGrokLogin,
  startLocalModel,
  stopLocalModel,
  submitGrokLoginCode,
  ApiError,
} from '@/api/client';
import type {
  LocalModel,
  ModelStatus,
  ProviderKeyStatus,
  RegistryModelPreset,
  RegistryModelsResponse,
} from '@/api/client';
import {
  Dialog,
  DialogHeader,
  DialogTitle,
  DialogContent,
} from '@/components/ui/dialog';
import { isLocalDesktopApp, openExternalUrl } from '@/lib/platform';
import { formatContextTokens } from '@/lib/runFormat';
import { cn } from '@/lib/utils';
import type { ConversationModelSelection } from '@/types';

type ChatGPTLoginState = {
  loginUrl: string;
  status: 'waiting' | 'timed_out';
};

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
export function ModelPicker({
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
