// Conversation view - simple chat interface

import { useEffect, useMemo, useRef, useState, useCallback, memo } from 'react';
import type { KeyboardEvent } from 'react';
import { useNavigate } from 'react-router-dom';
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
import { Eye, Loader2, Send, Square, Globe, MessageSquare, Sparkles, BarChart3, ChevronRight } from 'lucide-react';
import type { Run, Conversation, ReasoningEffort } from '@/types';

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
      <div className="flex justify-end">
        <div className="max-w-[95%] sm:max-w-[85%] md:max-w-[80%] lg:max-w-[70%] rounded-2xl bg-blue-600 text-white px-4 py-3 shadow-sm">
          <p className="text-sm leading-relaxed whitespace-pre-wrap">
            {run.user_message || run.prompt}
          </p>
          <p className="text-[11px] text-blue-100 mt-2 text-right">
            {formatRelativeTime(run.created_at)}
          </p>
        </div>
      </div>

      <div className="flex justify-start">
        <div className="max-w-full sm:max-w-[90%] md:max-w-[88%] lg:max-w-[80%] rounded-2xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
          {/* Thinking Panel - shows while thinking or after completion with thinking data */}
          <ThinkingPanel
            summary={run.thinking_summary}
            isStreaming={isThinking}
            streamingContent={streamingThinking}
            defaultExpanded={false}
          />

          {isRunning && !displayText && !streamingThinking ? (
            <div className="flex items-center gap-2 text-sm text-slate-500">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading...
            </div>
          ) : run.status === 'failed' ? (
            <div className="text-sm text-rose-600">
              {run.error_detail || 'Request failed. Please try again.'}
            </div>
          ) : displayText ? (
            <div>
              <AnswerMarkdown content={extractAnswer(displayText)} />
              {isStreaming && (
                <span className="inline-block w-2 h-4 bg-slate-400 animate-pulse ml-0.5" />
              )}
            </div>
          ) : !isThinking ? (
            <div className="text-sm text-slate-500">No response.</div>
          ) : null}

          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Button size="sm" variant="ghost" onClick={onShowTrace}>
              <Eye className="h-4 w-4" />
              Details
            </Button>
            <span className={cn(
              'text-xs px-2 py-0.5 rounded-full',
              run.status === 'succeeded'
                ? 'bg-emerald-100 text-emerald-700'
                : run.status === 'failed'
                  ? 'bg-rose-100 text-rose-700'
                  : 'bg-slate-100 text-slate-600'
            )}>
              {run.status}
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

  // Stop generation state
  const [pendingMessage, setPendingMessage] = useState('');
  const [pendingRunId, setPendingRunId] = useState<string | null>(null);
  const [pendingIsAgent, setPendingIsAgent] = useState(false);

  const activeRunId = useMemo(() => {
    for (let i = runs.length - 1; i >= 0; i -= 1) {
      if (runs[i].status === 'running') {
        return runs[i].run_id;
      }
    }
    return null;
  }, [runs]);

  // Get subscribe/unsubscribe functions from useSSE (chat mode)
  const { subscribe, unsubscribe } = useSSE(activeRunId);

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

        // Auto-reconnect to any active runs after page reload
        // This handles the case where user refreshes during an ongoing run
        for (const run of data.runs) {
          if (run.status === 'running') {
            if (run.mode === 'agent') {
              // Reconnect to agent SSE stream with sinceSeq=0 to replay all events
              console.log('[Auto-reconnect] Reconnecting to agent run:', run.run_id);
              subscribeAgent(run.run_id, 0);
            } else {
              // Reconnect to chat SSE stream
              console.log('[Auto-reconnect] Reconnecting to chat run:', run.run_id);
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

  useEffect(() => {
    if (!scrollRef.current) return;
    scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [runs.length]);

  const handleShowTrace = useCallback((runId: string) => {
    selectRun(runId);
    setDetailPanelOpen(true);
  }, [selectRun, setDetailPanelOpen]);

  const handleSubmit = async () => {
    if (!message.trim() || isSubmitting) return;

    // Block new conversation creation if there's an active run (prevents queue overflow)
    // This only blocks UI - API/curl can still create conversations for testing
    if (!selectedConversationId && hasActiveRun) {
      console.warn('Blocked new conversation: active run in progress');
      return;
    }

    const messageToSend = message.trim();
    setIsSubmitting(true);
    setPendingMessage(messageToSend);
    setMessage('');
    setPendingIsAgent(mode === 'research');
    let conversationId = selectedConversationId;

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
        // Navigate to the new conversation URL
        navigate(`/conversations/${conversationId}`);
      }

      if (mode === 'research') {
        // Research mode: use agent API
        const response = await createAgentRun({
          query: messageToSend,
          conversation_id: conversationId!,
          max_steps: 10,
        });

        setPendingRunId(response.run_id);

        // Subscribe to agent SSE stream
        subscribeAgent(response.run_id);

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
      }
    } catch (error) {
      console.error('Failed to create run:', error);
      // Restore message on error
      setMessage(messageToSend);
      setPendingMessage('');
      setPendingRunId(null);
      setPendingIsAgent(false);
      setIsSubmitting(false);
      return;
    }
  };

  // Handle stream completion - clear pending state
  useEffect(() => {
    if (pendingRunId && activeRunId !== pendingRunId) {
      // The run we started is no longer active (completed or failed)
      setPendingMessage('');
      setPendingRunId(null);
      setPendingIsAgent(false);
      setIsSubmitting(false);
    }
  }, [activeRunId, pendingRunId]);

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

  // Determine if we should show Stop button
  const isGenerating = isSubmitting && pendingRunId;

  const handlePresetClick = (query: string) => {
    setMessage(query);
    setMode('research'); // Preset questions are designed for research mode
  };

  if (!conversation && runs.length === 0) {
    return (
      <div className="h-full flex flex-col">
        {/* Top banner with benchmarks link */}
        <div className="border-b px-3 sm:px-4 py-2 flex items-center justify-end bg-gradient-to-r from-transparent to-slate-50">
          <button
            onClick={() => navigate('/benchmarks')}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-full bg-gradient-to-r from-blue-500 to-blue-600 hover:from-blue-600 hover:to-blue-700 text-white shadow-sm hover:shadow-md transition-all duration-200"
            title="View GAIA benchmark results"
          >
            <BarChart3 className="h-3.5 w-3.5" />
            <span className="font-semibold">Benchmarks</span>
            <ChevronRight className="h-3.5 w-3.5" />
          </button>
        </div>

        <div className="flex-1 flex flex-col items-center justify-center text-slate-500 gap-4 sm:gap-6 px-3 sm:px-4 md:px-6">
          <div className="text-center">
            <h2 className="text-lg font-semibold text-slate-700 mb-2">
              {mode === 'research' ? 'Agent Mode' : 'Chat Mode'}
            </h2>
            <p className="text-sm">
              {mode === 'research'
                ? 'Ask complex questions requiring multi-step research'
                : 'Have a conversation with reasoning-capable AI'}
            </p>
          </div>

          {/* Preset Questions - only show in agent mode */}
          {mode === 'research' && (
            <div className="w-full max-w-2xl">
              <div className="flex items-center gap-2 mb-3">
                <Sparkles className="h-4 w-4 text-indigo-500" />
                <span className="text-xs font-medium text-slate-600">Try these examples</span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {PRESET_QUESTIONS.map((preset) => (
                  <button
                    key={preset.label}
                    onClick={() => handlePresetClick(preset.query)}
                    className="px-3 py-2 text-xs rounded-lg border border-slate-200 bg-white hover:bg-indigo-50 hover:border-indigo-300 hover:text-indigo-700 transition-colors text-slate-600 text-left"
                    title={preset.query}
                  >
                    {preset.label}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
        <div className="border-t p-3 sm:p-4">
          <div className="flex flex-col sm:flex-row gap-2 sm:gap-3">
            <Textarea
              placeholder={mode === 'research' ? 'Ask agent to research...' : 'Ask a question...'}
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              onKeyDown={handleKeyDown}
              rows={3}
              className="resize-none flex-1"
              disabled={isSubmitting}
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
                    mode === 'research' && 'bg-indigo-600 hover:bg-indigo-700'
                  )}
                  onClick={() => setMode('research')}
                  title="Research mode"
                >
                  <Globe className="h-4 w-4" />
                </Button>
                <Button
                  size="sm"
                  variant={mode === 'chat' ? 'default' : 'outline'}
                  className="flex-1 sm:flex-initial sm:h-8 sm:px-2 h-9 min-w-[36px] px-2"
                  onClick={() => setMode('chat')}
                  title="Chat mode"
                >
                  <MessageSquare className="h-4 w-4" />
                </Button>
              </div>
              {/* Reasoning effort - only show in chat mode */}
              {mode === 'chat' && (
                <select
                  value={reasoningEffort}
                  onChange={(e) => setReasoningEffort(e.target.value as ReasoningEffort)}
                  className="h-9 sm:h-8 px-2 text-xs border border-slate-200 rounded-md bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                  title="Reasoning effort: how deeply the model thinks"
                >
                  <option value="low">⚡ Low</option>
                  <option value="medium">🧠 Medium</option>
                  <option value="high">🔬 High</option>
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
                      mode === 'research' ? 'bg-indigo-600 hover:bg-indigo-700' : ''
                    )}
                  >
                    {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                  </Button>
                </span>
              )}
            </div>
          </div>
          <p className="text-xs text-slate-500 mt-2">
            {hasActiveRun
              ? '⏳ Waiting for active run to complete...'
              : mode === 'research'
                ? '🌐 Agent mode: web search + analysis'
                : reasoningEffort === 'high'
                  ? '🔬 Deep reasoning'
                  : reasoningEffort === 'medium'
                    ? '🧠 Balanced'
                    : '⚡ Fast'}
            <span className="hidden md:inline">
              {' '}· Press ⌘/Ctrl+Enter to send · ⌘/Ctrl+1 for Agent · ⌘/Ctrl+2 for Chat
            </span>
          </p>
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
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-full bg-gradient-to-r from-blue-500 to-blue-600 hover:from-blue-600 hover:to-blue-700 text-white shadow-sm hover:shadow-md transition-all duration-200"
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

      <div className="border-t p-3 sm:p-4">
        <div className="flex flex-col sm:flex-row gap-2 sm:gap-3">
          <Textarea
            placeholder={mode === 'research' ? 'Ask agent to research...' : 'Ask a follow-up question...'}
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={3}
            className="resize-none flex-1"
            disabled={isSubmitting}
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
                  mode === 'research' && 'bg-indigo-600 hover:bg-indigo-700'
                )}
                onClick={() => setMode('research')}
                title="Research mode"
              >
                <Globe className="h-4 w-4" />
              </Button>
              <Button
                size="sm"
                variant={mode === 'chat' ? 'default' : 'outline'}
                className="flex-1 sm:flex-initial sm:h-8 sm:px-2 h-9 min-w-[36px] px-2"
                onClick={() => setMode('chat')}
                title="Chat mode"
              >
                <MessageSquare className="h-4 w-4" />
              </Button>
            </div>
            {/* Reasoning effort - only show in chat mode */}
            {mode === 'chat' && (
              <select
                value={reasoningEffort}
                onChange={(e) => setReasoningEffort(e.target.value as ReasoningEffort)}
                className="h-9 sm:h-8 px-2 text-xs border border-slate-200 rounded-md bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                title="Reasoning effort: how deeply the model thinks"
              >
                <option value="low">⚡ Low</option>
                <option value="medium">🧠 Medium</option>
                <option value="high">🔬 High</option>
              </select>
            )}
            {isGenerating ? (
              <Button onClick={handleStop} variant="destructive" className="h-9 sm:h-auto min-w-[36px] px-2">
                <Square className="h-4 w-4 fill-current" />
              </Button>
            ) : (
              <Button
                onClick={handleSubmit}
                disabled={!message.trim() || isSubmitting}
                className={cn(
                  'h-9 sm:h-auto min-w-[36px] px-2',
                  mode === 'research' ? 'bg-indigo-600 hover:bg-indigo-700' : ''
                )}
              >
                {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              </Button>
            )}
          </div>
        </div>
        <p className="text-xs text-slate-500 mt-2">
          {mode === 'research'
            ? '🌐 Agent mode: web search + analysis'
            : reasoningEffort === 'high'
              ? '🔬 Deep reasoning'
              : reasoningEffort === 'medium'
                ? '🧠 Balanced'
                : '⚡ Fast'}
          <span className="hidden md:inline">
            {' '}· Press ⌘/Ctrl+Enter to send · ⌘/Ctrl+1 for Agent · ⌘/Ctrl+2 for Chat
          </span>
        </p>
      </div>
    </div>
  );
}
