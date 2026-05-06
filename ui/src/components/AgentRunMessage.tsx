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
  onShowTrace: (runId: string) => void;
  onRetry?: (userMessage: string) => void;
  canRetry?: boolean;
}

export const AgentRunMessage = memo(function AgentRunMessage({
  run,
  onShowTrace,
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
  const handleShowTraceClick = useCallback(() => {
    onShowTrace(run.run_id);
  }, [onShowTrace, run.run_id]);
  const handleRetryClick = useCallback(() => {
    if (!userMessage || !onRetry) return;
    onRetry(userMessage);
  }, [onRetry, userMessage]);

  return (
    <div className="animate-in fade-in slide-in-from-bottom-2 space-y-4">
      <div className="flex gap-3">
        <div className="mt-0.5 flex h-7 w-7 flex-shrink-0 items-center justify-center bg-zinc-700">
          <span className="font-mono text-xs text-zinc-300">U</span>
        </div>
        <div className="min-w-0 flex-1">
          <div className="border border-zinc-800 bg-zinc-800/50 px-4 py-3">
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
        <div className="mt-0.5 flex h-7 w-7 flex-shrink-0 items-center justify-center border border-cyan-900/50 bg-cyan-950">
          <span className="font-mono text-[10px] text-cyan-400">R</span>
        </div>
        <div className="min-w-0 flex-1">
          <div className="py-2">
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
            <div className="mt-2 flex flex-wrap items-center gap-3 font-mono text-xs">
              <button
                onClick={handleShowTraceClick}
                className="text-zinc-600 transition-colors hover:text-zinc-300"
              >
                [details]
              </button>
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
              {finalAnswer && (
                <MessageActions
                  content={finalAnswer}
                  onRetry={onRetry ? handleRetryClick : undefined}
                  canRetry={canRetry}
                />
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
});
