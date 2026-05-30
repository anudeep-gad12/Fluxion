import { useCallback, useEffect, useRef, useState } from 'react';
import { PanelRightClose, GripVertical } from 'lucide-react';
import { IntegratedTerminal } from '@/components/IntegratedTerminal';
import { DesktopTitlebar } from '@/components/desktop/DesktopTitlebar';
import { TerminalSessionRail } from '@/components/desktop/TerminalSessionRail';
import {
  createTerminalSession,
  listTerminalSessions,
  type TerminalSessionResponse,
} from '@/api/client';
import { useStore, useConversationTerminal } from '@/hooks/useStore';
import { isLocalDesktopApp } from '@/lib/platform';
import { Button } from '@/components/ui/button';

const TERMINAL_WIDTH_KEY = 'reasoner_terminal_panel_width';
const DEFAULT_WIDTH = 380;
const MIN_WIDTH = 320;
const MAX_WIDTH = 560;

function readTerminalWidth(): number {
  if (typeof window === 'undefined') return DEFAULT_WIDTH;
  const stored = Number(localStorage.getItem(TERMINAL_WIDTH_KEY));
  if (!Number.isFinite(stored)) return DEFAULT_WIDTH;
  return Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, stored));
}

function workspaceFolderLabel(workspacePath: string): string {
  const trimmed = workspacePath.trim();
  if (!trimmed) return '';
  return trimmed.split('/').filter(Boolean).pop() || trimmed;
}

interface TerminalPanelProps {
  /** Agent mode active in conversation view */
  agentModeActive: boolean;
}

