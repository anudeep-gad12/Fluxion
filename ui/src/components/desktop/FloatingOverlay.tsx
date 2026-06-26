import { useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent, type ClipboardEvent, type KeyboardEvent } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { toast } from 'sonner';
import { Brain, Camera, ChevronDown, X } from 'lucide-react';
import { AgentRunMessage } from '@/components/AgentRunMessage';
import { ImagePreviewStrip } from '@/components/ImagePreviewStrip';
import { ReasoningSettingsDialog } from '@/components/ConversationView';
import { DesktopComposer } from '@/components/desktop/DesktopComposer';
import {
  createAgentRun,
  createConversation,
  cancelAgentRun,
  getModelStatus,
  getReasoningSettings,
  listRegistryModels,
  selectModel,
  updateReasoningSettings,
  type ModelStatus,
  type RegistryModelPreset,
  type RegistryModelsResponse,
  type ReasoningSettings,
  type ReasoningSettingsResponse,
} from '@/api/client';
import { useAgentSSE } from '@/hooks/useAgentSSE';
import { useStore, useHasActiveRun } from '@/hooks/useStore';
import type { ConversationModelSelection, ImageAttachment, Run } from '@/types';
import { cn } from '@/lib/utils';

const MAX_IMAGE_ATTACHMENTS = 20;
const MAX_IMAGE_BYTES = 20 * 1024 * 1024;
const OVERLAY_METADATA = { surface: 'floating_overlay' };
const CONVERSATION_MODEL_METADATA_KEY = 'model_selection';

type CapturePayload = {
  name: string;
  mime_type: string;
  data_url: string;
};

function attachmentFromCapture(capture: CapturePayload): ImageAttachment {
  return {
    id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
    name: capture.name || 'screenshot.png',
    mime_type: capture.mime_type || 'image/png',
    data_url: capture.data_url,
  };
}

