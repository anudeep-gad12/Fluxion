/**
 * Continuous agent activity stream.
 * Shows thinking/tool activity inline without boxed step labels.
 */

import { useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { sanitizeThinking } from '@/lib/utils';
import { ToolCallCard } from '@/components/ToolCallCard';
import { AnswerMarkdown } from '@/components/AnswerMarkdown';
import type { AgentToolCall, AgentUIState } from '@/types/agent';

function TimelineItem({
  dotClassName,
  lineClassName,
  children,
  isLast = false,
}: {
  dotClassName: string;
  lineClassName?: string;
  children: ReactNode;
  isLast?: boolean;
}) {
  return (
    <div className="relative pl-6">
      {!isLast && (
        <span
          className={`absolute left-[3px] top-3 bottom-[-0.75rem] w-px ${lineClassName || 'bg-zinc-800'}`}
        />
      )}
      <span className={`absolute left-0 top-2 h-2 w-2 rounded-full ${dotClassName}`} />
      {children}
    </div>
  );
}

function ThinkingBlock({
  stepNumber,
  content,
  isLive,
  expanded,
  onToggle,
}: {
  stepNumber: number;
  content: string;
  isLive: boolean;
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <div className="space-y-2">
      <button
        type="button"
        onClick={onToggle}
        className="flex items-center gap-2 text-left text-zinc-300 transition-colors hover:text-zinc-300"
      >
        <span className="select-none text-zinc-300">{expanded ? '▼' : '▶'}</span>
        <span>{isLive ? 'thinking...' : 'thinking'}</span>
        {isLive && <span className="text-cyan-400/70">live</span>}
      </button>
      {expanded && (
        <div className="rounded-sm border border-zinc-700 bg-zinc-950/82 px-3 py-2 text-zinc-300">
          <AnswerMarkdown content={content} />
          {isLive && (
            <span className="agent-caret ml-1 inline-block h-3 w-1.5 translate-y-0.5 bg-cyan-400/70" />
          )}
        </div>
      )}
      {!expanded && isLive && <div className="text-[11px] text-zinc-300">step {stepNumber}</div>}
    </div>
  );
}

interface AgentStepsPanelProps {
  agentState: AgentUIState;
}

export function AgentStepsPanel({ agentState }: AgentStepsPanelProps) {
  const {
    steps,
    toolCalls,
    thinkingBuffer,
    currentStep,
    isActive,
    injectedSteers,
    systemEvents = [],
  } = agentState;
  const [expandedThinking, setExpandedThinking] = useState<Record<number, boolean>>({});

  const stepIdToNumber: Record<string, number> = {};
  steps.forEach((step) => {
    stepIdToNumber[step.id] = step.step_number;
    stepIdToNumber[`step-${step.step_number}`] = step.step_number;
  });

  const toolCallsByStep = toolCalls.reduce(
    (acc, toolCall) => {
      const stepNum = stepIdToNumber[toolCall.step_id] ?? currentStep;
      if (!acc[stepNum]) acc[stepNum] = [];
      acc[stepNum].push(toolCall);
      return acc;
    },
    {} as Record<number, AgentToolCall[]>
  );

  const thinkingContentByStep = useMemo(() => {
    const map: Record<number, { content: string; isLive: boolean }> = {};
    for (const step of steps) {
      const historicalThinking = sanitizeThinking(step.thinking_text || '').trim();
      if (historicalThinking) {
        map[step.step_number] = { content: historicalThinking, isLive: false };
      }
    }
    const liveThinking = sanitizeThinking(thinkingBuffer).trim();
    if (isActive && currentStep > 0 && liveThinking) {
      map[currentStep] = { content: liveThinking, isLive: true };
    }
    return map;
  }, [steps, thinkingBuffer, isActive, currentStep]);

  if (steps.length === 0 && systemEvents.length === 0 && !isActive) {
    return null;
  }

  return (
    <div className="mb-3 font-mono text-xs">
      <div className="space-y-3">
        {systemEvents.map((event, index) => (
          <TimelineItem
            key={`system-${event.seq ?? index}`}
            dotClassName="bg-violet-400"
            lineClassName="bg-violet-500/20"
            isLast={steps.length === 0 && index === systemEvents.length - 1}
          >
            <div className="text-violet-200/80">
              <span className="text-violet-400/70">system: </span>
              {event.message}
            </div>
          </TimelineItem>
        ))}
        {steps.map((step) => {
          const isCurrentStep = step.step_number === currentStep;
          const stepToolCalls = toolCallsByStep[step.step_number] || [];
          const thinkingEntry = thinkingContentByStep[step.step_number];
          const stepSteers = injectedSteers.filter((steer) => steer.step_number === step.step_number);
          const itemsCount = stepSteers.length + (thinkingEntry ? 1 : 0) + stepToolCalls.length;
          let itemIndex = 0;

          const nextIsLast = () => {
            itemIndex += 1;
            return itemIndex === itemsCount;
          };

          return (
            <div key={step.id} className="space-y-2">
              {stepSteers.map((steer, index) => (
                <TimelineItem
                  key={`steer-${step.step_number}-${index}`}
                  dotClassName="bg-amber-400"
                  lineClassName="bg-amber-500/20"
                  isLast={nextIsLast()}
                >
                  <div className="text-amber-300/80">
                    <span className="text-amber-500/50">you: </span>
                    {steer.content}
                  </div>
                </TimelineItem>
              ))}

              {thinkingEntry && (
                <TimelineItem
                  dotClassName={thinkingEntry.isLive ? 'bg-cyan-400' : 'bg-zinc-500'}
                  isLast={nextIsLast()}
                >
                  <ThinkingBlock
                    stepNumber={step.step_number}
                    content={thinkingEntry.content}
                    isLive={thinkingEntry.isLive}
                    expanded={!!expandedThinking[step.step_number]}
                    onToggle={() =>
                      setExpandedThinking((current) => ({
                        ...current,
                        [step.step_number]: !current[step.step_number],
                      }))
                    }
                  />
                </TimelineItem>
              )}

              {stepToolCalls.map((toolCall) => (
                <TimelineItem
                  key={toolCall.id}
                  dotClassName={
                    toolCall.status === 'success'
                      ? 'bg-emerald-500'
                      : toolCall.status === 'error' || toolCall.status === 'interrupted'
                        ? 'bg-red-500'
                        : toolCall.status === 'pending'
                          ? 'bg-zinc-500'
                          : 'bg-amber-400'
                  }
                  isLast={nextIsLast()}
                >
                  <ToolCallCard toolCall={toolCall} />
                </TimelineItem>
              ))}

              {itemsCount === 0 && isCurrentStep && isActive && (
                <TimelineItem dotClassName="bg-cyan-400" isLast>
                  <div className="text-zinc-400">step {step.step_number}</div>
                </TimelineItem>
              )}
            </div>
          );
        })}

        {steps.length === 0 && isActive && (
          <TimelineItem dotClassName="bg-zinc-600" isLast>
            <div className="text-zinc-400">awaiting first step</div>
          </TimelineItem>
        )}
      </div>
    </div>
  );
}
