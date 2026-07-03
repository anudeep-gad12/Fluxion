/**
 * Live agent status surface — thin dispatcher.
 * Blocking states (approval / plan / user input) render as flat inline
 * prompts; otherwise a single spinner status line. The old HUD card,
 * metric pills, and kind-colored panels are gone.
 */

import { memo, useMemo } from 'react';
import { InlinePrompts } from '@/components/transcript/InlinePrompts';
import { RunStatusLine } from '@/components/transcript/RunStatusLine';
import type { AgentUIState } from '@/types/agent';

interface AgentLiveHUDProps {
  runId: string;
  runCreatedAt: string;
  agentState: AgentUIState;
  variant?: 'default' | 'desktop';
  onImplementationStarted?: (run: {
    run_id: string;
    stream_token?: string;
    stream_url?: string;
  }) => void;
}

export const AgentLiveHUD = memo(function AgentLiveHUD({
  runId,
  runCreatedAt,
  agentState,
  onImplementationStarted,
}: AgentLiveHUDProps) {
  const hasPendingApproval = useMemo(
    () =>
      agentState.toolCalls.some(
        (toolCall) => toolCall.status === 'pending' && toolCall.approval_required,
      ),
    [agentState.toolCalls]
  );

  const hasBlockingState =
    agentState.pendingPlanApproval?.status === 'pending'
    || !!agentState.pendingUserInput
    || hasPendingApproval;

  return (
    <div className="desktop-thread-column flex-shrink-0">
      {hasBlockingState ? (
        <InlinePrompts
          agentState={agentState}
          onImplementationStarted={onImplementationStarted}
        />
      ) : (
        <RunStatusLine runId={runId} runCreatedAt={runCreatedAt} agentState={agentState} />
      )}
    </div>
  );
});
