/**
 * Agent run message display.
 * Full agent run visualization with user query, progress, and answer.
 */

import { memo, useCallback } from 'react';
import { cn, formatRelativeTime } from '@/lib/utils';
import { AgentStepsPanel } from '@/components/AgentStepsPanel';
import { AnswerWithCitations } from '@/components/AnswerWithCitations';
import { MessageActions } from '@/components/MessageActions';
import { ShimmerSkeleton } from '@/components/StreamingIndicator';
import { useAgentRunDetails } from '@/hooks/useAgentRunDetails';
import { deriveAgentPhase, formatAgentCost, formatAgentDuration, formatAgentTokens } from '@/lib/agentLiveState';
import type { Run } from '@/types';

interface AgentRunMessageProps {
  run: Run;
  onRetry?: (userMessage: string) => void;
  canRetry?: boolean;
}

export const AgentRunMessage = memo(function AgentRunMessage({
  run,
  onRetry,
  canRetry,
}: AgentRunMessageProps) {
  const isRunning = run.status === 'running';
  const agentState = useAgentRunDetails(run.run_id, isRunning);

  const isActive = isRunning && agentState?.isActive;
  const finalAnswer = run.final_answer || agentState?.answerBuffer || '';
  const citations = agentState?.citations || [];
  const userMessage = run.user_message || run.prompt;
  const phase = agentState ? deriveAgentPhase(agentState) : null;
  const handleRetryClick = useCallback(() => {
    if (!userMessage || !onRetry) return;
    onRetry(userMessage);
  }, [onRetry, userMessage]);

  return (
    <div className="animate-in fade-in slide-in-from-bottom-2 space-y-4">
      <div className="flex gap-3">
        <div className="w-9 flex-shrink-0 pt-0.5">
          <span className="font-mono text-[11px] uppercase tracking-[0.18em] text-zinc-500">U:</span>
        </div>
        <div className="min-w-0 flex-1">
          <div className="rounded-2xl border border-zinc-800/70 bg-zinc-900/45 px-4 py-3.5 shadow-[inset_0_1px_0_rgba(255,255,255,0.025)]">
            <span className="whitespace-pre-wrap text-sm leading-relaxed text-zinc-100">
              {run.user_message || run.prompt}
            </span>
          </div>
          <div className="mt-1.5 flex items-center gap-2 px-1">
            <p className="text-[11px] text-zinc-600">{formatRelativeTime(run.created_at)}</p>
            <span className="font-mono text-[11px] text-cyan-700">agent</span>
          </div>
        </div>
      </div>

      <div className="group/msg flex gap-3">
        <div className="w-9 flex-shrink-0 pt-0.5">
          <span className="font-mono text-[11px] uppercase tracking-[0.18em] text-cyan-400/80">R:</span>
        </div>
        <div className="min-w-0 flex-1">
          <div className="rounded-2xl border border-zinc-800/55 bg-zinc-950/36 px-4 py-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.02)]">
            {agentState && <AgentStepsPanel agentState={agentState} />}

            {finalAnswer ? (
              <AnswerWithCitations
                content={finalAnswer}
                citations={citations}
                isStreaming={!!isActive}
              />
            ) : isActive && !agentState?.steps.length ? (
              <ShimmerSkeleton />
            ) : isActive ? null : run.status === 'failed' ? (
              <div className="text-sm text-zinc-400">
                [error] {run.error_detail || 'Agent failed. Please try again.'}
              </div>
            ) : null}
          </div>

          {!isActive && (
            <div className="mt-2 flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-1 font-mono text-xs">
              <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
                <span
                  className={cn(
                    phase?.accentClassName || 'text-zinc-500',
                    run.status === 'failed' && 'text-red-400/80'
                  )}
                >
                  [{phase?.label || (run.status === 'succeeded' ? 'done' : run.status)}]
                </span>
                {agentState?.timing_ms && (
                  <span className="text-zinc-600">{formatAgentDuration(agentState.timing_ms)}</span>
                )}
                {agentState?.total_tokens && (
                  <span className="text-zinc-600">{formatAgentTokens(agentState.total_tokens)} tok</span>
                )}
                {agentState?.usage && (
                  <span className="text-zinc-600">
                    in {formatAgentTokens(agentState.usage.input_tokens)} / out {formatAgentTokens(agentState.usage.output_tokens)}
                  </span>
                )}
                {agentState?.cost && agentState?.usage?.total_tokens ? (
                  <span className="text-zinc-600">est {formatAgentCost(agentState.cost.total_cost)}</span>
                ) : agentState?.usage ? (
                  <span className="text-zinc-600">cost n/a</span>
                ) : null}
                {agentState?.context_usage && (
                  <span className="text-zinc-600">
                    ctx {Math.round(agentState.context_usage.utilization_pct_effective)}%
                    {typeof agentState.compaction_count === 'number' ? ` · compact ${agentState.compaction_count}` : ''}
                  </span>
                )}
              </div>
              {finalAnswer && (
                <MessageActions
                  content={finalAnswer}
                  onRetry={onRetry ? handleRetryClick : undefined}
                  canRetry={canRetry}
                  className="shrink-0 opacity-100 md:opacity-0 md:group-hover/msg:opacity-100"
                />
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
});
