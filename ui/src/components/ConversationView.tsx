// Conversation view - simple chat interface

import { useEffect, useMemo, useRef, useState, useCallback, memo } from 'react';
import type { KeyboardEvent, ChangeEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { AnswerMarkdown, extractAnswer } from '@/components/AnswerMarkdown';
import { ThinkingPanel } from '@/components/ThinkingPanel';
import { AgentRunMessage } from '@/components/AgentRunMessage';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import {
  createConversation,
  createConversationRun,
  getConversation,
  abortRun,
  createAgentRun,
  cancelAgentRun,
} from '@/api/client';
import { useConversationRuns, useSelectedConversation, useStore, useHasActiveRun } from '@/hooks/useStore';
import { useSSE } from '@/hooks/useSSE';
import { useAgentSSE } from '@/hooks/useAgentSSE';
import { cn, formatRelativeTime } from '@/lib/utils';
import { Loader2, Send, Square, Globe, MessageSquare, Sparkles, BarChart3, ChevronRight } from 'lucide-react';
import type { Run, Conversation, ReasoningEffort } from '@/types';

/** Maximum characters allowed in the input textarea (~2000 tokens) */
const MAX_INPUT_CHARS = 8000;

/** Preset questions showcasing multi-step agentic research capabilities */
const PRESET_QUESTIONS = [
  {
    label: 'Hypothetical: Smaller hearts',
    query: 'What if humans have smaller hearts?',
  },
  {
    label: 'Last 3 Nobel Prizes',
    query: 'Who won the Nobel Prize in Physics for the last 3 years, what are their names and what topics did they receive it for?',
  },
  {
    label: 'Birth rate declines',
    query: 'What are the birth rate declines in recent years and what are the main causes?',
  },
  {
    label: 'Top 5 tallest buildings',
    query: 'What are the top 5 tallest buildings in the world, their heights, and how do they compare?',
  },
];

/** Mode: 'chat' for regular conversation, 'research' for agent */
type ChatMode = 'chat' | 'research';

// Empty string constant to avoid creating new references
const EMPTY_STRING = '';

const RunMessage = memo(function RunMessage({
  run,
  onShowTrace,
}: {
  run: Run;
  onShowTrace: () => void;
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
    <div className="space-y-3 animate-in fade-in slide-in-from-bottom-2">
      <div className="w-full">
        <div className="w-full py-2">
          <span className="text-zinc-500 mr-2 select-none font-mono">{'>'}</span>
          <span className="text-zinc-100 whitespace-pre-wrap text-sm leading-relaxed">
            {run.user_message || run.prompt}
          </span>
          <p className="text-[11px] text-zinc-600 mt-2 text-left">
            {formatRelativeTime(run.created_at)}
          </p>
        </div>
      </div>

      <div className="w-full">
        <div className="w-full py-2 pl-4 border-l border-zinc-800">
          {/* Thinking Panel - shows while thinking or after completion with thinking data */}
          <ThinkingPanel
            summary={run.thinking_summary}
            isStreaming={isThinking}
            streamingContent={streamingThinking}
            defaultExpanded={false}
          />

          {isRunning && !displayText && !streamingThinking ? (
            <div className="text-xs text-zinc-500 font-mono">
              [loading...]
            </div>
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

          <div className="mt-3 flex flex-wrap items-center gap-3 font-mono text-xs">
            <button
              onClick={onShowTrace}
              className="text-zinc-500 hover:text-zinc-300"
            >
              [details]
            </button>
            <span className={cn(
              run.status === 'succeeded'
                ? 'text-zinc-500'
                : run.status === 'failed'
                  ? 'text-zinc-500'
                  : 'text-zinc-600'
            )}>
              [{run.status}]
            </span>
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
          max_steps: 10,
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
        {/* Top banner with benchmarks link */}
        <div className="border-b border-border px-3 sm:px-4 py-2 flex items-center justify-end bg-transparent">
          <button
            onClick={() => navigate('/benchmarks')}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-none bg-zinc-800 border border-zinc-600 text-zinc-300 hover:bg-zinc-700 hover:text-zinc-100 shadow-none transition-all duration-200"
            title="View GAIA benchmark results"
          >
            <BarChart3 className="h-3.5 w-3.5" />
            <span className="font-semibold">Benchmarks</span>
            <ChevronRight className="h-3.5 w-3.5" />
          </button>
        </div>

        <div className="flex-1 flex flex-col items-center justify-center text-zinc-400 gap-4 sm:gap-6 px-3 sm:px-4 md:px-6 overflow-y-auto min-h-0">
          <div className="text-center">
            <h2 className="text-lg font-semibold text-zinc-100 mb-2">
              {mode === 'research' ? 'Agent Mode' : 'Chat Mode'}
            </h2>
            <p className="text-sm">
              {mode === 'research'
                ? 'Ask complex questions requiring multi-step research'
                : 'Have a conversation with reasoning-capable AI'}
            </p>
            {mode === 'research' && (
              <p className="text-xs text-zinc-600 mt-1">
                120B open-weight MoE · web search · content extraction · code execution
              </p>
            )}
          </div>

          {/* Preset Questions - only show in agent mode */}
          {mode === 'research' && (
            <div className="w-full max-w-2xl">
              <div className="flex items-center gap-2 mb-3">
                <Sparkles className="h-4 w-4 text-zinc-400" />
                <span className="text-xs font-medium text-zinc-500">Try these examples</span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {PRESET_QUESTIONS.map((preset) => (
                  <button
                    key={preset.label}
                    onClick={() => handlePresetClick(preset.query)}
                    className="px-3 py-2 text-xs rounded-none border border-zinc-700 bg-transparent hover:bg-zinc-800 hover:border-zinc-500 hover:text-zinc-100 transition-colors text-zinc-400 text-left"
                    title={preset.query}
                  >
                    {preset.label}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
        <div className="border-t p-3 pb-20 sm:p-4 flex-shrink-0 bg-background">
          <div className="flex flex-col sm:flex-row gap-2 sm:gap-3">
            <Textarea
              ref={textareaRef}
              placeholder={mode === 'research' ? 'Ask agent to research...' : 'Ask a question...'}
              value={message}
              onChange={handleMessageChange}
              onKeyDown={handleKeyDown}
              rows={2}
              className="resize-none flex-1"
              disabled={isSubmitting || hasActiveRun}
            />
            <div className="flex gap-2 sm:flex-col sm:gap-2 sm:self-end">
              {/* Mode toggle - horizontal on mobile, vertical on desktop */}
              <div className="flex gap-1 flex-1 sm:flex-initial">
                <Button
                  size="sm"
                  variant={mode === 'research' ? 'default' : 'outline'}
                  className={cn(
                    'flex-1 sm:flex-initial sm:h-8 sm:px-2',
                    'h-9 min-w-[36px] px-2',
                    mode === 'research' && 'bg-zinc-100 text-zinc-900 hover:bg-zinc-200'
                  )}
                  onClick={() => setMode('research')}
                  title="Research mode"
                >
                  <Globe className="h-4 w-4" />
                  <span className="hidden sm:inline ml-1">Agent</span>
                </Button>
                <Button
                  size="sm"
                  variant={mode === 'chat' ? 'default' : 'outline'}
                  className="flex-1 sm:flex-initial sm:h-8 sm:px-2 h-9 min-w-[36px] px-2"
                  onClick={() => setMode('chat')}
                  title="Chat mode"
                >
                  <MessageSquare className="h-4 w-4" />
                  <span className="hidden sm:inline ml-1">Chat</span>
                </Button>
              </div>
              {/* Reasoning effort - only show in chat mode */}
              {mode === 'chat' && (
                <select
                  value={reasoningEffort}
                  onChange={(e) => setReasoningEffort(e.target.value as ReasoningEffort)}
                  className="h-9 sm:h-8 px-2 text-xs border border-zinc-700 rounded-none bg-zinc-900 text-zinc-300 focus:outline-none focus:ring-2 focus:ring-zinc-500"
                  title="Reasoning effort: how deeply the model thinks"
                >
                  <option value="low">fast</option>
                  <option value="medium">balanced</option>
                  <option value="high">deep</option>
                </select>
              )}
              {isGenerating ? (
                <Button onClick={handleStop} variant="destructive" className="h-9 sm:h-auto min-w-[36px] px-2">
                  <Square className="h-4 w-4 fill-current" />
                </Button>
              ) : (
                <span title={hasActiveRun ? 'Active run in progress — cannot start new conversation until complete' : undefined}>
                  <Button
                    onClick={handleSubmit}
                    disabled={!message.trim() || isSubmitting || hasActiveRun}
                    className={cn(
                      'h-9 sm:h-auto min-w-[36px] px-2',
                      mode === 'research' ? '' : ''
                    )}
                  >
                    {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                  </Button>
                </span>
              )}
            </div>
          </div>
          <div className="flex items-center justify-between mt-2">
            <p className="text-xs text-zinc-500">
              {hasActiveRun
                ? 'waiting for active run...'
                : mode === 'research'
                  ? '> agent mode'
                  : reasoningEffort === 'high'
                    ? '> deep reasoning'
                    : reasoningEffort === 'medium'
                      ? '> balanced'
                      : '> fast'}
              <span className="hidden md:inline text-zinc-600">
                {' · ⌘+Enter send · ⌘+1 agent · ⌘+2 chat'}
              </span>
            </p>
            <span className={cn(
              'text-xs',
              message.length > MAX_INPUT_CHARS * 0.9 ? 'text-zinc-400' : 'text-zinc-600'
            )}>
              {message.length.toLocaleString()}/{MAX_INPUT_CHARS.toLocaleString()}
            </span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      <div className="border-b px-3 sm:px-4 md:px-6 py-3 sm:py-4 flex items-center justify-between">
        <h2 className="text-base sm:text-lg font-semibold">
          {conversation?.title || 'Conversation'}
        </h2>
        <button
          onClick={() => navigate('/benchmarks')}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-none bg-zinc-800 border border-zinc-600 text-zinc-300 hover:bg-zinc-700 hover:text-zinc-100 shadow-none transition-all duration-200"
          title="View GAIA benchmark results"
        >
          <BarChart3 className="h-3.5 w-3.5" />
          <span className="font-semibold">Benchmarks</span>
          <ChevronRight className="h-3.5 w-3.5" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-3 sm:px-4 md:px-6 py-4 sm:py-5 md:py-6" ref={scrollRef}>
        <div className="space-y-8">
          {runs.map((run) =>
            run.mode === 'agent' ? (
              <AgentRunMessage
                key={run.run_id}
                run={run}
                onShowTrace={() => handleShowTrace(run.run_id)}
              />
            ) : (
              <RunMessage
                key={run.run_id}
                run={run}
                onShowTrace={() => handleShowTrace(run.run_id)}
              />
            )
          )}
        </div>
      </div>

      <div className="border-t p-3 pb-20 sm:p-4 flex-shrink-0 bg-background">
        <div className="flex flex-col sm:flex-row gap-2 sm:gap-3">
          <Textarea
            ref={textareaRef}
            placeholder={mode === 'research' ? 'Ask agent to research...' : 'Ask a follow-up question...'}
            value={message}
            onChange={handleMessageChange}
            onKeyDown={handleKeyDown}
            rows={2}
            className="resize-none flex-1"
            disabled={isSubmitting || hasActiveRun}
          />
          <div className="flex gap-2 sm:flex-col sm:gap-2 sm:self-end">
            {/* Mode toggle - horizontal on mobile, vertical on desktop */}
            <div className="flex gap-1 flex-1 sm:flex-initial">
              <Button
                size="sm"
                variant={mode === 'research' ? 'default' : 'outline'}
                className={cn(
                  'flex-1 sm:flex-initial sm:h-8 sm:px-2',
                  'h-9 min-w-[36px] px-2',
                  mode === 'research' && 'bg-zinc-100 text-zinc-900 hover:bg-zinc-200'
                )}
                onClick={() => setMode('research')}
                title="Research mode"
              >
                <Globe className="h-4 w-4" />
                <span className="hidden sm:inline ml-1">Agent</span>
              </Button>
              <Button
                size="sm"
                variant={mode === 'chat' ? 'default' : 'outline'}
                className="flex-1 sm:flex-initial sm:h-8 sm:px-2 h-9 min-w-[36px] px-2"
                onClick={() => setMode('chat')}
                title="Chat mode"
              >
                <MessageSquare className="h-4 w-4" />
                <span className="hidden sm:inline ml-1">Chat</span>
              </Button>
            </div>
            {/* Reasoning effort - only show in chat mode */}
            {mode === 'chat' && (
              <select
                value={reasoningEffort}
                onChange={(e) => setReasoningEffort(e.target.value as ReasoningEffort)}
                className="h-9 sm:h-8 px-2 text-xs border border-zinc-700 rounded-none bg-zinc-900 text-zinc-300 focus:outline-none focus:ring-2 focus:ring-zinc-500"
                title="Reasoning effort: how deeply the model thinks"
              >
                <option value="low">fast</option>
                <option value="medium">balanced</option>
                <option value="high">deep</option>
              </select>
            )}
            {isGenerating ? (
              <Button onClick={handleStop} variant="destructive" className="h-9 sm:h-auto min-w-[36px] px-2">
                <Square className="h-4 w-4 fill-current" />
              </Button>
            ) : (
              <Button
                onClick={handleSubmit}
                disabled={!message.trim() || isSubmitting || hasActiveRun}
                className={cn(
                  'h-9 sm:h-auto min-w-[36px] px-2',
                  mode === 'research' ? '' : ''
                )}
              >
                {(isSubmitting || hasActiveRun) ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              </Button>
            )}
          </div>
        </div>
        <div className="flex items-center justify-between mt-2">
          <p className="text-xs text-zinc-500">
            {hasActiveRun
              ? '> waiting for active run...'
              : mode === 'research'
                ? '> agent mode'
                : reasoningEffort === 'high'
                  ? '> deep reasoning'
                  : reasoningEffort === 'medium'
                    ? '> balanced'
                    : '> fast'}
            <span className="hidden md:inline text-zinc-600">
              {' · ⌘+Enter send · ⌘+1 agent · ⌘+2 chat'}
            </span>
          </p>
          <span className={cn(
            'text-xs',
            message.length > MAX_INPUT_CHARS * 0.9 ? 'text-zinc-400' : 'text-zinc-600'
          )}>
            {message.length.toLocaleString()}/{MAX_INPUT_CHARS.toLocaleString()}
          </span>
        </div>
      </div>
    </div>
  );
}
