/**
 * Continuous agent activity stream.
 * Shows thinking/tool activity inline without boxed step labels.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { cn, sanitizeThinking } from '@/lib/utils';
import { ToolCallCard } from '@/components/ToolCallCard';
import { AnswerMarkdown } from '@/components/AnswerMarkdown';
import type { AgentToolCall, AgentUIState } from '@/types/agent';

/** Map agent state to human-readable label */
const STATE_LABELS: Record<string, { label: string; color: string }> = {
  initializing: { label: 'warming up', color: 'text-zinc-500' },
  running: { label: 'agenting', color: 'text-cyan-400' },
  planning: { label: 'llming', color: 'text-cyan-400' },
  tool_calling: { label: 'tooling', color: 'text-amber-400' },
  synthesizing: { label: 'landing', color: 'text-emerald-400' },
  paused: { label: 'paused', color: 'text-amber-400' },
  complete: { label: 'done', color: 'text-emerald-500' },
  error: { label: 'error', color: 'text-red-500' },
  cancelled: { label: 'cancelled', color: 'text-zinc-500' },
};

const ACTIVE_WORDS: Record<string, string[]> = {
  initializing: ['warming up', 'booting'],
  running: ['agenting', 'working', 'routing'],
  planning: ['thinking...', 'llming', 'mapping'],
  tool_calling: ['tooling', 'patching', 'probing'],
  synthesizing: ['writing', 'landing', 'wrapping'],
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

function AgentLoader({ state }: { state: string }) {
  const color =
    state === 'tool_calling'
      ? 'from-amber-500 via-orange-300 to-amber-500'
      : state === 'synthesizing'
        ? 'from-emerald-500 via-lime-300 to-emerald-500'
        : 'from-cyan-500 via-sky-300 to-cyan-500';

  return (
    <span className="relative inline-flex h-5 w-9 shrink-0 items-center justify-center overflow-hidden">
      <span className="absolute h-px w-8 bg-zinc-800" />
      <span className={cn('agent-scan absolute h-px w-5 bg-gradient-to-r', color)} />
      <span className="agent-dot agent-dot-a absolute h-1.5 w-1.5 rounded-full bg-cyan-400" />
      <span className="agent-dot agent-dot-b absolute h-1.5 w-1.5 rounded-full bg-amber-300" />
      <span className="agent-dot agent-dot-c absolute h-1.5 w-1.5 rounded-full bg-emerald-400" />
    </span>
  );
}

function useAnimatedStateLabel(state: string, isActive: boolean): string {
  const words = ACTIVE_WORDS[state];
  const [index, setIndex] = useState(0);

  useEffect(() => {
    setIndex(0);
  }, [state]);

  useEffect(() => {
    if (!isActive || !words || words.length <= 1) {
      return;
    }
    const interval = setInterval(() => {
      setIndex((current) => (current + 1) % words.length);
    }, 1300);
    return () => clearInterval(interval);
  }, [isActive, words]);

  return words?.[index] || STATE_LABELS[state]?.label || state;
}

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
          className={cn(
            'absolute left-[3px] top-3 bottom-[-0.75rem] w-px bg-zinc-800',
            lineClassName
          )}
        />
      )}
      <span className={cn('absolute left-0 top-2 h-2 w-2 rounded-full', dotClassName)} />
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
        className="flex items-center gap-2 text-left text-zinc-500 hover:text-zinc-300 transition-colors"
      >
        <span className="text-zinc-700 select-none">{expanded ? '▼' : '▶'}</span>
        <span>{isLive ? 'thinking...' : 'thinking'}</span>
        {isLive && <span className="text-cyan-400/70">live</span>}
      </button>
      {expanded && (
        <div className="rounded-sm border border-zinc-900 bg-zinc-950/50 px-3 py-2 text-zinc-500">
          <AnswerMarkdown content={content} />
          {isLive && (
            <span className="ml-1 inline-block h-3 w-1.5 translate-y-0.5 bg-cyan-400/70 agent-caret" />
          )}
        </div>
      )}
      {!expanded && isLive && (
        <div className="text-[11px] text-zinc-700">step {stepNumber}</div>
      )}
    </div>
  );
}

interface AgentStepsPanelProps {
  agentState: AgentUIState;
  defaultExpanded?: boolean;
}

