/**
 * Agent steps and tool calls visualization panel.
 * Shows research progress with collapsible steps and tool calls.
 */

import { useState } from 'react';
import {
  ChevronDown,
  ChevronRight,
  Brain,
  Loader2,
  CheckCircle2,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { ToolCallCard } from '@/components/ToolCallCard';
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
        'flex items-center gap-2 py-2',
        isActive && 'text-indigo-700'
      )}
    >
      {isActive ? (
        <Loader2 className="h-4 w-4 animate-spin text-indigo-500" />
      ) : isComplete ? (
        <CheckCircle2 className="h-4 w-4 text-emerald-500" />
      ) : (
        <div className="h-4 w-4 rounded-full border-2 border-slate-300" />
      )}
      <span className="font-medium text-sm">Step {step.step_number}</span>
      {step.decision && (
        <span className="text-xs text-slate-500">({step.decision})</span>
      )}
      {toolCallCount > 0 && (
        <span className="text-xs bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded">
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

  // Group tool calls by step
  const toolCallsByStep = toolCalls.reduce(
    (acc, tc) => {
      const stepNum = parseInt(tc.step_id.replace('step-', ''), 10);
      if (!acc[stepNum]) acc[stepNum] = [];
      acc[stepNum].push(tc);
      return acc;
    },
    {} as Record<number, AgentToolCall[]>
  );

  if (steps.length === 0 && !isActive) {
    return null;
  }

  return (
    <div className="mb-3 rounded-lg border border-indigo-200 bg-indigo-50/50 overflow-hidden">
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className={cn(
          'w-full px-3 py-2 flex items-center gap-2 text-sm text-indigo-700',
          'hover:bg-indigo-100/50 transition-colors',
          expanded && 'border-b border-indigo-200'
        )}
      >
        {expanded ? (
          <ChevronDown className="h-4 w-4 text-indigo-400" />
        ) : (
          <ChevronRight className="h-4 w-4 text-indigo-400" />
        )}
        <Brain className="h-4 w-4 text-indigo-500" />
        <span className="font-medium">Research Progress</span>
        {isActive && (
          <Loader2 className="h-3 w-3 animate-spin text-indigo-500" />
        )}
        <span className="text-xs text-indigo-400">
          Step {currentStep} of {agentState.maxSteps}
        </span>
      </button>

      {/* Expanded content */}
      {expanded && (
        <div className="px-3 py-2 space-y-2 max-h-[400px] overflow-y-auto">
          {steps.map((step, i) => {
            const stepToolCalls = toolCallsByStep[step.step_number] || [];
            const isCurrentStep = step.step_number === currentStep;
            const isStepExpanded =
              expandedSteps.has(step.step_number) || isCurrentStep;

            return (
              <div
                key={step.id}
                className={cn(
                  'border-l-2 pl-3',
                  isCurrentStep ? 'border-indigo-400' : 'border-slate-200'
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
                    {/* Thinking content for current step */}
                    {isCurrentStep && thinkingBuffer && (
                      <div className="text-xs text-slate-600 bg-white/50 rounded p-2 italic">
                        {thinkingBuffer}
                        {isActive && (
                          <span className="inline-block w-1.5 h-3 bg-indigo-400 animate-pulse ml-0.5" />
                        )}
                      </div>
                    )}

                    {/* Historical thinking */}
                    {!isCurrentStep && step.thinking_text && (
                      <div className="text-xs text-slate-600 bg-white/50 rounded p-2 italic">
                        {step.thinking_text}
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
            <div className="flex items-center gap-2 text-sm text-indigo-600">
              <Loader2 className="h-4 w-4 animate-spin" />
              Initializing research agent...
            </div>
          )}
        </div>
      )}
    </div>
  );
}
