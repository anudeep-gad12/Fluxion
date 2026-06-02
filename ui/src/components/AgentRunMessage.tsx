/**
 * Agent run message display.
 */

import { memo, useCallback } from 'react';
import { cn, formatRelativeTime } from '@/lib/utils';
import { AgentStepsPanel } from '@/components/AgentStepsPanel';
import { AnswerWithCitations } from '@/components/AnswerWithCitations';
import { MessageActions } from '@/components/MessageActions';
import { useAgentRunDetails } from '@/hooks/useAgentRunDetails';
import { deriveAgentPhase, formatAgentCost, formatAgentDuration, formatAgentTokens } from '@/lib/agentLiveState';
import { normalizeTokenUsage } from '@/lib/usageMetrics';
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
  const usage = normalizeTokenUsage(agentState?.usage ?? run.usage);
  const totalTokens = agentState?.total_tokens ?? usage?.total_tokens;
  const cost = agentState?.cost ?? run.cost;
  const contextUsage = agentState?.context_usage ?? run.context_usage;
  const compactionCount = (
    agentState?.compaction_count
    ?? contextUsage?.compaction_count
    ?? contextUsage?.compactions_so_far
  );
  const handleRetryClick = useCallback(() => {
    if (!userMessage || !onRetry) return;
    onRetry(userMessage);
  }, [onRetry, userMessage]);

  const metaStatus =
    run.status === 'running'
      ? 'running'
      : run.status === 'failed'
        ? 'failed'
        : run.status === 'cancelled'
          ? 'cancelled'
          : run.status === 'interrupted'
            ? 'interrupted'
          : 'succeeded';

  return (
    <div className="animate-in fade-in slide-in-from-bottom-2 space-y-5 duration-200">
      <div className="desktop-run">
        <div className="min-w-0 flex-1">
          <div className="desktop-message-card fluxion-card rounded-[1.35rem] border px-6 py-5">
            <span className="whitespace-pre-wrap text-[14px] leading-[1.9] text-zinc-50">
              {run.user_message || run.prompt}
            </span>
          </div>
          <p className="desktop-run-meta mt-2 px-1 text-[11px] text-zinc-500">
            {formatRelativeTime(run.created_at)}
          </p>
        </div>
      </div>

      <div className="desktop-run group/msg">
        <div className="min-w-0 flex-1">
          <div className="desktop-run-stream space-y-4">
            {agentState && <AgentStepsPanel agentState={agentState} />}

            {finalAnswer ? (
              <div className="desktop-run-answer">
                <AnswerWithCitations
                  content={finalAnswer}
                  citations={citations}
                  isStreaming={!!isActive}
                />
              </div>
            ) : isActive ? null : run.status === 'cancelled' ? (
              <div className="desktop-message-card-cancelled border-l border-amber-500/35 pl-4 text-sm text-amber-100/90">
                stopped by user
              </div>
            ) : run.status === 'interrupted' ? (
              <div className="desktop-message-card-cancelled border-l border-orange-500/35 pl-4 text-sm text-orange-100/90">
                interrupted by server restart
              </div>
            ) : run.status === 'failed' ? (
              <div className="desktop-message-card-error border-l border-red-500/35 pl-4 text-sm text-red-200/90">
                [error] {run.error_detail || 'Agent failed. Please try again.'}
              </div>
            ) : null}
          </div>

          {!isActive && (
            <div className="desktop-run-meta mt-2 flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-1 font-mono text-[11px]">
              <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 text-zinc-500">
                <span
                  className={cn(
                    'desktop-run-meta-pill rounded-full border border-zinc-900/90 bg-transparent px-2.5 py-1',
                    phase?.accentClassName || 'text-zinc-300',
                    run.status === 'failed' && 'border-red-500/15 text-red-400/85',
                    run.status === 'cancelled' && 'border-amber-500/15 text-amber-300/85',
                    run.status === 'interrupted' && 'border-orange-500/15 text-orange-300/85'
                  )}
                  data-status={metaStatus}
                >
                  {phase?.label || (run.status === 'succeeded' ? 'done' : run.status === 'cancelled' ? 'stopped' : run.status)}
                </span>
                {agentState?.timing_ms && (
                  <span>{formatAgentDuration(agentState.timing_ms)}</span>
                )}
                {totalTokens ? (
                  <span>{formatAgentTokens(totalTokens)} tok</span>
                ) : null}
                {usage ? (
                  <span>
                    in {formatAgentTokens(usage.input_tokens)} / out {formatAgentTokens(usage.output_tokens)}
                  </span>
                ) : null}
                {cost && typeof cost.total_cost === 'number' ? (
                  <span>est {formatAgentCost(cost.total_cost)}</span>
                ) : usage ? (
                  <span>cost n/a</span>
                ) : null}
                {contextUsage && (
                  <span>
                    ctx {Math.round(contextUsage.utilization_pct_effective)}
                    %
                    {typeof compactionCount === 'number' ? ` · compact ${compactionCount}` : ''}
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
