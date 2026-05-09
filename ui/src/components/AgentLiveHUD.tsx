import { memo, useEffect, useMemo, useRef, useState } from 'react';
import { approveAgentToolCall, denyAgentToolCall } from '@/api/client';
import { cn } from '@/lib/utils';
import { formatAgentCost, formatAgentTokens, useDerivedAgentPhase } from '@/lib/agentLiveState';
import type { AgentToolCall } from '@/types/agent';
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

function formatApprovalArguments(toolCall: AgentToolCall): string {
  const args = toolCall.arguments || {};
  if (typeof args.file_path === 'string' && args.file_path.trim()) return args.file_path;
  if (typeof args.path === 'string' && args.path.trim()) return args.path;
  if (typeof args.pattern === 'string' && args.pattern.trim()) return args.pattern;
  if (typeof args.command === 'string' && args.command.trim()) return args.command;
  if (typeof args.url === 'string' && args.url.trim()) return args.url;
  if (typeof args.query === 'string' && args.query.trim()) return args.query;
  return '';
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
  const [deciding, setDeciding] = useState<'approve' | 'deny' | null>(null);
  const pendingApproval = useMemo(
    () =>
      [...agentState.toolCalls]
        .reverse()
        .find((toolCall) => toolCall.status === 'pending' && toolCall.approval_required),
    [agentState.toolCalls]
  );

  useEffect(() => {
    if (!pendingApproval) {
      setDeciding(null);
    }
  }, [pendingApproval]);

  const decide = async (decision: 'approve' | 'deny') => {
    if (!pendingApproval) return;
    setDeciding(decision);
    try {
      if (decision === 'approve') {
        await approveAgentToolCall(pendingApproval.run_id, pendingApproval.id);
      } else {
        await denyAgentToolCall(pendingApproval.run_id, pendingApproval.id);
      }
    } finally {
      setDeciding(null);
    }
  };

  return (
    <div className="flex-shrink-0 px-3 pb-2 sm:px-4 md:px-6">
      <div className="ui-panel ui-elevated animate-in fade-in slide-in-from-bottom-2 duration-200 rounded-[1.2rem] border border-cyan-500/18 px-3.5 py-3 font-mono text-xs">
        {pendingApproval ? (
          <div className="space-y-3">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <div className="flex min-w-0 flex-wrap items-center gap-2">
                  <span className="h-2 w-2 rounded-full bg-amber-300/90" />
                  <span className="text-[11px] uppercase tracking-[0.18em] text-amber-200">
                    permission
                  </span>
                  <span className="text-zinc-600">/</span>
                  <span className="truncate text-[12px] text-zinc-100">
                    {pendingApproval.tool_name.replace(/_/g, ' ')}
                  </span>
                </div>
                <div className="mt-1.5 flex min-w-0 flex-wrap items-center gap-2 text-[11px] text-zinc-500">
                  {pendingApproval.permission_level ? (
                    <span className="rounded-full border border-amber-500/18 bg-amber-500/[0.08] px-2 py-0.5 uppercase tracking-[0.14em] text-amber-100">
                      {pendingApproval.permission_level}
                    </span>
                  ) : null}
                  {formatApprovalArguments(pendingApproval) ? (
                    <span className="truncate text-zinc-300">
                      {formatApprovalArguments(pendingApproval)}
                    </span>
                  ) : null}
                </div>
              </div>

              <div className="rounded-full border border-amber-500/24 bg-amber-500/[0.09] px-2.5 py-1 text-[10px] uppercase tracking-[0.18em] text-amber-100">
                waiting
              </div>
            </div>

            {typeof pendingApproval.diff_preview === 'string' && pendingApproval.diff_preview.trim() ? (
              <pre className="max-h-48 overflow-auto rounded-[1rem] border border-zinc-800/90 bg-zinc-950/92 px-3 py-3 whitespace-pre-wrap text-[11px] leading-6 text-zinc-300">
                {pendingApproval.diff_preview}
              </pre>
            ) : null}

            <div className="flex flex-wrap items-center gap-2 border-t border-zinc-900/90 pt-3">
              <button
                type="button"
                onClick={() => decide('approve')}
                disabled={deciding !== null}
                className="ui-transition rounded-full border border-emerald-500/20 bg-emerald-500/[0.08] px-3 py-1.5 text-[11px] uppercase tracking-[0.16em] text-emerald-100 hover:border-emerald-400/30 hover:text-white disabled:cursor-not-allowed disabled:border-zinc-800 disabled:bg-zinc-900 disabled:text-zinc-500"
              >
                {deciding === 'approve' ? 'approving…' : 'approve'}
              </button>
              <button
                type="button"
                onClick={() => decide('deny')}
                disabled={deciding !== null}
                className="ui-transition rounded-full border border-red-500/20 bg-red-500/[0.08] px-3 py-1.5 text-[11px] uppercase tracking-[0.16em] text-red-100 hover:border-red-400/30 hover:text-white disabled:cursor-not-allowed disabled:border-zinc-800 disabled:bg-zinc-900 disabled:text-zinc-500"
              >
                {deciding === 'deny' ? 'denying…' : 'deny'}
              </button>
              <MetricPill label="elapsed" value={<ElapsedClock startedAt={startedAt} />} />
            </div>
          </div>
        ) : (
          <>
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
              <MetricPill label="ctx" value={currentContextPct} caution={phase.isContextWarning} />
              <MetricPill label="compact" value={String(compactionCount)} caution={phase.isCompactionWarning} />
              <MetricPill label="elapsed" value={<ElapsedClock startedAt={startedAt} />} />
              {agentState.total_tokens ? <MetricPill label="tok" value={formatAgentTokens(agentState.total_tokens)} /> : null}
              {agentState.cost && agentState.usage?.total_tokens ? (
                <MetricPill label="est" value={formatAgentCost(agentState.cost.total_cost)} />
              ) : null}
            </div>
          </>
        )}
      </div>
    </div>
  );
});
