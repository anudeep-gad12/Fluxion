/**
 * Agent run message display.
 * Full agent run visualization with user query, progress, and answer.
 */

import { Globe, Square, Eye } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { cn, formatRelativeTime } from '@/lib/utils';
import { AgentStepsPanel } from '@/components/AgentStepsPanel';
import { AnswerWithCitations } from '@/components/AnswerWithCitations';
import { useAgentRunDetails } from '@/hooks/useAgentRunDetails';
import { cancelAgentRun } from '@/api/client';
import type { Run } from '@/types';

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
      <div className="flex justify-end">
        <div className="max-w-[70%] rounded-2xl bg-indigo-600 text-white px-4 py-3 shadow-sm">
          <div className="flex items-center gap-2 mb-1">
            <Globe className="h-4 w-4" />
            <span className="text-xs font-medium opacity-80">
              Research Query
            </span>
          </div>
          <p className="text-sm leading-relaxed whitespace-pre-wrap">
            {run.user_message || run.prompt}
          </p>
          <p className="text-[11px] text-indigo-200 mt-2 text-right">
            {formatRelativeTime(run.created_at)}
          </p>
        </div>
      </div>

      {/* Agent response */}
      <div className="flex justify-start">
        <div className="max-w-[85%] rounded-2xl border border-indigo-200 bg-white px-4 py-3 shadow-sm">
          {/* Agent badge */}
          <div className="flex items-center gap-2 mb-3">
            <Badge
              variant="outline"
              className="text-indigo-600 border-indigo-200"
            >
              <Globe className="h-3 w-3 mr-1" />
              Research Agent
            </Badge>
            {agentState && (
              <span className="text-xs text-slate-500">
                Step {agentState.currentStep}/{agentState.maxSteps}
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
            <div className="text-sm text-slate-500">
              Researching your query...
            </div>
          ) : run.status === 'failed' ? (
            <div className="text-sm text-rose-600">
              {run.error_detail || 'Research failed. Please try again.'}
            </div>
          ) : null}

          {/* Actions */}
          <div className="mt-3 flex flex-wrap items-center gap-2 pt-2 border-t border-slate-100">
            {isActive ? (
              <Button size="sm" variant="destructive" onClick={handleCancel}>
                <Square className="h-4 w-4 fill-current mr-1" />
                Stop
              </Button>
            ) : (
              <Button size="sm" variant="ghost" onClick={onShowTrace}>
                <Eye className="h-4 w-4 mr-1" />
                Details
              </Button>
            )}
            <span
              className={cn(
                'text-xs px-2 py-0.5 rounded-full',
                run.status === 'succeeded'
                  ? 'bg-emerald-100 text-emerald-700'
                  : run.status === 'failed'
                    ? 'bg-rose-100 text-rose-700'
                    : 'bg-indigo-100 text-indigo-600'
              )}
            >
              {run.status === 'running' ? 'researching' : run.status}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
