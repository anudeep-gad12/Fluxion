/**
 * Agent run message display.
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
    <div className="animate-in fade-in slide-in-from-bottom-2 space-y-5 duration-200">
      <div className="flex gap-4">
        <div className="w-11 flex-shrink-0 pt-1.5">
          <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-zinc-500">you</span>
        </div>
        <div className="min-w-0 flex-1">
          <div className="ui-panel rounded-[1.55rem] border border-zinc-800/90 px-6 py-5 shadow-[0_18px_38px_rgba(0,0,0,0.16),inset_0_1px_0_rgba(255,255,255,0.025)]">
            <span className="whitespace-pre-wrap text-[14px] leading-[1.9] text-zinc-50">
              {run.user_message || run.prompt}
            </span>
          </div>
          <div className="mt-2 flex items-center gap-2 px-1">
            <p className="text-[11px] text-zinc-500">{formatRelativeTime(run.created_at)}</p>
            <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-zinc-600">prompt</span>
          </div>
        </div>
      </div>

      <div className="group/msg flex gap-4">
        <div className="w-11 flex-shrink-0 pt-1.5">
          <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-cyan-200/80">AI</span>
        </div>
        <div className="min-w-0 flex-1">
          <div className="rounded-[1.55rem] border border-zinc-800/85 bg-zinc-950/78 px-6 py-5 shadow-[0_24px_44px_rgba(0,0,0,0.18),inset_0_1px_0_rgba(255,255,255,0.02)]">
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
              <div className="rounded-[1rem] border border-red-500/16 bg-red-500/[0.06] px-4 py-3 text-sm text-red-200/90">
                [error] {run.error_detail || 'Agent failed. Please try again.'}
              </div>
            ) : null}
          </div>

          {!isActive && (
            <div className="mt-2 flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-1 font-mono text-[11px]">
              <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 text-zinc-500">
                <span
                  className={cn(
                    'rounded-full border border-zinc-800/85 bg-zinc-950/72 px-2.5 py-1',
                    phase?.accentClassName || 'text-zinc-300',
                    run.status === 'failed' && 'border-red-500/15 text-red-400/85'
                  )}
                >
                  {phase?.label || (run.status === 'succeeded' ? 'done' : run.status)}
                </span>
                {agentState?.timing_ms && (
                  <span>{formatAgentDuration(agentState.timing_ms)}</span>
                )}
                {agentState?.total_tokens && (
                  <span>{formatAgentTokens(agentState.total_tokens)} tok</span>
                )}
                {agentState?.usage && (
                  <span>
                    in {formatAgentTokens(agentState.usage.input_tokens)} / out {formatAgentTokens(agentState.usage.output_tokens)}
                  </span>
                )}
                {agentState?.cost && agentState?.usage?.total_tokens ? (
                  <span>est {formatAgentCost(agentState.cost.total_cost)}</span>
                ) : agentState?.usage ? (
                  <span>cost n/a</span>
                ) : null}
                {agentState?.context_usage && (
                  <span>
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