export function TerminalPanel({ agentModeActive }: TerminalPanelProps) {
  const localDesktop = isLocalDesktopApp();
  const selectedConversationId = useStore((s) => s.selectedConversationId);
  const draftWorkspacePath = useStore((s) => s.draftWorkspacePath);
  const conversations = useStore((s) => s.conversations);
  const initTerminalState = useStore((s) => s.initTerminalState);
  const updateTerminalState = useStore((s) => s.updateTerminalState);
  const setActiveTerminalSession = useStore((s) => s.setActiveTerminalSession);

  const terminalState = useConversationTerminal(selectedConversationId);
  const [panelWidth, setPanelWidth] = useState(readTerminalWidth);
  const isResizing = useRef(false);

  const conversation = conversations.find(
    (item) => item.conversation_id === selectedConversationId
  );
  const workspacePath =
    conversation?.workspace_path?.trim() || draftWorkspacePath.trim();
  const terminalAvailable =
    localDesktop &&
    agentModeActive &&
    !!selectedConversationId &&
    !!workspacePath;

  useEffect(() => {
    if (!selectedConversationId || !terminalAvailable || terminalState) return;
    initTerminalState(selectedConversationId, { dock: 'right', isOpen: false });
  }, [selectedConversationId, terminalAvailable, initTerminalState, terminalState]);

  const isOpen = terminalAvailable && !!terminalState?.isOpen;
  const sessions = terminalState?.sessions ?? [];
  const activeSessionId = terminalState?.activeSessionId ?? null;
  const maxSessions = terminalState?.maxSessionsPerConversation ?? 5;

  useEffect(() => {
    if (!isOpen || !selectedConversationId || !terminalAvailable) return;
    let cancelled = false;

    const loadSessions = async () => {
      try {
        const listed = await listTerminalSessions(selectedConversationId);
        if (cancelled) return;

        let nextSessions = listed.sessions;
        let activeId = localStorage.getItem(
          `reasoner_terminal_active_session:${selectedConversationId}`,
        );

        if (nextSessions.length === 0) {
          const created = await createTerminalSession(selectedConversationId, {
            workspace_path: workspacePath.trim() || undefined,
            cols: 120,
            rows: 30,
          });
          if (cancelled) return;
          nextSessions = [created];
          activeId = created.session_id;
        }

        const activeSession =
          nextSessions.find((item) => item.session_id === activeId) ?? nextSessions[0];
        const resolvedId = activeSession?.session_id ?? null;

        updateTerminalState(selectedConversationId, {
          sessions: nextSessions,
          activeSessionId: resolvedId,
          session: activeSession ?? null,
          maxSessionsPerConversation: listed.max_sessions_per_conversation,
          buffer: activeSession?.replay_buffer ?? '',
          status: activeSession?.status === 'running' ? 'running' : 'idle',
        });
        if (resolvedId) {
          localStorage.setItem(
            `reasoner_terminal_active_session:${selectedConversationId}`,
            resolvedId,
          );
        }
      } catch {
        if (!cancelled) {
          updateTerminalState(selectedConversationId, { status: 'error' });
        }
      }
    };

    void loadSessions();
    return () => {
      cancelled = true;
    };
  }, [
    isOpen,
    selectedConversationId,
    terminalAvailable,
    updateTerminalState,
    workspacePath,
  ]);

  const handleSelectSession = useCallback(
    (sessionId: string) => {
      if (!selectedConversationId) return;
      setActiveTerminalSession(selectedConversationId, sessionId);
      localStorage.setItem(
        `reasoner_terminal_active_session:${selectedConversationId}`,
        sessionId,
      );
    },
    [selectedConversationId, setActiveTerminalSession],
  );

  const handleSessionsChange = useCallback(
    (nextSessions: TerminalSessionResponse[], nextActiveId: string | null) => {
      if (!selectedConversationId) return;
      const activeSession =
        nextSessions.find((item) => item.session_id === nextActiveId) ?? null;
      updateTerminalState(selectedConversationId, {
        sessions: nextSessions,
        activeSessionId: nextActiveId,
        session: activeSession,
        buffer: activeSession?.replay_buffer ?? '',
        connected: false,
        status: nextActiveId ? 'idle' : 'idle',
      });
      const storageKey = `reasoner_terminal_active_session:${selectedConversationId}`;
      if (nextActiveId) {
        localStorage.setItem(storageKey, nextActiveId);
      } else {
        localStorage.removeItem(storageKey);
      }
    },
    [selectedConversationId, updateTerminalState],
  );

  const handleToggleOpen = useCallback(() => {
    if (!selectedConversationId || !terminalAvailable) return;
    updateTerminalState(selectedConversationId, {
      isOpen: !terminalState?.isOpen,
    });
  }, [selectedConversationId, terminalAvailable, terminalState?.isOpen, updateTerminalState]);

  const handleMouseMove = useCallback((e: MouseEvent) => {
    if (!isResizing.current) return;
    const next = Math.min(
      MAX_WIDTH,
      Math.max(MIN_WIDTH, window.innerWidth - e.clientX)
    );
    setPanelWidth(next);
    localStorage.setItem(TERMINAL_WIDTH_KEY, String(next));
    if (selectedConversationId && terminalState?.isOpen) {
      updateTerminalState(selectedConversationId, { width: next });
    }
  }, [selectedConversationId, terminalState?.isOpen, updateTerminalState]);

  const handleMouseUp = useCallback(() => {
    isResizing.current = false;
    document.removeEventListener('mousemove', handleMouseMove);
    document.removeEventListener('mouseup', handleMouseUp);
  }, [handleMouseMove]);

  const handleMouseDown = useCallback(() => {
    isResizing.current = true;
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
  }, [handleMouseMove, handleMouseUp]);

  if (!localDesktop) {
    return null;
  }

  const folderLabel = workspaceFolderLabel(workspacePath);

  if (!isOpen) {
    return null;
  }

  return (
    <>
      <aside
        className="desktop-shell-right ui-panel relative flex flex-shrink-0 flex-col"
        style={{ width: panelWidth }}
      >
        <DesktopTitlebar className="desktop-terminal-header flex h-[var(--titlebar-height)] items-center justify-between border-b border-white/[0.05] px-3">
          <div className="desktop-titlebar-content min-w-0">
            <div className="pointer-events-none text-[12px] font-medium text-zinc-400">Terminal</div>
            {folderLabel ? (
              <div
                className="pointer-events-none truncate text-[11px] text-zinc-600"
                title={workspacePath}
              >
                {folderLabel}
              </div>
            ) : null}
          </div>
          <Button
            variant="ghost"
            size="icon"
            onClick={handleToggleOpen}
            className="desktop-no-drag relative z-10 h-8 w-8 text-zinc-500"
            aria-label="Collapse terminal"
          >
            <PanelRightClose className="h-4 w-4" />
          </Button>
        </DesktopTitlebar>
        <div className="flex min-h-0 flex-1">
          {selectedConversationId && terminalAvailable && sessions.length > 0 ? (
            <>
              <TerminalSessionRail
                conversationId={selectedConversationId}
                workspacePath={workspacePath}
                sessions={sessions}
                activeSessionId={activeSessionId}
                maxSessions={maxSessions}
                onSelect={handleSelectSession}
                onSessionsChange={handleSessionsChange}
              />
              <div className="min-h-0 min-w-0 flex-1">
                {activeSessionId ? (
                  <IntegratedTerminal
                    key={activeSessionId}
                    conversationId={selectedConversationId}
                    sessionId={activeSessionId}
                    workspacePath={workspacePath}
                    active={terminalAvailable}
                    dock="right"
                    chrome="embedded"
                  />
                ) : null}
              </div>
            </>
          ) : null}
        </div>
        <div
          className="group absolute bottom-0 left-0 top-0 w-1 cursor-col-resize hover:bg-white/10"
          onMouseDown={handleMouseDown}
        >
          <div className="absolute left-0 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100">
            <GripVertical className="h-6 w-6 text-zinc-600" />
          </div>
        </div>
      </aside>
    </>
  );
}

/** Opens terminal from toolbar; exported hook pattern via store is enough */
export function useTerminalPanelToggle() {
  const selectedConversationId = useStore((s) => s.selectedConversationId);
  const updateTerminalState = useStore((s) => s.updateTerminalState);
  const initTerminalState = useStore((s) => s.initTerminalState);
  const terminalState = useConversationTerminal(selectedConversationId);

  return useCallback(() => {
    if (!selectedConversationId) return;
    if (!terminalState) {
      initTerminalState(selectedConversationId, { dock: 'right', isOpen: true });
      return;
    }
    updateTerminalState(selectedConversationId, { isOpen: !terminalState.isOpen });
  }, [selectedConversationId, terminalState, initTerminalState, updateTerminalState]);
}
