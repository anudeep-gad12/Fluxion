import type { MouseEvent } from 'react';
import { Plus, Terminal, X } from 'lucide-react';
import { toast } from 'sonner';

import {
  ApiError,
  closeTerminalSession,
  createTerminalSession,
  type TerminalSessionResponse,
} from '@/api/client';
import { useStore } from '@/hooks/useStore';
import { cn } from '@/lib/utils';

function sessionLabel(session: TerminalSessionResponse): string {
  if (session.title?.trim()) {
    return session.title.trim();
  }
  const shell = session.shell || '';
  const parts = shell.split('/');
  return parts[parts.length - 1] || 'shell';
}

interface TerminalSessionRailProps {
  conversationId: string;
  workspacePath: string;
  sessions: TerminalSessionResponse[];
  activeSessionId: string | null;
  maxSessions: number;
  onSelect: (sessionId: string) => void;
  onSessionsChange: (
    sessions: TerminalSessionResponse[],
    activeSessionId: string | null,
  ) => void;
}

export function TerminalSessionRail({
  conversationId,
  workspacePath,
  sessions,
  activeSessionId,
  maxSessions,
  onSelect,
  onSessionsChange,
}: TerminalSessionRailProps) {
  const updateTerminalState = useStore((s) => s.updateTerminalState);
  const atLimit = sessions.length >= maxSessions;

  const handleNewSession = async () => {
    if (atLimit) {
      toast.error(`Maximum ${maxSessions} terminals for this conversation`);
      return;
    }
    try {
      const created = await createTerminalSession(conversationId, {
        workspace_path: workspacePath.trim() || undefined,
        cols: 120,
        rows: 30,
      });
      const nextSessions = [...sessions, created];
      onSessionsChange(nextSessions, created.session_id);
      updateTerminalState(conversationId, {
        sessions: nextSessions,
        activeSessionId: created.session_id,
        session: created,
        buffer: created.replay_buffer || '',
        status: created.status === 'running' ? 'running' : 'stale',
      });
      localStorage.setItem(
        `reasoner_terminal_active_session:${conversationId}`,
        created.session_id,
      );
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        toast.error(`Maximum ${maxSessions} terminals for this conversation`);
        return;
      }
      toast.error('Could not create terminal');
    }
  };

  const handleCloseSession = async (sessionId: string, event: MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    try {
      await closeTerminalSession(conversationId, sessionId);
      const nextSessions = sessions.filter((item) => item.session_id !== sessionId);
      const nextActiveId =
        activeSessionId === sessionId
          ? (nextSessions[0]?.session_id ?? null)
          : activeSessionId;
      onSessionsChange(nextSessions, nextActiveId);
      const current = useStore.getState().terminalByConversation[conversationId];
      if (!current) return;
      const bufferBySessionId = { ...current.bufferBySessionId };
      delete bufferBySessionId[sessionId];
      const activeSession = nextActiveId
        ? nextSessions.find((item) => item.session_id === nextActiveId) ?? null
        : null;
      updateTerminalState(conversationId, {
        sessions: nextSessions,
        activeSessionId: nextActiveId,
        session: activeSession,
        buffer: nextActiveId ? (bufferBySessionId[nextActiveId] ?? '') : '',
        bufferBySessionId,
        connected: false,
        status: 'idle',
      });
      if (nextActiveId) {
        localStorage.setItem(
          `reasoner_terminal_active_session:${conversationId}`,
          nextActiveId,
        );
      } else {
        localStorage.removeItem(`reasoner_terminal_active_session:${conversationId}`);
      }
    } catch {
      toast.error('Could not close terminal');
    }
  };

  return (
    <div className="desktop-terminal-tabs flex h-10 shrink-0 items-center gap-1 border-b border-white/[0.06] bg-[var(--desktop-bg-0)] px-2">
      <div className="min-w-0 flex-1 overflow-x-auto">
        <div className="flex min-w-max items-center gap-1">
          {sessions.map((session) => {
            const isActive = session.session_id === activeSessionId;
            return (
              <div
                key={session.session_id}
                className={cn('desktop-terminal-tab', isActive && 'is-active')}
              >
                <button
                  type="button"
                  onClick={() => onSelect(session.session_id)}
                  className="desktop-terminal-tab-select desktop-no-drag"
                  title={sessionLabel(session)}
                >
                  <Terminal className="h-3 w-3 shrink-0 opacity-55" aria-hidden />
                  <span className="truncate">{sessionLabel(session)}</span>
                </button>
                <button
                  type="button"
                  onClick={(event) => void handleCloseSession(session.session_id, event)}
                  className="desktop-terminal-tab-close desktop-no-drag"
                  aria-label={`Close ${sessionLabel(session)}`}
                >
                  <X className="h-3 w-3" strokeWidth={2} />
                </button>
              </div>
            );
          })}
        </div>
      </div>
      <div className="shrink-0">
        <button
          type="button"
          onClick={() => void handleNewSession()}
          disabled={atLimit}
          className={cn(
            'desktop-no-drag flex h-6 w-6 items-center justify-center rounded-md text-zinc-500 transition-colors',
            atLimit
              ? 'cursor-not-allowed opacity-40'
              : 'hover:bg-white/[0.06] hover:text-zinc-200'
          )}
          title={atLimit ? `Maximum ${maxSessions} terminals` : 'New terminal'}
          aria-label="New terminal"
        >
          <Plus className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}
