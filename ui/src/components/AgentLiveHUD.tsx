import { memo, useEffect, useRef, useState } from 'react';
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

function MetricPill({
  label,
  value,
  highlighted = false,
  caution = false,
}: {
  label: string;
  value: string | number | JSX.Element;
  highlighted?: boolean;
  caution?: boolean;
}) {
  return (
    <div
      className={cn(
        'ui-transition inline-flex items-center gap-2 rounded-full border px-2.5 py-1',
        caution
          ? 'border-amber-500/20 bg-amber-500/8 text-amber-200'
          : 'border-cyan-500/18 bg-cyan-500/[0.07] text-zinc-300'
      )}
    >
      <span className="text-[10px] uppercase tracking-[0.18em] text-zinc-500">{label}</span>
      <span className={cn('tabular-nums text-[11px]', highlighted ? 'text-zinc-50' : 'text-current')}>
        {value}
      </span>
    </div>
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
  const currentContextPct = agentState.context_usage
    ? `${Math.round(agentState.context_usage.utilization_pct_effective)}%`
    : '—';
  const compactionCount = (agentState.compaction_count ?? agentState.context_usage?.compactions_so_far) ?? 0;
  const currentStep = Math.max(agentState.currentStep, agentState.steps.length);

  return (
    <div className="flex-shrink-0 px-3 pb-2 sm:px-4 md:px-6">
      <div className="ui-panel ui-elevated animate-in fade-in slide-in-from-bottom-2 duration-200 rounded-[1.2rem] border border-cyan-500/18 px-3.5 py-3 font-mono text-xs">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex min-w-0 flex-wrap items-center gap-2">
              <span className={cn('h-2 w-2 rounded-full', phase.indicatorClassName)} />
              <span className={cn('text-[11px] uppercase tracking-[0.18em]', phase.accentClassName)}>
                {phase.activeWord}
              </span>
              <span className="text-zinc-600">/</span>
              <span className="truncate text-[12px] text-zinc-100">{phase.detail.summary}</span>
            </div>
            <div className="mt-1.5 flex min-w-0 flex-wrap items-center gap-2 text-[11px] text-zinc-500">
              <span>step {currentStep || 1}</span>
              {phase.detail.target ? <span className="text-zinc-700">→</span> : null}
              {phase.detail.target ? (
                <span className="truncate text-zinc-300">{phase.detail.target}</span>
              ) : null}
              {phase.detail.toolName ? (
                <span className="rounded-full border border-cyan-500/20 bg-cyan-500/[0.07] px-2 py-0.5 uppercase tracking-[0.14em] text-cyan-100">
                  {phase.detail.toolName}
                </span>
              ) : null}
            </div>
          </div>

          <div className="rounded-full border border-cyan-500/24 bg-cyan-500/[0.09] px-2.5 py-1 text-[10px] uppercase tracking-[0.18em] text-cyan-100">
            live
          </div>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-zinc-900/90 pt-3">
          <MetricPill label="step" value={currentStep || 0} highlighted />
          <MetricPill label="ctx" value={currentContextPct} caution={phase.isContextWarning} />
          <MetricPill label="compact" value={String(compactionCount)} caution={phase.isCompactionWarning} />
          <MetricPill label="elapsed" value={<ElapsedClock startedAt={startedAt} />} />
          {agentState.total_tokens ? <MetricPill label="tok" value={formatAgentTokens(agentState.total_tokens)} /> : null}
          {agentState.cost && agentState.usage?.total_tokens ? (
            <MetricPill label="est" value={formatAgentCost(agentState.cost.total_cost)} />
          ) : null}
        </div>
      </div>
    </div>
  );
});