export function AgentStepsPanel({ agentState }: AgentStepsPanelProps) {
  const {
    steps,
    toolCalls,
    thinkingBuffer,
    currentStep,
    isActive,
    total_tokens,
    usage,
    cost,
    context_usage,
    context_tokens,
    context_remaining,
    injectedSteers,
  } = agentState;
  const [expandedThinking, setExpandedThinking] = useState<Record<number, boolean>>({});

  const currentState = (() => {
    if (!isActive && agentState.agentState === 'complete') return 'complete';
    if (!isActive && agentState.agentState === 'error') return 'error';
    if (!isActive && agentState.agentState === 'cancelled') return 'cancelled';
    if (agentState.answerBuffer) return 'synthesizing';
    if (toolCalls.some((tc) => tc.status === 'running' || tc.status === 'pending')) {
      return 'tool_calling';
    }
    if (thinkingBuffer) return 'planning';
    if (isActive) return 'running';
    return agentState.agentState || 'initializing';
  })();

  const stateInfo = STATE_LABELS[currentState] || STATE_LABELS.running;
  const animatedLabel = useAnimatedStateLabel(currentState, isActive);
  const firstStepTime = steps.length > 0 ? steps[0].created_at : undefined;

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

  if (steps.length === 0 && !isActive) {
    return null;
  }

  return (
    <div className="mb-3 font-mono text-xs">
      <div className="mb-2 flex items-center justify-between gap-3 text-xs">
        <div className="flex min-w-0 items-center gap-2">
          {isActive && currentState !== 'paused' ? (
            <AgentLoader state={currentState} />
          ) : (
            <span
              className={cn(
                'h-1.5 w-1.5 shrink-0 rounded-full',
                currentState === 'complete'
                  ? 'bg-emerald-500'
                  : currentState === 'error'
                    ? 'bg-red-500'
                    : currentState === 'paused'
                      ? 'bg-amber-400'
                      : 'bg-zinc-600'
              )}
            />
          )}
          <span className={cn('truncate', stateInfo.color)}>{isActive ? animatedLabel : stateInfo.label}</span>
        </div>

        <div className="flex shrink-0 items-center gap-3 text-zinc-600">
          {isActive && firstStepTime && <ElapsedTimer startedAt={firstStepTime} />}
          {total_tokens && total_tokens > 0 && <span>{total_tokens.toLocaleString()} tok</span>}
          {cost && usage?.total_tokens ? (
            <span>est ${cost.total_cost < 0.01 ? cost.total_cost.toFixed(4) : cost.total_cost.toFixed(2)}</span>
          ) : null}
          {context_tokens != null && context_tokens > 0 && (
            <span className={context_remaining != null && context_remaining < 20000 ? 'text-amber-500' : ''}>
              {Math.round(context_tokens / 1000)}k ctx est
            </span>
          )}
          {!context_tokens && context_usage && <span>ctx est {Math.round(context_usage.utilization_pct)}%</span>}
        </div>
      </div>

      {(usage || context_usage || context_tokens != null) && (
        <div className="mb-2 grid grid-cols-2 gap-2 text-[11px] text-zinc-500 sm:grid-cols-4">
          <div className="bg-zinc-950/60 border border-zinc-900 px-2 py-1">
            <span className="text-zinc-700">input </span>
            {usage?.input_tokens?.toLocaleString() ?? '—'}
          </div>
          <div className="bg-zinc-950/60 border border-zinc-900 px-2 py-1">
            <span className="text-zinc-700">output </span>
            {usage?.output_tokens?.toLocaleString() ?? '—'}
          </div>
          <div className="bg-zinc-950/60 border border-zinc-900 px-2 py-1">
            <span className="text-zinc-700">ctx est </span>
            {context_tokens != null
              ? `${Math.round(context_tokens / 1000)}k`
              : context_usage
                ? `${Math.round(context_usage.utilization_pct)}%`
                : '—'}
          </div>
          <div className="bg-zinc-950/60 border border-zinc-900 px-2 py-1">
            <span className="text-zinc-700">cost </span>
            {cost && usage?.total_tokens
              ? `$${cost.total_cost < 0.01 ? cost.total_cost.toFixed(4) : cost.total_cost.toFixed(2)}`
              : 'n/a'}
          </div>
        </div>
      )}

      <div className="space-y-3">
        {steps.map((step) => {
          const isCurrentStep = step.step_number === currentStep;
          const stepToolCalls = toolCallsByStep[step.step_number] || [];
          const thinkingEntry = thinkingContentByStep[step.step_number];
          const stepSteers = injectedSteers.filter((s) => s.step_number === step.step_number);
          const itemsCount =
            stepSteers.length +
            (thinkingEntry ? 1 : 0) +
            stepToolCalls.length;
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
                  <div className="text-zinc-600">step {step.step_number}</div>
                </TimelineItem>
              )}
            </div>
          );
        })}

        {steps.length === 0 && isActive && (
          <TimelineItem dotClassName="bg-cyan-400" isLast>
            <div className="flex items-center gap-2 text-zinc-500">
              <AgentLoader state={currentState} />
              <span>starting agent</span>
            </div>
          </TimelineItem>
        )}
      </div>
    </div>
  );
}