export function FloatingOverlay() {
  const search = new URLSearchParams(window.location.search);
  const nonce = search.get('nonce') || '';
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const threadRef = useRef<HTMLDivElement | null>(null);
  const threadBottomRef = useRef<HTMLDivElement | null>(null);

  const [homeDir, setHomeDir] = useState('');
  const [message, setMessage] = useState('');
  const [imageAttachments, setImageAttachments] = useState<ImageAttachment[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [activeRun, setActiveRun] = useState<Run | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [capturing, setCapturing] = useState(false);
  const [modelPickerOpen, setModelPickerOpen] = useState(false);
  const [registryModels, setRegistryModels] = useState<RegistryModelsResponse | null>(null);
  const [modelPickerLoading, setModelPickerLoading] = useState(false);
  const [modelStatus, setModelStatus] = useState<ModelStatus | null>(null);
  const [activeModelSelection, setActiveModelSelection] = useState<ConversationModelSelection | null>(null);
  const [reasoningSettingsOpen, setReasoningSettingsOpen] = useState(false);
  const [reasoningSettings, setReasoningSettings] = useState<ReasoningSettingsResponse | null>(null);
  const [reasoningDraft, setReasoningDraft] = useState<ReasoningSettings | null>(null);
  const [reasoningSaving, setReasoningSaving] = useState(false);
  const [permissionPolicy] = useState<'strict' | 'relaxed' | 'yolo'>('relaxed');
  const [collaborationMode] = useState<'default' | 'plan'>('default');

  const addConversation = useStore((s) => s.addConversation);
  const setRuns = useStore((s) => s.setRuns);
  const addRun = useStore((s) => s.addRun);
  const updateRun = useStore((s) => s.updateRun);
  const hasActiveRun = useHasActiveRun();
  const liveAgentState = useStore((s) => (activeRunId ? s.agentRunState[activeRunId] : undefined));
  const { subscribe } = useAgentSSE(null);

  const refreshReasoningSettings = useCallback(async () => {
    try {
      const settings = await getReasoningSettings();
      setReasoningSettings(settings);
      setReasoningDraft(settings.settings);
    } catch {
      setReasoningSettings(null);
      setReasoningDraft(null);
    }
  }, []);

  const refreshModelStatus = useCallback(async () => {
    try {
      const status = await getModelStatus();
      setModelStatus(status);
    } catch {
      setModelStatus(null);
    }
  }, []);

  useEffect(() => {
    void invoke<string>('fluxion_home_dir')
      .then(setHomeDir)
      .catch(() => setHomeDir(''));
    void refreshModelStatus();
    void refreshReasoningSettings();
  }, [refreshModelStatus, refreshReasoningSettings]);

  const resetDraft = useCallback(() => {
    setMessage('');
    setImageAttachments([]);
    setConversationId(null);
    setActiveRunId(null);
    setActiveRun(null);
    window.setTimeout(() => textareaRef.current?.focus(), 50);
  }, []);

  useEffect(() => {
    resetDraft();
  }, [nonce, resetDraft]);

  const addAttachment = useCallback((attachment: ImageAttachment) => {
    setImageAttachments((prev) => [attachment, ...prev].slice(0, MAX_IMAGE_ATTACHMENTS));
  }, []);

  const captureArea = useCallback(async () => {
    if (capturing) return;
    setCapturing(true);
    try {
      const capture = await invoke<CapturePayload | null>('fluxion_capture_area');
      if (capture) {
        addAttachment(attachmentFromCapture(capture));
      }
    } catch (error) {
      toast.error((error as { message?: string })?.message || 'Screenshot failed');
    } finally {
      setCapturing(false);
      void invoke('fluxion_show_floating_overlay', { capture: false }).catch(() => undefined);
      window.setTimeout(() => textareaRef.current?.focus(), 50);
    }
  }, [addAttachment, capturing]);

  const handlePaste = useCallback((event: ClipboardEvent<HTMLTextAreaElement>) => {
    const files = Array.from(event.clipboardData.files).filter((file) => (
      file.type === 'image/png' || file.type === 'image/jpeg' || file.type === 'image/webp'
    ));
    if (!files.length) return;
    event.preventDefault();

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
        addAttachment({
          id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
          name: file.name || 'pasted-image.png',
          mime_type: file.type,
          data_url: String(reader.result || ''),
        });
      };
      reader.readAsDataURL(file);
    });
  }, [addAttachment, imageAttachments.length]);

  const removeImageAttachment = useCallback((id?: string) => {
    setImageAttachments((prev) => prev.filter((attachment) => attachment.id !== id));
  }, []);

  const refreshRegistryModels = useCallback(async () => {
    setModelPickerLoading(true);
    try {
      setRegistryModels(await listRegistryModels());
    } catch {
      setRegistryModels(null);
      toast.error('Failed to load models');
    } finally {
      setModelPickerLoading(false);
    }
  }, []);

  const handleSelectFloatingModel = useCallback(async (provider: string, model: RegistryModelPreset) => {
    try {
      await selectModel({ provider, model_id: model.model_id });
      const status = await getModelStatus();
      const selection: ConversationModelSelection = {
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
      setModelStatus(status);
      setActiveModelSelection(selection);
      setModelPickerOpen(false);
      void refreshReasoningSettings();
    } catch (error) {
      toast.error((error as { message?: string })?.message || 'Failed to switch model');
    }
  }, [refreshReasoningSettings]);

  const openFloatingModelPicker = useCallback(() => {
    setModelPickerOpen((open) => {
      const next = !open;
      if (next && !registryModels && !modelPickerLoading) {
        void refreshRegistryModels();
      }
      return next;
    });
  }, [modelPickerLoading, refreshRegistryModels, registryModels]);

  const handleSaveReasoningSettings = useCallback(async () => {
    if (!reasoningDraft) return;
    setReasoningSaving(true);
    try {
      const response = await updateReasoningSettings(reasoningDraft);
      setReasoningSettings(response);
      setReasoningDraft(response.settings);
      void refreshModelStatus();
      toast.success('Reasoning settings updated');
    } catch (error) {
      toast.error((error as { message?: string })?.message || 'Failed to update reasoning settings');
    } finally {
      setReasoningSaving(false);
    }
  }, [reasoningDraft, refreshModelStatus]);

  const handleSubmit = useCallback(async () => {
    if ((!message.trim() && imageAttachments.length === 0) || isSubmitting) return;
    if (!homeDir) {
      toast.error('Home directory not available');
      return;
    }
    if (imageAttachments.length > 0 && !modelStatus?.supports_vision) {
      toast.error('Active model does not support images. Select a vision model.');
      return;
    }
    const text = message.trim() || 'Please analyze the attached image.';
    const attachmentsToSend = imageAttachments.map(({ name, mime_type, data_url }) => ({
      name,
      mime_type,
      data_url,
    }));

    setIsSubmitting(true);
    setMessage('');
    setImageAttachments([]);
    try {
      let nextConversationId = conversationId;
      if (!nextConversationId) {
        const response = await createConversation({
          title: 'Floating chat',
          workspace_path: homeDir,
          metadata: activeModelSelection
            ? { ...OVERLAY_METADATA, [CONVERSATION_MODEL_METADATA_KEY]: activeModelSelection }
            : { ...OVERLAY_METADATA },
        });
        nextConversationId = response.conversation_id;
        setConversationId(nextConversationId);
        addConversation({
          conversation_id: nextConversationId,
          created_at: new Date().toISOString(),
          title: 'Floating chat',
          summary: '',
          workspace_path: homeDir,
          status: 'active',
          metadata: activeModelSelection
            ? { ...OVERLAY_METADATA, [CONVERSATION_MODEL_METADATA_KEY]: activeModelSelection }
            : { ...OVERLAY_METADATA },
        });
        setRuns(nextConversationId, []);
      }

      const response = await createAgentRun(
        {
          query: text,
          image_attachments: attachmentsToSend,
          conversation_id: nextConversationId!,
          max_steps: 1000,
          workspace_path: homeDir,
          filesystem_enabled: true,
          permission_policy: permissionPolicy,
          collaboration_mode: collaborationMode,
          capabilities: {
            web: true,
            filesystem: true,
            command: true,
            python: false,
          },
        },
        activeModelSelection,
      );

      const run: Run = {
        run_id: response.run_id,
        created_at: new Date().toISOString(),
        status: 'running',
        mode: 'agent',
        profile: 'agent',
        prompt: text,
        user_message: text,
        conversation_id: nextConversationId,
        image_attachments: attachmentsToSend.map((attachment, index) => ({
          id: `${response.run_id}-${index}`,
          name: attachment.name,
          mime_type: attachment.mime_type,
          data_url: attachment.data_url,
        })),
      };
      setActiveRunId(response.run_id);
      setActiveRun(run);
      addRun(nextConversationId!, run);
      localStorage.setItem(`stream_token:${response.run_id}`, response.stream_token);
      subscribe(response.run_id, 0, response.stream_token);
    } catch (error) {
      toast.error((error as { message?: string })?.message || 'Failed to start agent');
      setMessage(text);
      setImageAttachments(imageAttachments);
    } finally {
      setIsSubmitting(false);
      window.setTimeout(() => textareaRef.current?.focus(), 50);
    }
  }, [
    activeModelSelection,
    addConversation,
    addRun,
    collaborationMode,
    conversationId,
    homeDir,
    imageAttachments,
    isSubmitting,
    message,
    modelStatus?.supports_vision,
    permissionPolicy,
    setRuns,
    subscribe,
  ]);

  const currentRun = useMemo(() => {
    if (!activeRunId || !activeRun) return null;
    const storeRuns = conversationId ? useStore.getState().runsByConversation[conversationId] : null;
    return storeRuns?.find((run) => run.run_id === activeRunId) || activeRun;
  }, [activeRun, activeRunId, conversationId, hasActiveRun]);

  const scrollThreadToBottom = useCallback((behavior: ScrollBehavior = 'smooth') => {
    window.requestAnimationFrame(() => {
      threadBottomRef.current?.scrollIntoView({ block: 'end', behavior });
    });
  }, []);

  useEffect(() => {
    if (!currentRun) return;
    scrollThreadToBottom(currentRun.status === 'running' ? 'smooth' : 'auto');
  }, [
    currentRun,
    liveAgentState?.answerBuffer,
    liveAgentState?.assistantUpdates.length,
    liveAgentState?.currentStep,
    liveAgentState?.steps.length,
    liveAgentState?.thinkingBuffer,
    liveAgentState?.toolCalls.length,
    scrollThreadToBottom,
  ]);

  useEffect(() => {
    if (!activeRunId) return;
    const interval = window.setInterval(() => {
      const storeRun = conversationId
        ? useStore.getState().runsByConversation[conversationId]?.find((run) => run.run_id === activeRunId)
        : null;
      if (storeRun && storeRun.status !== activeRun?.status) {
        setActiveRun(storeRun);
      }
    }, 500);
    return () => window.clearInterval(interval);
  }, [activeRun?.status, activeRunId, conversationId]);

  const isGenerating = activeRun?.status === 'running';
  const currentModelName = activeModelSelection?.display_name
    || modelStatus?.model_name?.split('/').pop()
    || modelStatus?.model_name
    || 'Model';
  const currentProviderName = activeModelSelection?.provider || modelStatus?.provider || 'provider';
  const modelChoices = useMemo(() => {
    if (!registryModels) return [];
    return Object.entries(registryModels.providers)
      .filter(([, provider]) => provider.available)
      .flatMap(([provider, providerData]) => providerData.models
        .filter((model) => model.supports_tools)
        .map((model) => ({
          provider,
          providerLabel: providerData.display_name || provider,
          model,
          active: (
            (activeModelSelection?.provider || registryModels.active_provider || modelStatus?.provider) === provider
            && (activeModelSelection?.model_id || registryModels.active_model_id || modelStatus?.model_name) === model.model_id
          ),
        })));
  }, [activeModelSelection, modelStatus, registryModels]);

  const attachmentsRow = imageAttachments.length > 0 ? (
    <ImagePreviewStrip
      images={imageAttachments}
      onRemove={removeImageAttachment}
      className="px-1"
      thumbnailClassName="h-14 w-14"
    />
  ) : null;

  const controlsRow = (
    <div className="floating-overlay-controls desktop-no-drag">
      <button
        type="button"
        onClick={openFloatingModelPicker}
        className="floating-model-trigger"
        title={`${currentProviderName} · ${currentModelName}`}
      >
        <span className="truncate">{currentModelName}</span>
        <span className="floating-model-provider-name">{currentProviderName}</span>
        <ChevronDown className={cn('h-3.5 w-3.5 shrink-0 transition-transform', modelPickerOpen && 'rotate-180')} />
      </button>
      {modelPickerOpen ? (
        <div className="floating-model-picker">
          {modelPickerLoading ? (
            <div className="floating-model-empty">Loading models…</div>
          ) : modelChoices.length > 0 ? (
            modelChoices.map(({ provider, providerLabel, model, active }) => (
              <button
                key={`${provider}:${model.model_id}`}
                type="button"
                onClick={() => void handleSelectFloatingModel(provider, model)}
                className={cn('floating-model-option', active && 'is-active')}
              >
                <span className="floating-model-option-main">
                  <span className="truncate">{model.display_name || model.model_id}</span>
                  {model.supports_vision ? <span className="floating-model-pill">vision</span> : null}
                </span>
                <span className="floating-model-option-sub">{providerLabel}</span>
              </button>
            ))
          ) : (
            <div className="floating-model-empty">No available agent models</div>
          )}
        </div>
      ) : null}
      <button
        type="button"
        onClick={() => setReasoningSettingsOpen(true)}
        className="desktop-icon-btn shrink-0"
        title="Reasoning settings"
        aria-label="Reasoning settings"
      >
        <Brain className="h-3.5 w-3.5" />
      </button>
      <button
        type="button"
        onClick={() => void captureArea()}
        disabled={capturing || isGenerating}
        className={cn('desktop-icon-btn shrink-0', capturing && 'opacity-60')}
        title="Capture screen area"
        aria-label="Capture screen area"
      >
        <Camera className="h-3.5 w-3.5" />
      </button>
    </div>
  );

  const handleKeyDown = useCallback((event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      void handleSubmit();
    }
    if (event.key === 'Escape' && !message.trim() && imageAttachments.length === 0) {
      void invoke('fluxion_hide_floating_overlay');
    }
  }, [handleSubmit, imageAttachments.length, message]);

  return (
    <div className="floating-overlay-root">
      <div className="floating-overlay-card">
        <header className="floating-overlay-header" data-tauri-drag-region>
          <div className="flex min-w-0 items-center gap-2">
            <span className="floating-overlay-dot" aria-hidden />
            <span className="truncate text-[13px] font-medium text-zinc-300">Fluxion</span>
            <span className="truncate text-[11px] text-zinc-600">{homeDir || 'Home'}</span>
          </div>
          <div className="desktop-no-drag flex items-center gap-1">
            <button
              type="button"
              onClick={resetDraft}
              className="floating-overlay-action"
            >
              New Chat
            </button>
            <button
              type="button"
              onClick={() => void invoke('fluxion_hide_floating_overlay')}
              className="floating-overlay-close"
              aria-label="Close"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        </header>

        <main className="floating-overlay-thread" ref={threadRef}>
          {capturing ? (
            <div className="floating-overlay-hint">Drag an area to attach a screenshot…</div>
          ) : currentRun ? (
            <AgentRunMessage run={currentRun} />
          ) : (
            <div className="floating-overlay-hint">Ask Fluxion anything. This agent starts in your Home folder.</div>
          )}
          <div ref={threadBottomRef} aria-hidden className="h-px" />
        </main>

        <div className="floating-overlay-composer">
          <DesktopComposer
            mode="agent"
            onModeChange={() => undefined}
            workspaceLabel="Home"
            workspaceTitle={homeDir}
            textareaRef={textareaRef}
            message={message}
            placeholder={capturing ? 'Select a screen area…' : 'What can I help you with today?'}
            disabled={isSubmitting}
            atLimit={false}
            isSubmitting={isSubmitting}
            isGenerating={isGenerating}
            canSteerActiveRun={false}
            hasActiveRun={isGenerating}
            stoppingRunId={null}
            onChange={(event: ChangeEvent<HTMLTextAreaElement>) => setMessage(event.target.value)}
            onPaste={handlePaste}
            onKeyDown={handleKeyDown}
            onSelect={() => undefined}
            onClick={() => undefined}
            onSubmit={() => void handleSubmit()}
            onStop={() => {
              if (activeRunId) {
                void cancelAgentRun(activeRunId).catch(() => undefined);
                updateRun(activeRunId, { status: 'cancelled' });
              }
            }}
            mentionPicker={null}
            attachmentsRow={attachmentsRow}
            controlsRow={controlsRow}
          />
        </div>
      </div>

      <ReasoningSettingsDialog
        open={reasoningSettingsOpen}
        onOpenChange={setReasoningSettingsOpen}
        settingsResponse={reasoningSettings}
        draft={reasoningDraft}
        onDraftChange={setReasoningDraft}
        onSave={handleSaveReasoningSettings}
        saving={reasoningSaving}
      />
    </div>
  );
}
