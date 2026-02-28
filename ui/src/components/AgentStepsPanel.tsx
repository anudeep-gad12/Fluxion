/**
 * Agent steps and tool calls visualization panel.
 * Shows research progress with collapsible steps and tool calls.
 */

import { useState } from 'react';
import { cn, sanitizeThinking } from '@/lib/utils';
import { ToolCallCard } from '@/components/ToolCallCard';
import { AnswerMarkdown } from '@/components/AnswerMarkdown';
import type { AgentStep, AgentToolCall, AgentUIState } from '@/types/agent';

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
      <span className={cn('select-none', isActive ? 'text-zinc-300' : isComplete ? 'text-zinc-400' : 'text-zinc-600')}>
        {isActive ? '→' : isComplete ? '✓' : '○'}
      </span>
      <span className="font-medium text-sm">Step {step.step_number}</span>
      {step.decision && (
        <span className="text-zinc-600">({step.decision})</span>
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

  const { steps, toolCalls, thinkingBuffer, currentStep, isActive } =
    agentState;

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
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className={cn(
          'w-full px-3 py-2 flex items-center gap-2 text-xs font-mono text-zinc-300',
          'hover:bg-zinc-800',
          expanded && 'border-b border-zinc-800'
        )}
      >
        <span className="text-zinc-600 select-none">{expanded ? '▼' : '▶'}</span>
        <span className="font-medium">[progress]</span>
        {isActive && (
          <span className="text-zinc-500">[running...]</span>
        )}
        <span className="text-zinc-600">
          step {currentStep}
        </span>
      </button>

      {/* Animated collapsible content */}
      <div className="collapsible-content" data-expanded={expanded}>
        <div>
          <div className="px-3 py-2 space-y-2 max-h-[400px] overflow-y-auto">
            {steps.map((step, i) => {
              const stepToolCalls = toolCallsByStep[step.step_number] || [];
              const isCurrentStep = step.step_number === currentStep;
              const isStepExpanded =
                expandedSteps.has(step.step_number) || isCurrentStep || !isActive;

              return (
                <div
                  key={step.id}
                  className={cn(
                    'border-l-2 pl-3',
                    isCurrentStep ? 'border-zinc-400' : 'border-zinc-800'
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
                      {/* Live thinking for active current step — raw plain text,
                          no processing at all to preserve exact token order */}
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
              <div className="text-xs text-zinc-500 font-mono">
                [initializing...]
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
