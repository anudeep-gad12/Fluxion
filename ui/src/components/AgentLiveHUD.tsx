import { memo, useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';
import { formatAgentCost, formatAgentTokens, useDerivedAgentPhase } from '@/lib/agentLiveState';
import type { AgentUIState } from '@/types/agent';

function formatElapsedSeconds(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return minutes > 0 ? `${minutes}m ${seconds}s` : `${seconds}s`;
}

function ElapsedClock({ startedAt }: { startedAt: string }) {
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const startRef = useRef(new Date(startedAt).getTime());

  useEffect(() => {
    startRef.current = new Date(startedAt).getTime();
    setElapsedSeconds(Math.max(0, Math.floor((Date.now() - startRef.current) / 1000)));
  }, [startedAt]);

  useEffect(() => {
    const interval = window.setInterval(() => {
      setElapsedSeconds(Math.max(0, Math.floor((Date.now() - startRef.current) / 1000)));
    }, 1000);
    return () => window.clearInterval(interval);
  }, []);

  return <span>{formatElapsedSeconds(elapsedSeconds)}</span>;
}

function AgentLoader({ gradientClassName, paused }: { gradientClassName: string; paused: boolean }) {
  return (
    <span className="relative inline-flex h-8 w-10 shrink-0 items-center justify-center overflow-hidden rounded-sm border border-zinc-800/80 bg-black/50 shadow-[inset_0_0_18px_rgba(255,255,255,0.03)]">
      <span className="absolute inset-x-1 top-1/2 h-px -translate-y-1/2 bg-zinc-800/90" />
      {!paused && <span className={cn('agent-scan absolute inset-x-1 top-1/2 h-px -translate-y-1/2 bg-gradient-to-r', gradientClassName)} />}
      <span className={cn('absolute left-1.5 h-1.5 w-1.5 rounded-full bg-cyan-300', !paused && 'agent-dot agent-dot-a')} />
      <span className={cn('absolute h-1.5 w-1.5 rounded-full bg-amber-300', !paused && 'agent-dot agent-dot-b')} />
      <span className={cn('absolute right-1.5 h-1.5 w-1.5 rounded-full bg-emerald-300', !paused && 'agent-dot agent-dot-c')} />
    </span>
  );
}

function MetricChip({
  label,
  value,
  emphasized = false,
  warning = false,
}: {
  label: string;
  value: ReactNode;
  emphasized?: boolean;
  warning?: boolean;
}) {
  return (
    <div
      className={cn(
        'inline-flex items-center gap-1.5 rounded-sm border px-2 py-1 whitespace-nowrap',
        warning ? 'border-amber-500/20 bg-amber-500/8' : 'border-zinc-800 bg-black/35'
      )}
    >
      <span className={cn('text-[10px] uppercase tracking-[0.18em]', warning ? 'text-amber-300/70' : 'text-zinc-500')}>
        {label}
      </span>
      <span className={cn('tabular-nums text-zinc-300', emphasized && 'text-zinc-100')}>
        {value}
      </span>
    </div>
  );
}

function WordSwap({ className, value }: { className?: string; value: string }) {
  return (
    <span className={cn('relative inline-flex min-h-[1.2rem] items-center overflow-hidden', className)}>
      <span key={value} className="animate-in fade-in slide-in-from-bottom-1 duration-300">
        {value}
      </span>
    </span>
  );
}

interface AgentLiveHUDProps {
  runId: string;
  runCreatedAt: string;
  agentState: AgentUIState;
}

export const AgentLiveHUD = memo(function AgentLiveHUD({
  runId,
  runCreatedAt,
  agentState,
}: AgentLiveHUDProps) {
  const phase = useDerivedAgentPhase(agentState, runId);
  const startedAt = agentState.steps[0]?.created_at || runCreatedAt;
  const isPaused = phase.phase === 'paused';
  const currentContextPct = agentState.context_usage
    ? `${Math.round(agentState.context_usage.utilization_pct_effective)}%`
    : '—';
  const compactionCount = (agentState.compaction_count ?? agentState.context_usage?.compactions_so_far) ?? 0;
  const currentStep = Math.max(agentState.currentStep, agentState.steps.length);
  const hasLimit = agentState.maxSteps > 0;




  return (
    <div className="flex-shrink-0 px-3 pb-2 sm:px-4 md:px-6">
      <div
        className={cn(
          'animate-in fade-in slide-in-from-bottom-2 relative overflow-hidden rounded-md border bg-zinc-950/92 font-mono text-xs shadow-[0_-14px_36px_rgba(0,0,0,0.28)] backdrop-blur-md',
          phase.borderClassName,
          isPaused && 'bg-zinc-950/96'
        )}
      >
        <div className={cn('pointer-events-none absolute inset-y-0 left-0 w-px bg-gradient-to-b', phase.glowClassName)} />
        <div className={cn('pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r', phase.glowClassName)} />

        <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-3 px-3 py-2.5">
          <div className="flex min-w-0 flex-1 items-start gap-3">
            <AgentLoader gradientClassName={phase.loaderGradientClassName} paused={isPaused} />

            <div className="min-w-0 flex-1 space-y-1">
              <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
                <span className={cn('h-1.5 w-1.5 shrink-0 rounded-full shadow-[0_0_10px_rgba(255,255,255,0.14)]', phase.indicatorClassName)} />
                <WordSwap className={cn('truncate text-[13px] leading-none', phase.accentClassName)} value={phase.activeWord} />
                {phase.detail.toolName && (
                  <span className={cn('rounded-sm border px-1.5 py-0.5 text-[10px] uppercase tracking-[0.18em]', phase.chipClassName)}>
                    {phase.detail.toolName}
                  </span>
                )}
              </div>

              <div className="min-w-0 text-[11px] leading-relaxed text-zinc-400">
                <span key={`${phase.detail.summary}:${phase.detail.target ?? ''}`} className="animate-in fade-in duration-200 inline-flex min-w-0 max-w-full flex-wrap items-center gap-1">
                  <span>{phase.detail.summary}</span>
                  {phase.detail.target && <span className="text-zinc-600">→</span>}
                  {phase.detail.target && <span className="truncate text-zinc-300">{phase.detail.target}</span>}
                </span>
              </div>
            </div>
          </div>

          <div className="ml-auto flex items-center gap-2 text-[10px] uppercase tracking-[0.18em] text-zinc-600">
            {isPaused ? 'paused' : 'live'}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 border-t border-zinc-900/90 px-3 py-2 text-zinc-400">
          <MetricChip label="step" value={currentStep || 0} emphasized />
          {hasLimit ? <MetricChip label="limit" value={agentState.maxSteps} /> : null}
          <MetricChip label="ctx" value={currentContextPct} warning={phase.isContextWarning} />
          <MetricChip label="compact" value={String(compactionCount)} warning={phase.isCompactionWarning} />
          <MetricChip label="elapsed" value={<ElapsedClock startedAt={startedAt} />} />
          {agentState.total_tokens ? <MetricChip label="tok" value={formatAgentTokens(agentState.total_tokens)} /> : null}
          {agentState.cost && agentState.usage?.total_tokens ? (
            <MetricChip label="est" value={formatAgentCost(agentState.cost.total_cost)} />
          ) : null}
        </div>
      </div>
    </div>
  );
});
