/**
 * Agent run message display.
 * Full agent run visualization with user query, progress, and answer.
 */

import { cn, formatRelativeTime } from '@/lib/utils';
import { AgentStepsPanel } from '@/components/AgentStepsPanel';
import { AnswerWithCitations } from '@/components/AnswerWithCitations';
import { MessageActions } from '@/components/MessageActions';
import { ShimmerSkeleton } from '@/components/StreamingIndicator';
import { useAgentRunDetails } from '@/hooks/useAgentRunDetails';
import { cancelAgentRun, pauseAgentRun, resumeAgentRun } from '@/api/client';
import type { Run } from '@/types';

/** Format milliseconds to human-readable duration */
function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = Math.round(seconds % 60);
  return `${minutes}m ${remainingSeconds}s`;
}

/** Format token count with thousands separator */
function formatTokens(tokens: number): string {
  return tokens.toLocaleString();
}

function formatCost(cost: number): string {
  if (cost === 0) return '$0';
  if (cost < 0.01) return `$${cost.toFixed(4)}`;
  return `$${cost.toFixed(2)}`;
}

interface AgentRunMessageProps {
  run: Run;
  onShowTrace: () => void;
  onRetry?: () => void;
  canRetry?: boolean;
}

export function AgentRunMessage({ run, onShowTrace, onRetry, canRetry }: AgentRunMessageProps) {
  const isRunning = run.status === 'running';
  const agentState = useAgentRunDetails(run.run_id, isRunning);

  const isActive = isRunning && agentState?.isActive;
  const isPaused = agentState?.agentState === 'paused';
  const finalAnswer = run.final_answer || agentState?.answerBuffer || '';
  const citations = agentState?.citations || [];

  const handleCancel = async () => {
    try {
      await cancelAgentRun(run.run_id);
    } catch (error) {
      console.error('Failed to cancel agent run:', error);
    }
  };

  const handlePause = async () => {
    try {
      await pauseAgentRun(run.run_id);
    } catch (error) {
      console.error('Failed to pause agent run:', error);
    }
  };

  const handleResume = async () => {
    try {
      await resumeAgentRun(run.run_id);
    } catch (error) {
      console.error('Failed to resume agent run:', error);
    }
  };

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
          <div className="flex items-center gap-2 mt-1.5 px-1">
            <p className="text-[11px] text-zinc-600">
              {formatRelativeTime(run.created_at)}
            </p>
            <span className="text-[11px] text-cyan-700 font-mono">agent</span>
          </div>
        </div>
      </div>

      {/* Agent response */}
      <div className="flex gap-3 group/msg">
        <div className="flex-shrink-0 w-7 h-7 bg-cyan-950 border border-cyan-900/50 flex items-center justify-center mt-0.5">
          <span className="text-[10px] font-mono text-cyan-400">R</span>
        </div>
        <div className="flex-1 min-w-0">
          <div className="py-2">
            {/* Steps panel */}
            {agentState && (
              <AgentStepsPanel
                agentState={agentState}
                defaultExpanded={isActive}
              />
            )}

            {/* Answer */}
            {finalAnswer ? (
              <AnswerWithCitations
                content={finalAnswer}
                citations={citations}
                isStreaming={isActive}
              />
            ) : isActive && !agentState?.steps.length ? (
              <ShimmerSkeleton />
            ) : isActive ? (
              null
            ) : run.status === 'failed' ? (
              <div className="text-sm text-zinc-400">
                [error] {run.error_detail || 'Agent failed. Please try again.'}
              </div>
            ) : null}
          </div>

          {/* Actions */}
          <div className="mt-2 flex flex-wrap items-center gap-3 font-mono text-xs">
            {isActive && isPaused ? (
              <>
                <button
                  onClick={handleResume}
                  className="text-emerald-500/80 hover:text-emerald-400 transition-colors"
                >
                  [resume]
                </button>
                <button
                  onClick={handleCancel}
                  className="text-red-500/70 hover:text-red-400 transition-colors"
                >
                  [stop]
                </button>
              </>
            ) : isActive ? (
              <button
                onClick={handlePause}
                className="text-amber-500/70 hover:text-amber-400 transition-colors"
              >
                [pause]
              </button>
            ) : (
              <button
                onClick={onShowTrace}
                className="text-zinc-600 hover:text-zinc-300 transition-colors"
              >
                [details]
              </button>
            )}
            <span
              className={cn(
                run.status === 'succeeded'
                  ? 'text-emerald-600'
                  : run.status === 'failed'
                    ? 'text-red-500/70'
                    : 'text-cyan-700'
              )}
            >
              [{run.status === 'running' ? 'agenting...' : run.status === 'succeeded' ? 'done' : run.status}]
            </span>
            {!isActive && agentState?.timing_ms && (
              <span className="text-zinc-600">
                {formatDuration(agentState.timing_ms)}
              </span>
            )}
            {!isActive && agentState?.total_tokens && (
              <span className="text-zinc-600">
                {formatTokens(agentState.total_tokens)} tok
              </span>
            )}
            {!isActive && agentState?.usage && (
              <span className="text-zinc-600">
                in {formatTokens(agentState.usage.input_tokens)} / out {formatTokens(agentState.usage.output_tokens)}
              </span>
            )}
            {!isActive && agentState?.cost && agentState?.usage?.total_tokens ? (
              <span className="text-zinc-600">
                est {formatCost(agentState.cost.total_cost)}
              </span>
            ) : !isActive && agentState?.usage ? (
              <span className="text-zinc-600">cost n/a</span>
            ) : null}
            {!isActive && agentState?.context_usage && (
              <span className="text-zinc-600">
                ctx {Math.round(agentState.context_usage.utilization_pct_effective)}%
                {typeof agentState.compaction_count === 'number' ? ` · compact ${agentState.compaction_count}` : ''}
              </span>
            )}
            {/* Copy / Retry actions - visible on hover */}
            {!isActive && finalAnswer && (
              <MessageActions
                content={finalAnswer}
                onRetry={onRetry}
                canRetry={canRetry}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
