/**
 * Chat-mode run message display (user turn + streamed answer).
 */

import { memo, useCallback } from 'react';
import { AnswerMarkdown, extractAnswer } from '@/components/AnswerMarkdown';
import { MessageActions } from '@/components/MessageActions';
import { ThinkingPanel } from '@/components/ThinkingPanel';
import { BrailleSpinner } from '@/components/transcript/BrailleSpinner';
import { ElapsedClock } from '@/components/transcript/RunStatusLine';
import { MarkerLine } from '@/components/transcript/TranscriptLine';
import { RunFooter } from '@/components/transcript/RunFooter';
import { UserTurn } from '@/components/transcript/UserTurn';
import { useStore } from '@/hooks/useStore';
import { formatRunStatusLabel, getRunFooterMetrics } from '@/lib/runFormat';
import { cn, formatRelativeTime } from '@/lib/utils';
import type { Run } from '@/types';

// Empty string constant to avoid creating new references
const EMPTY_STRING = '';

export const ChatRunMessage = memo(function ChatRunMessage({
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
    <div
      className={cn(
        'space-y-5',
        // Entrance animation only while live — virtualized remounts of
        // settled runs must not re-animate on scroll.
        isRunning && 'ui-pop-in [--pop-offset:6px]'
      )}
    >
      <UserTurn run={run} />

      <div className="desktop-run group/msg">
        <div className="min-w-0 flex-1">
          <div className="desktop-run-stream space-y-4" data-live={isRunning ? 'true' : undefined}>
            <ThinkingPanel
              summary={run.thinking_summary}
              isStreaming={isThinking}
              streamingContent={streamingThinking}
              defaultExpanded={false}
            />

            {isRunning && !displayText ? (
              <div className="tr-status-line" data-active="true">
                <BrailleSpinner />
                <span className="tr-status-word">
                  {isThinking ? 'Thinking…' : 'Waiting for the first token…'}
                </span>
                <span className="tr-status-meta">
                  (<ElapsedClock startedAt={run.created_at} />)
                </span>
              </div>
            ) : run.status === 'cancelled' ? (
              <MarkerLine tone="steer" mono className="tr-run-state">
                stopped by user
              </MarkerLine>
            ) : run.status === 'interrupted' ? (
              <MarkerLine tone="steer" mono className="tr-run-state">
                interrupted by server restart
              </MarkerLine>
            ) : run.status === 'failed' ? (
              <MarkerLine tone="error" mono className="tr-run-state">
                <span className="tr-danger">
                  [error] {run.error_detail || 'Request failed. Please try again.'}
                </span>
              </MarkerLine>
            ) : displayText ? (
              <div className="desktop-run-answer">
                <AnswerMarkdown content={extractAnswer(displayText)} />
                {isStreaming && (
                  <span className="agent-caret ml-0.5" />
                )}
              </div>
            ) : !isThinking ? (
              <div className="text-sm text-[var(--desktop-text-secondary)]">No response.</div>
            ) : null}
          </div>

          <RunFooter
            pillClassName={cn(
              'desktop-run-meta-pill rounded-full border border-[var(--desktop-border-subtle)] bg-[var(--desktop-panel-inset)] px-2.5 py-1',
              run.status === 'succeeded'
                ? 'text-emerald-300'
                : run.status === 'failed'
                  ? 'border-red-500/15 text-red-400/85'
                  : run.status === 'interrupted'
                    ? 'border-[var(--desktop-interrupt-border)] text-[var(--desktop-interrupt)]'
                  : 'text-[var(--desktop-text-secondary)]'
            )}
            dataStatus={run.status}
            statusLabel={formatRunStatusLabel(run)}
            metrics={
              <>
                {run.created_at && (
                  <span>{formatRelativeTime(run.created_at)}</span>
                )}
                {footerMetrics.map((metric) => (
                  <span key={metric}>{metric}</span>
                ))}
              </>
            }
            actions={
              !isRunning ? (
                <MessageActions
                  content={finalAnswer || displayText}
                  onRetry={onRetry ? handleRetryClick : undefined}
                  canRetry={canRetry}
                  className="shrink-0 opacity-100 md:opacity-0 md:group-hover/msg:opacity-100"
                />
              ) : undefined
            }
          />
        </div>
      </div>
    </div>
  );
});
