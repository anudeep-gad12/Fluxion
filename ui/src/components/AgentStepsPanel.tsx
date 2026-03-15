/**
 * Agent steps and tool calls visualization panel.
 * Shows research progress with visual progress bar, step timeline,
 * state labels, and live token counter.
 */

import { useState, useEffect, useRef } from 'react';
import { cn, sanitizeThinking } from '@/lib/utils';
import { ToolCallCard } from '@/components/ToolCallCard';
import { AnswerMarkdown } from '@/components/AnswerMarkdown';
import type { AgentStep, AgentToolCall, AgentUIState } from '@/types/agent';

/** Map agent state to human-readable label */
const STATE_LABELS: Record<string, { label: string; color: string }> = {
  initializing: { label: 'Initializing', color: 'text-zinc-500' },
  running: { label: 'Researching', color: 'text-cyan-500' },
  planning: { label: 'Planning', color: 'text-cyan-500' },
  tool_calling: { label: 'Using tools', color: 'text-amber-500' },
  synthesizing: { label: 'Writing answer', color: 'text-emerald-500' },
  complete: { label: 'Complete', color: 'text-emerald-500' },
  error: { label: 'Error', color: 'text-red-500' },
  cancelled: { label: 'Cancelled', color: 'text-zinc-500' },
};

/** Elapsed time counter for active runs */
function ElapsedTimer({ startedAt }: { startedAt: string }) {
  const [elapsed, setElapsed] = useState(0);
  const startRef = useRef(new Date(startedAt).getTime());

  useEffect(() => {
    startRef.current = new Date(startedAt).getTime();
  }, [startedAt]);

  useEffect(() => {
    const interval = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startRef.current) / 1000));
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  const mins = Math.floor(elapsed / 60);
  const secs = elapsed % 60;
  return (
    <span className="text-zinc-600 tabular-nums">
      {mins > 0 ? `${mins}m ${secs}s` : `${secs}s`}
    </span>
  );
}

interface AgentStepsPanelProps {
  agentState: AgentUIState;
  defaultExpanded?: boolean;
}

function StepHeader({
  step,
  isActive,
  toolCallCount,
}: {
  step: AgentStep;
  isActive: boolean;
  isLast: boolean;
  toolCallCount: number;
}) {
  const isComplete = step.state === 'complete' || step.completed_at;

  return (
    <div
      className={cn(
        'flex items-center gap-2 py-1.5 font-mono text-xs',
        isActive && 'text-zinc-200'
      )}
    >
      <span className={cn(
        'select-none w-4 text-center',
        isActive ? 'text-cyan-400' : isComplete ? 'text-emerald-600' : 'text-zinc-600'
      )}>
        {isActive ? '→' : isComplete ? '✓' : '○'}
      </span>
      <span className="font-medium text-sm">Step {step.step_number}</span>
      {step.decision && (
        <span className="text-zinc-600 truncate max-w-[200px]">({step.decision})</span>
      )}
      {toolCallCount > 0 && (
        <span className="text-zinc-600">
          {toolCallCount} tool{toolCallCount !== 1 ? 's' : ''}
        </span>
      )}
    </div>
  );
}

