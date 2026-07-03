/**
 * Live run status as a single spinner line:
 *   ◜ Working… (12s · 3.2k tok · 19% ctx)
 * Replaces the AgentLiveHUD live card + metric pills.
 */

import { useEffect, useRef, useState } from 'react';
import { CometSpinner } from '@/components/transcript/CometSpinner';
import { formatAgentTokens, useDerivedAgentPhase } from '@/lib/agentLiveState';
import { cn } from '@/lib/utils';
import type { AgentUIState } from '@/types/agent';

function formatElapsedSeconds(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return minutes > 0 ? `${minutes}m ${seconds}s` : `${seconds}s`;
}

export function ElapsedClock({ startedAt }: { startedAt: string }) {
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

export function RunStatusLine({
  runId,
  runCreatedAt,
  agentState,
}: {
  runId: string;
  runCreatedAt: string;
  agentState: AgentUIState;
}) {
  const phase = useDerivedAgentPhase(agentState, runId);
  const startedAt = agentState.steps[0]?.created_at || runCreatedAt;
  const contextPct = agentState.context_usage
    ? `${Math.round(agentState.context_usage.utilization_pct_effective)}% ctx`
    : null;

  return (
    <div className="tr-status-line" data-active={agentState.isActive ? 'true' : 'false'}>
      <CometSpinner active={agentState.isActive} />
      <span className="tr-status-word">{phase.activeWord}…</span>
      <span className="tr-status-meta">
        (<ElapsedClock startedAt={startedAt} />
        {agentState.total_tokens ? ` · ${formatAgentTokens(agentState.total_tokens)} tok` : ''}
        {contextPct ? (
          <span className={cn(phase.isContextWarning && 'tr-warning')}> · {contextPct}</span>
        ) : null}
        )
      </span>
    </div>
  );
}
