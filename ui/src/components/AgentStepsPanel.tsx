/**
 * Continuous agent activity stream.
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
    <div className="relative pl-7">
      {!isLast && (
        <span
          className={lineClassName || 'absolute left-[7px] top-4 bottom-[-1rem] w-px bg-zinc-800'}
        />
      )}
      <span className={cnBaseDot(dotClassName)} />
      {children}
    </div>
  );
}

function cnBaseDot(className: string): string {
  return `absolute left-0 top-2.5 h-3 w-3 rounded-full border border-black/40 ring-2 ring-black ${className}`;
}

function summarize(content: string): string {
  const line = content
    .split('\n')
    .map((item) => item.trim())
    .find(Boolean) || '';
  return line.length > 88 ? `${line.slice(0, 85)}...` : line;
}

function ThinkingBlock({
  content,
  isLive,
  expanded,
  onToggle,
}: {
  content: string;
  isLive: boolean;
  expanded: boolean;
  onToggle: () => void;
}) {
  const preview = summarize(content);

  return (
    <div className="space-y-2.5 rounded-[1rem] border border-zinc-800/80 bg-zinc-950/62 px-3.5 py-3">
      <button
        type="button"
        onClick={onToggle}
        className="ui-transition flex w-full items-start justify-between gap-3 text-left"
      >
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full border border-zinc-800/85 bg-zinc-950 px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.14em] text-zinc-300">
              thinking
            </span>
            {isLive && (
              <span className="rounded-full border border-cyan-500/24 bg-cyan-500/[0.10] px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.14em] text-cyan-200">
                live
              </span>
            )}
          </div>
          {!expanded && preview && <div className="text-[12px] leading-6 text-zinc-400">{preview}</div>}
        </div>
        <span className="mt-0.5 text-zinc-500">{expanded ? '▾' : '▸'}</span>
      </button>
      {expanded && (
        <div className="rounded-[0.9rem] border border-zinc-800/85 bg-zinc-950/88 px-3 py-3 text-zinc-200">
          <AnswerMarkdown content={content} />
          {isLive && (
            <span className="agent-caret ml-1 inline-block h-3 w-1.5 translate-y-0.5 bg-cyan-400/70" />
          )}
        </div>
      )}
    </div>
  );
}

function formatStepStateLabel(stepState: string, isCurrentStep: boolean, isActive: boolean): string {
  if (isCurrentStep && isActive) return 'live';
  if (stepState === 'tool_calling') return 'tooling';
  if (stepState === 'synthesizing') return 'writing';
  if (stepState === 'planning') return 'thinking';
  if (stepState === 'complete') return 'done';
  if (stepState === 'error') return 'error';
  return stepState.replace(/_/g, ' ');
}

function stepChipClass(stepState: string, isCurrentStep: boolean, isActive: boolean): string {
  if (isCurrentStep && isActive) {
    return 'border-cyan-500/20 bg-cyan-500/[0.09] text-cyan-100';
  }
  if (stepState === 'complete') {
    return 'border-emerald-500/16 bg-emerald-500/[0.08] text-emerald-100';
  }
  if (stepState === 'error') {
    return 'border-red-500/16 bg-red-500/[0.08] text-red-100';
  }
  if (stepState === 'tool_calling') {
    return 'border-amber-500/16 bg-amber-500/[0.08] text-amber-100';
  }
  return 'border-zinc-800/85 bg-zinc-950 text-zinc-300';
}

function PendingStepCard() {
  return (
    <div className="rounded-[1rem] border border-cyan-500/14 bg-cyan-500/[0.04] px-4 py-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="inline-flex h-2 w-2 rounded-full bg-cyan-400 animate-pulse" />
          <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-cyan-100">thinking</span>
        </div>
        <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-zinc-500">waiting for first trace</span>
      </div>
      <div className="mt-3 space-y-2">
        <div className="h-2.5 w-[70%] rounded-full bg-zinc-900 shimmer" />
        <div className="h-2.5 w-[52%] rounded-full bg-zinc-900 shimmer" />
      </div>
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

  if (steps.length === 0 && systemEvents.length === 0) {
    return null;
  }

  return (
    <div className="mb-5 pl-1 font-mono text-xs">
      <div className="space-y-4">
        {systemEvents.map((event, index) => (
          <TimelineItem
            key={`system-${event.seq ?? index}`}
            dotClassName="bg-violet-400"
            lineClassName="absolute left-[7px] top-4 bottom-[-1rem] w-px bg-violet-500/20"
            isLast={steps.length === 0 && index === systemEvents.length - 1}
          >
            <div className="rounded-[1rem] border border-violet-500/14 bg-violet-500/[0.06] px-3.5 py-3 text-[12px] leading-6 text-violet-100/85">
              <span className="mr-1 text-violet-300/80">system:</span>
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
            <div key={step.id} className="space-y-3">
              <div className="pl-7">
                <div className="flex flex-wrap items-center gap-2 font-mono text-[10px] uppercase tracking-[0.18em]">
                  <span className={`rounded-full border px-2 py-0.5 ${stepChipClass(step.state, isCurrentStep, isActive)}`}>
                    {formatStepStateLabel(step.state, isCurrentStep, isActive)}
                  </span>
                  {stepToolCalls.length > 0 ? (
                    <span className="text-zinc-700">{stepToolCalls.length} action{stepToolCalls.length === 1 ? '' : 's'}</span>
                  ) : null}
                </div>
              </div>
              {stepSteers.map((steer, index) => (
                <TimelineItem
                  key={`steer-${step.step_number}-${index}`}
                  dotClassName="bg-amber-400"
                  lineClassName="absolute left-[7px] top-4 bottom-[-1rem] w-px bg-amber-500/20"
                  isLast={nextIsLast()}
                >
                  <div className="rounded-[1rem] border border-amber-500/14 bg-amber-500/[0.06] px-3.5 py-3 text-[12px] leading-6 text-amber-100/85">
                    <span className="mr-1 text-amber-300/80">you:</span>
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
                  <div className="rounded-[1rem] border border-zinc-800/80 bg-zinc-950/58 px-3.5 py-3">
                    <ToolCallCard toolCall={toolCall} />
                  </div>
                </TimelineItem>
              ))}

              {itemsCount === 0 && isCurrentStep && isActive && (
                <TimelineItem dotClassName="bg-cyan-400" isLast>
                  <PendingStepCard />
                </TimelineItem>
              )}
            </div>
          );
        })}

        {steps.length === 0 && isActive && (
          <TimelineItem dotClassName="bg-zinc-600" isLast>
            <PendingStepCard />
          </TimelineItem>
        )}
      </div>
    </div>
  );
}
