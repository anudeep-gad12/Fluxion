import { AgentLiveHUD } from '@/components/AgentLiveHUD';
import type { AgentUIState } from '@/types/agent';

interface DesktopAgentStatusBarProps {
  runId: string;
  runCreatedAt: string;
  agentState: AgentUIState;
  onImplementationStarted?: (run: {
    run_id: string;
    stream_token?: string;
    stream_url?: string;
  }) => void;
}

/** One-line live status + expandable approval panel (desktop presentation). */
export function DesktopAgentStatusBar(props: DesktopAgentStatusBarProps) {
  return <AgentLiveHUD {...props} variant="desktop" />;
}
