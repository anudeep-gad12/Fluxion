/**
 * Continuous agent activity stream.
 * Shows thinking/tool activity inline without boxed step labels.
 */

import { useEffect, useRef, useState } from 'react';
import { cn, sanitizeThinking } from '@/lib/utils';
import { ToolCallCard } from '@/components/ToolCallCard';
import { AnswerMarkdown } from '@/components/AnswerMarkdown';
import type { AgentToolCall, AgentUIState } from '@/types/agent';

/** Map agent state to human-readable label */
const STATE_LABELS: Record<string, { label: string; color: string }> = {
  initializing: { label: 'warming up', color: 'text-zinc-500' },
  running: { label: 'working', color: 'text-cyan-400' },
  planning: { label: 'thinking', color: 'text-cyan-400' },
  tool_calling: { label: 'using tools', color: 'text-amber-400' },
  synthesizing: { label: 'writing answer', color: 'text-emerald-400' },
  paused: { label: 'paused', color: 'text-amber-400' },
  complete: { label: 'done', color: 'text-emerald-500' },
  error: { label: 'error', color: 'text-red-500' },
  cancelled: { label: 'cancelled', color: 'text-zinc-500' },
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
          <span className={cn('truncate', stateInfo.color)}>{stateInfo.label}</span>
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

      <div className="space-y-2 border-l border-zinc-800 pl-3">
        {steps.map((step) => {
          const isCurrentStep = step.step_number === currentStep;
          const stepToolCalls = toolCallsByStep[step.step_number] || [];
          const historicalThinking = sanitizeThinking(step.thinking_text || '').trim();
          const liveThinking = sanitizeThinking(thinkingBuffer).trim();
          const stepSteers = injectedSteers.filter((s) => s.step_number === step.step_number);

          return (
            <div key={step.id} className="space-y-2">
              {stepSteers.map((steer, index) => (
                <div key={`steer-${step.step_number}-${index}`} className="text-amber-300/80">
                  <span className="text-amber-500/50">you: </span>
                  {steer.content}
                </div>
              ))}

              {historicalThinking && !(isCurrentStep && isActive) && (
                <div className="thinking-markdown text-zinc-500">
                  <AnswerMarkdown content={historicalThinking} />
                </div>
              )}

              {isCurrentStep && isActive && liveThinking && (
                <div className="text-zinc-500">
                  <AnswerMarkdown content={liveThinking} />
                  <span className="ml-1 inline-block h-3 w-1.5 translate-y-0.5 bg-cyan-400/70 agent-caret" />
                </div>
              )}

              {stepToolCalls.map((toolCall) => (
                <ToolCallCard key={toolCall.id} toolCall={toolCall} />
              ))}
            </div>
          );
        })}

        {steps.length === 0 && isActive && (
          <div className="flex items-center gap-2 text-zinc-500">
            <AgentLoader state={currentState} />
            <span>starting agent</span>
          </div>
        )}
      </div>
    </div>
  );
}
