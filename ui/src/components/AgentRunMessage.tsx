/**
 * Agent run message display.
 * Full agent run visualization with user query, progress, and answer.
 */

import { cn, formatRelativeTime } from '@/lib/utils';
import { AgentStepsPanel } from '@/components/AgentStepsPanel';
import { AnswerWithCitations } from '@/components/AnswerWithCitations';
import { useAgentRunDetails } from '@/hooks/useAgentRunDetails';
import { cancelAgentRun } from '@/api/client';
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

interface AgentRunMessageProps {
  run: Run;
  onShowTrace: () => void;
}

export function AgentRunMessage({ run, onShowTrace }: AgentRunMessageProps) {
  const isRunning = run.status === 'running';
  const agentState = useAgentRunDetails(run.run_id, isRunning);

  const isActive = isRunning && agentState?.isActive;
  const finalAnswer = run.final_answer || agentState?.answerBuffer || '';
  const citations = agentState?.citations || [];

  const handleCancel = async () => {
    try {
      await cancelAgentRun(run.run_id);
    } catch (error) {
      console.error('Failed to cancel agent run:', error);
    }
  };

  return (
    <div className="space-y-3 animate-in fade-in slide-in-from-bottom-2">
      {/* User message */}
      <div className="w-full">
        <div className="w-full py-2">
          <span className="text-zinc-500 mr-2 select-none font-mono">{'$'}</span>
          <span className="text-zinc-600 text-xs mr-2">[research]</span>
          <span className="text-zinc-100 whitespace-pre-wrap text-sm leading-relaxed">
            {run.user_message || run.prompt}
          </span>
          <p className="text-[11px] text-zinc-600 mt-2 text-left">
            {formatRelativeTime(run.created_at)}
          </p>
        </div>
      </div>

      {/* Agent response */}
      <div className="w-full">
        <div className="w-full py-2 pl-4 border-l border-zinc-800">
          {/* Agent badge */}
          <div className="flex items-center gap-2 mb-3">
            <span className="text-zinc-500 text-xs font-mono">[agent]</span>
            {agentState && (
              <span className="text-xs text-zinc-600">
                Step {agentState.currentStep}
              </span>
            )}
          </div>

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
          ) : isActive ? (
            <div className="text-xs text-zinc-500 font-mono">
              [researching...]
            </div>
          ) : run.status === 'failed' ? (
            <div className="text-sm text-zinc-400">
              [error] {run.error_detail || 'Research failed. Please try again.'}
            </div>
          ) : null}

          {/* Actions */}
          <div className="mt-3 flex flex-wrap items-center gap-3 pt-2 border-t border-zinc-800 font-mono text-xs">
            {isActive ? (
              <button
                onClick={handleCancel}
                className="text-zinc-400 hover:text-zinc-200"
              >
                [^C stop]
              </button>
            ) : (
              <button
                onClick={onShowTrace}
                className="text-zinc-500 hover:text-zinc-300"
              >
                [details]
              </button>
            )}
            <span
              className={cn(
                run.status === 'succeeded'
                  ? 'text-zinc-500'
                  : run.status === 'failed'
                    ? 'text-zinc-500'
                    : 'text-zinc-600'
              )}
            >
              [{run.status === 'running' ? 'researching...' : run.status === 'succeeded' ? 'done' : run.status}]
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
          </div>
        </div>
      </div>
    </div>
  );
}