export function AgentStepsPanel({
  agentState,
  defaultExpanded = true,
}: AgentStepsPanelProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const [expandedSteps, setExpandedSteps] = useState<Set<number>>(new Set());

  const toggleStep = (stepNum: number) => {
    const newExpanded = new Set(expandedSteps);
    if (newExpanded.has(stepNum)) {
      newExpanded.delete(stepNum);
    } else {
      newExpanded.add(stepNum);
    }
    setExpandedSteps(newExpanded);
  };

  const { steps, toolCalls, thinkingBuffer, currentStep, isActive, total_tokens, context_usage } =
    agentState;

  // Derive current state from step data
  const currentState = (() => {
    if (!isActive && agentState.agentState === 'complete') return 'complete';
    if (!isActive && agentState.agentState === 'error') return 'error';
    if (!isActive && agentState.agentState === 'cancelled') return 'cancelled';
    if (agentState.answerBuffer) return 'synthesizing';
    // Check if any tool is running
    const hasRunningTool = toolCalls.some((tc) => tc.status === 'running');
    if (hasRunningTool) return 'tool_calling';
    if (thinkingBuffer) return 'planning';
    if (isActive) return 'running';
    return agentState.agentState || 'initializing';
  })();

  const stateInfo = STATE_LABELS[currentState] || STATE_LABELS.running;

  // Find earliest step timestamp for timer
  const firstStepTime = steps.length > 0 ? steps[0].created_at : undefined;

  // Build step_id to step_number mapping (handles both UUID and step-N formats)
  const stepIdToNumber: Record<string, number> = {};
  steps.forEach((s) => {
    stepIdToNumber[s.id] = s.step_number;
    stepIdToNumber[`step-${s.step_number}`] = s.step_number;
  });

  // Group tool calls by step using the mapping
  const toolCallsByStep = toolCalls.reduce(
    (acc, tc) => {
      const stepNum = stepIdToNumber[tc.step_id];
      if (stepNum !== undefined) {
        if (!acc[stepNum]) acc[stepNum] = [];
        acc[stepNum].push(tc);
      }
      return acc;
    },
    {} as Record<number, AgentToolCall[]>
  );

  if (steps.length === 0 && !isActive) {
    return null;
  }

  return (
    <div className="mb-3 rounded-none border border-zinc-800 bg-zinc-900 overflow-hidden">
      {/* Header with progress bar */}
      <button
        onClick={() => setExpanded(!expanded)}
        className={cn(
          'w-full px-3 py-2.5 text-left',
          'hover:bg-zinc-800/50 transition-colors',
          expanded && 'border-b border-zinc-800'
        )}
      >
        {/* Top row: state label + step counter + timer */}
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <span className="text-zinc-600 select-none text-xs">{expanded ? '▼' : '▶'}</span>
            <span className={cn('text-xs font-medium font-mono', stateInfo.color)}>
              {stateInfo.label}
            </span>
            {isActive && (
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-cyan-500 animate-pulse" />
            )}
          </div>
          <div className="flex items-center gap-3 text-xs font-mono">
            {/* Live elapsed timer */}
            {isActive && firstStepTime && (
              <ElapsedTimer startedAt={firstStepTime} />
            )}
            {/* Step counter — no denominator since the model decides when to stop */}
            {currentStep > 0 && (
              <span className="text-zinc-500">
                step {currentStep}
              </span>
            )}
            {/* Token counter */}
            {total_tokens && total_tokens > 0 && (
              <span className="text-zinc-600">
                {total_tokens.toLocaleString()} tok
              </span>
            )}
            {/* Context usage */}
            {context_usage && (
              <span className={cn(
                'text-xs',
                context_usage.utilization_pct > 80 ? 'text-amber-500' : 'text-zinc-600'
              )}>
                ctx {Math.round(context_usage.utilization_pct)}%
              </span>
            )}
          </div>
        </div>

        {/* Phase indicator — indeterminate bar that shows activity, not percentage */}
        {isActive ? (
          <div className="h-0.5 bg-zinc-800 w-full overflow-hidden">
            <div
              className={cn(
                'h-full w-1/3 animate-indeterminate',
                currentState === 'synthesizing' ? 'bg-emerald-500' :
                currentState === 'tool_calling' ? 'bg-amber-500' :
                'bg-cyan-600'
              )}
            />
          </div>
        ) : (
          <div className={cn(
            'h-0.5 w-full',
            currentState === 'complete' ? 'bg-emerald-600' :
            currentState === 'error' ? 'bg-red-500' :
            'bg-zinc-700'
          )} />
        )}
      </button>

      {/* Animated collapsible content */}
      <div className="collapsible-content" data-expanded={expanded}>
        <div>
          <div className="px-3 py-2 space-y-2 max-h-[500px] overflow-y-auto">
            {steps.map((step, i) => {
              const stepToolCalls = toolCallsByStep[step.step_number] || [];
              const isCurrentStep = step.step_number === currentStep;
              const isStepExpanded =
                expandedSteps.has(step.step_number) || isCurrentStep || !isActive;

              return (
                <div
                  key={step.id}
                  className={cn(
                    'border-l-2 pl-3 transition-colors',
                    isCurrentStep && isActive
                      ? 'border-cyan-600'
                      : (step.state === 'complete' || step.completed_at)
                        ? 'border-zinc-700'
                        : 'border-zinc-800'
                  )}
                >
                  <button
                    onClick={() => toggleStep(step.step_number)}
                    className="w-full text-left"
                  >
                    <StepHeader
                      step={step}
                      isActive={isCurrentStep && isActive}
                      isLast={i === steps.length - 1}
                      toolCallCount={stepToolCalls.length}
                    />
                  </button>

                  {isStepExpanded && (
                    <div className="ml-6 space-y-2 pb-2">
                      {/* Live thinking for active current step */}
                      {isCurrentStep && isActive && thinkingBuffer && (
                        <pre className="text-xs text-zinc-500 bg-zinc-800/50 rounded-none p-2 whitespace-pre-wrap font-mono leading-relaxed">
                          {sanitizeThinking(thinkingBuffer)}
                          <span className="inline-block w-1.5 h-3 bg-zinc-400 animate-pulse ml-0.5" />
                        </pre>
                      )}

                      {/* Historical thinking for completed steps */}
                      {!(isCurrentStep && isActive) && step.thinking_text && (
                        <div className="text-xs text-zinc-500 bg-zinc-800/50 rounded-none p-2 thinking-markdown">
                          <AnswerMarkdown content={sanitizeThinking(step.thinking_text)} />
                        </div>
                      )}

                      {/* Tool calls */}
                      {stepToolCalls.map((tc) => (
                        <ToolCallCard key={tc.id} toolCall={tc} />
                      ))}
                    </div>
                  )}
                </div>
              );
            })}

            {/* Active step indicator when no steps yet */}
            {steps.length === 0 && isActive && (
              <div className="flex items-center gap-2 text-xs text-zinc-500 font-mono py-2">
                <span className="inline-block w-1.5 h-1.5 rounded-full bg-cyan-500 animate-pulse" />
                Initializing agent...
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
