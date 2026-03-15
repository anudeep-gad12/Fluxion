// Conversation view - simple chat interface

import { useEffect, useMemo, useRef, useState, useCallback, memo } from 'react';
import type { KeyboardEvent, ChangeEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { AnswerMarkdown, extractAnswer } from '@/components/AnswerMarkdown';
import { ThinkingPanel } from '@/components/ThinkingPanel';
import { AgentRunMessage } from '@/components/AgentRunMessage';
import { MessageActions } from '@/components/MessageActions';
import { ShimmerSkeleton, ThinkingTimer } from '@/components/StreamingIndicator';
import { ScrollToBottom } from '@/components/ScrollToBottom';
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
  listRegistryModels,
  selectModel,
} from '@/api/client';
import type { LocalModel, ModelStatus, RegistryModelPreset, RegistryModelsResponse } from '@/api/client';
import {
  Dialog,
  DialogHeader,
  DialogTitle,
  DialogContent,
} from '@/components/ui/dialog';
import { useConversationRuns, useSelectedConversation, useStore, useHasActiveRun } from '@/hooks/useStore';
import { useSSE } from '@/hooks/useSSE';
import { useAgentSSE } from '@/hooks/useAgentSSE';
import { cn, formatRelativeTime } from '@/lib/utils';
import type { Run, Conversation, ReasoningEffort } from '@/types';

/** Maximum characters allowed in the input textarea (~2000 tokens) */
const MAX_INPUT_CHARS = 8000;

/** Preset questions showcasing multi-step agentic research capabilities */
const PRESET_QUESTIONS = [
  {
    label: "What's the total mass of all humans versus all ants?",
    query: "What's the total mass of all humans alive today versus all ants, and which weighs more?",
  },
  {
    label: 'How long to watch every Oscar Best Picture winner back to back?',
    query: 'How long would it take to watch every movie that won Best Picture at the Oscars back to back?',
  },
  {
    label: '$1,000 in Apple, Google, Amazon 10 years ago — worth today?',
    query: 'If you invested $1,000 in Apple, Google, and Amazon 10 years ago, how much would each be worth today?',
  },
  {
    label: 'How many soccer fields to cover the entire EU?',
    query: 'How many soccer fields would it take to cover the surface area of every country in the EU?',
  },
];

