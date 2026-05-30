/**
 * Continuous agent activity stream.
 */

import { useMemo, useState } from 'react';
import type { CSSProperties, ReactNode } from 'react';
import { cn, sanitizeThinking } from '@/lib/utils';
import { ToolCallCard } from '@/components/ToolCallCard';
import { AnswerMarkdown } from '@/components/AnswerMarkdown';
import type { AgentToolCall, AgentUIState } from '@/types/agent';

type StepDotTone = 'live' | 'success' | 'error' | 'running' | 'system' | 'steer' | 'default';

function isTimelineNodeActive(dotTone: StepDotTone): boolean {
  return dotTone === 'live' || dotTone === 'running';
}

function computeStepsProgress(
  dotTones: StepDotTone[],
  isActive: boolean,
): number {
  const total = dotTones.length;
  if (total === 0) return 0;
  if (!isActive) return 1;

  const activeIndex = dotTones.findIndex((tone) => isTimelineNodeActive(tone));
  if (activeIndex === -1) return 1;

  return Math.min(1, (activeIndex + 0.35) / total);
}

function TimelineItem({
  dotTone = 'default',
  children,
}: {
  dotTone?: StepDotTone;
  children: ReactNode;
}) {
  return (
    <div className="desktop-step-row relative pl-7">
      <span
        className="desktop-step-dot absolute left-[3px] top-2.5 z-[2] h-2.5 w-2.5 rounded-full border border-[#07080a] bg-zinc-500"
        data-tone={dotTone}
      />
      {children}
    </div>
  );
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
    <div className="desktop-step-thinking desktop-step-block space-y-2">
      <button
        type="button"
        onClick={onToggle}
        className="ui-transition flex w-full items-start justify-between gap-3 text-left"
      >
        <div className="space-y-1">
          <span className="desktop-step-thinking-badge rounded-md border border-white/8 bg-white/[0.04] px-2 py-0.5 text-[11px] text-zinc-400">
            thinking
          </span>
          {!expanded && preview && <div className="text-[12px] leading-6 text-zinc-400">{preview}</div>}
        </div>
        <span className="mt-0.5 text-zinc-500">{expanded ? '▾' : '▸'}</span>
      </button>
      {expanded && (
        <div className="border-t border-white/10 pt-3 text-zinc-200">
          <AnswerMarkdown content={content} />
          {isLive && (
            <span className="desktop-agent-caret agent-caret ml-1 inline-block h-3 w-1.5 translate-y-0.5 bg-cyan-400/70" />
          )}
        </div>
      )}
    </div>
  );
}

function toolCallDotTone(status: AgentToolCall['status']): StepDotTone {
  if (status === 'success') return 'success';
  if (status === 'error' || status === 'interrupted') return 'error';
  if (status === 'pending') return 'default';
  return 'running';
}

function PendingStepCard() {
  return (
    <div className="desktop-step-block desktop-step-thinking">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="inline-flex h-2 w-2 rounded-full bg-cyan-400 animate-pulse" />
          <span className="desktop-step-pending-title text-[11px] font-medium text-cyan-200">Thinking</span>
        </div>
        <span className="text-[11px] text-zinc-500">Waiting for first trace</span>
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

  const timelineDotTones = useMemo(() => {
    const tones: StepDotTone[] = [];

    for (const _event of systemEvents) {
      tones.push('system');
    }

    for (const step of steps) {
      const isCurrentStep = step.step_number === currentStep;
      const stepToolCalls = toolCallsByStep[step.step_number] || [];
      const thinkingEntry = thinkingContentByStep[step.step_number];
      const stepSteers = injectedSteers.filter((steer) => steer.step_number === step.step_number);
      const itemsCount = stepSteers.length + (thinkingEntry ? 1 : 0) + stepToolCalls.length;

      for (const _steer of stepSteers) {
        tones.push('steer');
      }

      if (thinkingEntry) {
        tones.push(thinkingEntry.isLive ? 'live' : 'default');
      }

      for (const toolCall of stepToolCalls) {
        tones.push(toolCallDotTone(toolCall.status));
      }

      if (itemsCount === 0 && isCurrentStep && isActive) {
        tones.push('live');
      }
    }

    if (steps.length === 0 && isActive) {
      tones.push('live');
    }

    return tones;
  }, [
    systemEvents,
    steps,
    toolCallsByStep,
    thinkingContentByStep,
    injectedSteers,
    currentStep,
    isActive,
  ]);

  const stepsProgress = useMemo(
    () => computeStepsProgress(timelineDotTones, isActive),
    [timelineDotTones, isActive],
  );

  if (steps.length === 0 && systemEvents.length === 0) {
    return null;
  }

  return (
    <div className="desktop-agent-steps mb-5 pl-1 text-xs">
      <div
        className={cn(
          'desktop-steps-track relative',
          isActive && 'desktop-steps-track-active',
        )}
        style={{ '--steps-progress': String(stepsProgress) } as CSSProperties}
      >
        <div className="desktop-steps-track-base" aria-hidden />
        <div className="desktop-steps-track-progress" aria-hidden />

        <div className="desktop-steps-stream space-y-5">
          {systemEvents.map((event, index) => (
            <TimelineItem key={`system-${event.seq ?? index}`} dotTone="system">
              <div
                className="desktop-step-block text-[12px] leading-6 text-violet-100/85"
                data-tone="system"
              >
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

            return (
              <div key={step.id} className="space-y-3">
                {stepSteers.map((steer, index) => (
                  <TimelineItem key={`steer-${step.step_number}-${index}`} dotTone="steer">
                    <div
                      className="desktop-step-block text-[12px] leading-6 text-amber-100/85"
                      data-tone="steer"
                    >
                      <span className="mr-1 text-amber-300/80">you:</span>
                      {steer.content}
                    </div>
                  </TimelineItem>
                ))}

                {thinkingEntry && (
                  <TimelineItem dotTone={thinkingEntry.isLive ? 'live' : 'default'}>
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
                  <TimelineItem key={toolCall.id} dotTone={toolCallDotTone(toolCall.status)}>
                    <div className="desktop-step-block">
                      <ToolCallCard toolCall={toolCall} />
                    </div>
                  </TimelineItem>
                ))}

                {itemsCount === 0 && isCurrentStep && isActive && (
                  <TimelineItem dotTone="live">
                    <PendingStepCard />
                  </TimelineItem>
                )}
              </div>
            );
          })}

          {steps.length === 0 && isActive && (
            <TimelineItem dotTone="live">
              <PendingStepCard />
            </TimelineItem>
          )}
        </div>
      </div>
    </div>
  );
}
