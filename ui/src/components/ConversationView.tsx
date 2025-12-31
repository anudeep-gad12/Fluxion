// Conversation view - simple chat interface

import { useEffect, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent } from 'react';
import { AnswerMarkdown, extractAnswer } from '@/components/AnswerMarkdown';
import { ThinkingPanel } from '@/components/ThinkingPanel';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { createConversation, createConversationRun, getConversation } from '@/api/client';
import { useConversationRuns, useSelectedConversation, useStore } from '@/hooks/useStore';
import { useSSE } from '@/hooks/useSSE';
import { cn, formatRelativeTime } from '@/lib/utils';
import { Eye, Loader2, Send } from 'lucide-react';
import type { Run, Conversation, ReasoningEffort } from '@/types';

function RunMessage({
  run,
  onShowTrace,
}: {
  run: Run;
  onShowTrace: () => void;
}) {
  const isRunning = run.status === 'running';
  const finalAnswer = run.final_answer ? extractAnswer(run.final_answer) : '';
  const streamingText = useStore((s) => s.streamingText[run.run_id] || '');
  const streamingThinking = useStore((s) => s.streamingThinking[run.run_id] || '');

  // Debug logging for streaming state
  if (isRunning) {
    console.log('[RunMessage] Streaming state:', {
      run_id: run.run_id,
      streamingText_len: streamingText.length,
      streamingThinking_len: streamingThinking.length,
      streamingThinking_preview: streamingThinking.slice(0, 50),
    });
  }

  // Use streaming text while running, final answer when complete
  const displayText = isRunning ? streamingText : finalAnswer;
  const isStreaming = isRunning && streamingText.length > 0;

  // Determine if we're in thinking phase (streaming thinking but no answer yet)
  const isThinking = isRunning && streamingThinking.length > 0;

  return (
    <div className="space-y-3 animate-in fade-in slide-in-from-bottom-2">
      <div className="flex justify-end">
        <div className="max-w-[70%] rounded-2xl bg-blue-600 text-white px-4 py-3 shadow-sm">
          <p className="text-sm leading-relaxed whitespace-pre-wrap">
            {run.user_message || run.prompt}
          </p>
          <p className="text-[11px] text-blue-100 mt-2 text-right">
            {formatRelativeTime(run.created_at)}
          </p>
        </div>
      </div>

      <div className="flex justify-start">
        <div className="max-w-[80%] rounded-2xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
          {/* Thinking Panel - shows while thinking or after completion with thinking data */}
          <ThinkingPanel
            summary={run.thinking_summary}
            steps={run.thinking_steps}
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
}

export function ConversationView() {
  const selectedConversationId = useStore((s) => s.selectedConversationId);
  const setRuns = useStore((s) => s.setRuns);
  const updateConversation = useStore((s) => s.updateConversation);
  const addConversation = useStore((s) => s.addConversation);
  const selectConversation = useStore((s) => s.selectConversation);
  const addRun = useStore((s) => s.addRun);
  const setEvents = useStore((s) => s.setEvents);
  const selectRun = useStore((s) => s.selectRun);
  const setDetailPanelOpen = useStore((s) => s.setDetailPanelOpen);
  const conversation = useSelectedConversation();
  const runs = useConversationRuns(selectedConversationId);
  const [message, setMessage] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [reasoningEffort, setReasoningEffort] = useState<ReasoningEffort>('medium');
  const scrollRef = useRef<HTMLDivElement>(null);

  const activeRunId = useMemo(() => {
    for (let i = runs.length - 1; i >= 0; i -= 1) {
      if (runs[i].status === 'running') {
        return runs[i].run_id;
      }
    }
    return null;
  }, [runs]);

  // Get subscribe function from useSSE - we'll call it manually on run creation
  // to avoid race condition where events are emitted before React re-renders
  const { subscribe } = useSSE(activeRunId);

  useEffect(() => {
    if (!selectedConversationId) return;

    async function loadConversation() {
      try {
        const data = await getConversation(selectedConversationId!);
        updateConversation(selectedConversationId!, data.conversation);
        setRuns(selectedConversationId!, data.runs);
      } catch (error) {
        console.error('Failed to load conversation:', error);
      }
    }

    loadConversation();
  }, [selectedConversationId, setRuns, updateConversation]);

  useEffect(() => {
    if (!scrollRef.current) return;
    scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [runs.length]);

  const handleShowTrace = (runId: string) => {
    selectRun(runId);
    setDetailPanelOpen(true);
  };

  const handleSubmit = async () => {
    if (!message.trim() || isSubmitting) return;

    setIsSubmitting(true);
    let conversationId = selectedConversationId;

    try {
      if (!conversationId) {
        const response = await createConversation();
        conversationId = response.conversation_id;
        const newConversation: Conversation = {
          conversation_id: conversationId,
          created_at: new Date().toISOString(),
          title: message.trim().slice(0, 64),
          summary: '',
          status: 'active',
          metadata: {},
        };
        addConversation(newConversation);
        selectConversation(conversationId);
        setRuns(conversationId, []);
      }

      const response = await createConversationRun(conversationId!, {
        message: message.trim(),
        reasoning_effort: reasoningEffort,
      });

      // CRITICAL: Subscribe to SSE IMMEDIATELY after getting run_id
      // This prevents race condition where events are emitted before frontend subscribes
      // (Phase 1 thinking tokens were being lost while waiting for React re-render)
      subscribe(response.run_id);

      const run: Run = {
        run_id: response.run_id,
        created_at: new Date().toISOString(),
        status: 'running',
        mode: 'system',
        profile: 'lmstudio',
        prompt: message.trim(),
        user_message: message.trim(),
        conversation_id: conversationId!,
        conversation_summary: conversation?.summary || '',
      };

      addRun(conversationId!, run);
      setEvents(response.run_id, []);
      setMessage('');
    } catch (error) {
      console.error('Failed to create run:', error);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      handleSubmit();
    }
  };

  if (!conversation && runs.length === 0) {
    return (
      <div className="h-full flex flex-col">
        <div className="flex-1 flex flex-col items-center justify-center text-slate-500 gap-3">
          <p className="text-sm">Start a conversation.</p>
        </div>
        <div className="border-t p-4">
          <div className="flex gap-3">
            <Textarea
              placeholder="Ask a question..."
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              onKeyDown={handleKeyDown}
              rows={2}
              className="resize-none"
              disabled={isSubmitting}
            />
            <div className="flex flex-col gap-2 self-end">
              <select
                value={reasoningEffort}
                onChange={(e) => setReasoningEffort(e.target.value as ReasoningEffort)}
                className="h-8 px-2 text-xs border border-slate-200 rounded-md bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                title="Reasoning effort: how deeply the model thinks"
              >
                <option value="low">⚡ Low</option>
                <option value="medium">🧠 Medium</option>
                <option value="high">🔬 High</option>
              </select>
              <Button
                onClick={handleSubmit}
                disabled={!message.trim() || isSubmitting}
              >
                {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              </Button>
            </div>
          </div>
          <p className="text-xs text-slate-500 mt-2">
            {reasoningEffort === 'high' ? '🔬 Deep reasoning' : reasoningEffort === 'medium' ? '🧠 Balanced' : '⚡ Fast'} · Cmd/Ctrl + Enter to send
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      <div className="border-b px-6 py-4">
        <h2 className="text-lg font-semibold">
          {conversation?.title || 'Conversation'}
        </h2>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-6" ref={scrollRef}>
        <div className="space-y-8">
          {runs.map((run) => (
            <RunMessage
              key={run.run_id}
              run={run}
              onShowTrace={() => handleShowTrace(run.run_id)}
            />
          ))}
        </div>
      </div>

      <div className="border-t p-4">
        <div className="flex gap-3">
          <Textarea
            placeholder="Ask a follow-up question..."
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={2}
            className="resize-none"
            disabled={isSubmitting}
          />
          <div className="flex flex-col gap-2 self-end">
            <select
              value={reasoningEffort}
              onChange={(e) => setReasoningEffort(e.target.value as ReasoningEffort)}
              className="h-8 px-2 text-xs border border-slate-200 rounded-md bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              title="Reasoning effort: how deeply the model thinks"
            >
              <option value="low">⚡ Low</option>
              <option value="medium">🧠 Medium</option>
              <option value="high">🔬 High</option>
            </select>
            <Button
              onClick={handleSubmit}
              disabled={!message.trim() || isSubmitting}
            >
              {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            </Button>
          </div>
        </div>
        <p className="text-xs text-slate-500 mt-2">
          {reasoningEffort === 'high' ? '🔬 Deep reasoning' : reasoningEffort === 'medium' ? '🧠 Balanced' : '⚡ Fast'} · Cmd/Ctrl + Enter to send
        </p>
      </div>
    </div>
  );
}