/** Mode: 'chat' for regular conversation, 'research' for agent */
type ChatMode = 'chat' | 'research';

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
      setError('Failed to start model. Check logs/llama.log');
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
                            {Math.round(model.context_window / 1024)}k
                          </span>
                        </div>
                      </button>
                    );
                  })}
                </div>
              ))}

              {/* Local models */}
              {localModels.length > 0 && (
                <>
                  <div className="border-t border-zinc-800 my-1" />
                  <p className="text-[10px] text-zinc-600 font-mono px-3 pt-2 pb-1 uppercase">
                    local
                  </p>
                  {localModels.map((model) => {
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
            </>
          )}
        </div>
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
  const hasActiveRun = useHasActiveRun();
  const [message, setMessage] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [reasoningEffort, setReasoningEffort] = useState<ReasoningEffort>('medium');
  const [mode, setMode] = useState<ChatMode>('research');
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Model picker state
  const [modelPickerOpen, setModelPickerOpen] = useState(false);
  const [modelStatus, setModelStatus] = useState<ModelStatus | null>(null);
  const [modelSelectEnabled, setModelSelectEnabled] = useState(false);
  // Fetch model status and config on mount
  useEffect(() => {
    getModelStatus().then(setModelStatus).catch(() => {});
    fetch('/api/config')
      .then((r) => r.json())
      .then((data) => setModelSelectEnabled(data.local_models_enabled ?? false))
      .catch(() => {});
  }, []);

  // Stop generation state
  const [pendingMessage, setPendingMessage] = useState('');
  // Track run IDs we already subscribed to in handleSubmit, so
  // loadConversation doesn't open a second EventSource for the same run.
  const subscribedRunRef = useRef<string | null>(null);
  const [pendingRunId, setPendingRunId] = useState<string | null>(null);
  const [pendingIsAgent, setPendingIsAgent] = useState(false);

  // Track any active run (chat or agent) for UI purposes (auto-scroll, completion detection)
  const activeRunId = useMemo(() => {
    for (let i = runs.length - 1; i >= 0; i -= 1) {
      if (runs[i].status === 'running') {
        return runs[i].run_id;
      }
    }
    return null;
  }, [runs]);

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

  // Get subscribe/unsubscribe functions from useAgentSSE (research mode)
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

  useEffect(() => {
    if (!scrollRef.current || !activeRunId) return;
    const el = scrollRef.current;
    // Only auto-scroll if user is near the bottom (within 150px)
    const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 150;
    if (isNearBottom) {
      el.scrollTop = el.scrollHeight;
    }
  }, [lastStreamLen, activeRunId]);

  const handleShowTrace = useCallback((runId: string) => {
    selectRun(runId);
    setDetailPanelOpen(true);
  }, [selectRun, setDetailPanelOpen]);

  /** Retry a message: pre-fill the input with the original user message */
  const handleRetry = useCallback((userMessage: string) => {
    if (hasActiveRun) return;
    setMessage(userMessage);
    // Focus the textarea so user can edit before sending
    requestAnimationFrame(() => textareaRef.current?.focus());
  }, [hasActiveRun]);

  const handleSubmit = async () => {
    if (!message.trim() || isSubmitting || hasActiveRun) return;

    const messageToSend = message.trim();
    setIsSubmitting(true);
    setPendingMessage(messageToSend);
    setMessage('');
    setPendingIsAgent(mode === 'research');
    let conversationId = selectedConversationId;

    // Track whether we need to navigate after setup (deferred to prevent
    // useEffect from re-subscribing while handleSubmit is still in flight)
    let needsNavigate = false;

    try {
      // Create conversation if needed
      if (!conversationId) {
        const response = await createConversation();
        conversationId = response.conversation_id;
        const newConversation: Conversation = {
          conversation_id: conversationId,
          created_at: new Date().toISOString(),
          title: messageToSend.slice(0, 64),
          summary: '',
          status: 'active',
          metadata: {},
        };
        addConversation(newConversation);
        setRuns(conversationId, []);
        needsNavigate = true;
      }

      if (mode === 'research') {
        // Research mode: use agent API
        const response = await createAgentRun({
          query: messageToSend,
          conversation_id: conversationId!,
          max_steps: 25,
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
          reasoning_effort: reasoningEffort,
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
    } catch (error) {
      console.error('Failed to create run:', error);
      toast.error('Failed to send message. Please try again.');
      // Restore message on error
      setMessage(messageToSend);
      setPendingMessage('');
      setPendingRunId(null);
      setPendingIsAgent(false);
      setIsSubmitting(false);
      return;
    }
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
      subscribedRunRef.current = null;
    }
  }, [selectedConversationId, activeRunId, pendingRunId]);

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
    // Cmd/Ctrl + Enter to send
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      handleSubmit();
      return;
    }
    // Cmd/Ctrl + 1 for Agent mode
    if (e.key === '1' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      setMode('research');
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

  // Auto-resize textarea
  const resizeTextarea = useCallback(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    ta.style.height = Math.min(ta.scrollHeight, 200) + 'px';
  }, []);

  const handleMessageChange = useCallback((e: ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value;
    // Enforce character limit
    if (value.length <= MAX_INPUT_CHARS) {
      setMessage(value);
    }
    // Resize on next frame after state update
    requestAnimationFrame(resizeTextarea);
  }, [resizeTextarea]);

  // Reset textarea height when message is cleared (after submit)
  useEffect(() => {
    if (!message && textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  }, [message]);

  const handlePresetClick = (query: string) => {
    setMessage(query);
    setMode('research'); // Preset questions are designed for research mode
    requestAnimationFrame(resizeTextarea);
  };

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
                {modelStatus?.provider === 'local' && (
                  <span className="text-zinc-700 ml-1">(local)</span>
                )}
              </button>
            ) : (
              <span className="text-zinc-600">{modelStatus?.model_name || 'model'}</span>
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

        <div className="flex-1 flex flex-col items-center justify-center text-zinc-400 gap-4 sm:gap-6 px-3 sm:px-4 md:px-6 overflow-y-auto min-h-0">
          <div className="font-mono text-center">
            <p className="text-sm text-zinc-500">
              <span className="text-zinc-700">───</span> {mode === 'research' ? 'agent' : 'chat'} <span className="text-zinc-700">───</span>
            </p>
            <p className="text-xs text-zinc-600 mt-1">
              {mode === 'research'
                ? 'web search · content extraction · code execution'
                : 'reasoning-capable conversation'}
            </p>
          </div>

          {/* Preset Questions - only show in agent mode */}
          {mode === 'research' && (
            <div className="w-full max-w-xl font-mono">
              <p className="text-xs text-zinc-700 mb-2">~ examples</p>
              <div className="space-y-0.5 border-l border-zinc-800 ml-1">
                {PRESET_QUESTIONS.map((preset) => (
                  <button
                    key={preset.label}
                    onClick={() => handlePresetClick(preset.query)}
                    className="block w-full px-3 py-1 text-xs text-zinc-600 hover:text-zinc-300 hover:bg-zinc-800/50 transition-colors text-left font-mono"
                    title={preset.query}
                  >
                    {preset.label}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
        <div className="p-3 pb-[max(1rem,env(safe-area-inset-bottom))] sm:p-4 sm:pb-[max(1rem,env(safe-area-inset-bottom))] flex-shrink-0 space-y-2">
          {/* Prompt area */}
          <div className="border border-zinc-700 bg-zinc-900 focus-within:border-zinc-500 transition-colors">
            <div className="flex items-start p-3 gap-2">
              <span className="text-zinc-500 font-mono text-sm mt-0.5 select-none">&gt;</span>
              <textarea
                ref={textareaRef}
                placeholder={mode === 'research' ? 'Ask agent to research...' : 'Ask a question...'}
                value={message}
                onChange={handleMessageChange}
                onKeyDown={handleKeyDown}
                rows={2}
                className="flex-1 bg-transparent border-none outline-none resize-none text-sm font-mono text-zinc-100 placeholder:text-zinc-600"
                disabled={isSubmitting || hasActiveRun}
                style={{ maxHeight: '200px' }}
              />
            </div>
          </div>
          {/* Toolbar */}
          <div className="flex items-center justify-between px-1">
            <div className="flex items-center gap-3 font-mono text-xs">
              <button
                onClick={() => setMode('research')}
                className={cn(
                  'transition-colors',
                  mode === 'research' ? 'text-zinc-200' : 'text-zinc-600 hover:text-zinc-400'
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
              {mode === 'chat' && (
                <select
                  value={reasoningEffort}
                  onChange={(e) => setReasoningEffort(e.target.value as ReasoningEffort)}
                  className="bg-transparent border-none outline-none text-xs font-mono text-zinc-500 cursor-pointer"
                  title="Reasoning effort"
                >
                  <option value="low">fast</option>
                  <option value="medium">balanced</option>
                  <option value="high">deep</option>
                </select>
              )}
              <span className="text-zinc-700">|</span>
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
                {modelStatus?.provider === 'local' && (
                  <span className="text-zinc-700 ml-1">(local)</span>
                )}
              </button>
              <span className="text-zinc-700">|</span>
            </>
          ) : (
            <>
              <span className="text-zinc-600 flex-shrink-0">{modelStatus?.model_name || 'model'}</span>
              <span className="text-zinc-700">|</span>
            </>
          )}
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
        className="left-1/2 -translate-x-1/2 bottom-28"
      />

      <div className="p-3 pb-[max(1rem,env(safe-area-inset-bottom))] sm:p-4 sm:pb-[max(1rem,env(safe-area-inset-bottom))] flex-shrink-0 space-y-2">
        {/* Prompt area */}
        <div className="border border-zinc-700 bg-zinc-900 focus-within:border-zinc-500 transition-colors">
          <div className="flex items-start p-3 gap-2">
            <span className="text-zinc-500 font-mono text-sm mt-0.5 select-none">&gt;</span>
            <textarea
              ref={textareaRef}
              placeholder={mode === 'research' ? 'Ask agent to research...' : 'Ask a follow-up question...'}
              value={message}
              onChange={handleMessageChange}
              onKeyDown={handleKeyDown}
              rows={2}
              className="flex-1 bg-transparent border-none outline-none resize-none text-sm font-mono text-zinc-100 placeholder:text-zinc-600"
              disabled={isSubmitting || hasActiveRun}
              style={{ maxHeight: '200px' }}
            />
          </div>
        </div>
        {/* Toolbar */}
        <div className="flex items-center justify-between px-1">
          <div className="flex items-center gap-3 font-mono text-xs">
            <button
              onClick={() => setMode('research')}
              className={cn(
                'transition-colors',
                mode === 'research' ? 'text-zinc-200' : 'text-zinc-600 hover:text-zinc-400'
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
            {mode === 'chat' && (
              <select
                value={reasoningEffort}
                onChange={(e) => setReasoningEffort(e.target.value as ReasoningEffort)}
                className="bg-transparent border-none outline-none text-xs font-mono text-zinc-500 cursor-pointer"
                title="Reasoning effort"
              >
                <option value="low">fast</option>
                <option value="medium">balanced</option>
                <option value="high">deep</option>
              </select>
            )}
            <span className="text-zinc-700">|</span>
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
