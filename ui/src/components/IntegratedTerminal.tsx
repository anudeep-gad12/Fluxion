import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { MouseEvent as ReactMouseEvent } from 'react';
import { Terminal } from 'xterm';
import { FitAddon } from '@xterm/addon-fit';
import 'xterm/css/xterm.css';

import {
  createTerminalSession,
  createTerminalWebSocket,
  restartTerminalSession,
} from '@/api/client';
import { useConversationTerminal, useStore } from '@/hooks/useStore';
import { cn } from '@/lib/utils';

const MIN_HEIGHT = 160;
const MAX_HEIGHT = 520;
const MIN_WIDTH = 320;
const MAX_WIDTH = 760;

type TerminalDock = 'bottom' | 'right';

type TerminalStatus = 'idle' | 'connecting' | 'running' | 'closed' | 'stale' | 'error';

interface IntegratedTerminalProps {
  conversationId: string;
  workspacePath: string;
  active: boolean;
  dock: TerminalDock;
  /** When embedded, outer panel supplies header/resize/close chrome */
  chrome?: 'full' | 'embedded';
}

const STATUS_DOT_STYLES: Record<TerminalStatus, string> = {
  connecting: 'bg-cyan-300',
  running: 'bg-emerald-300',
  stale: 'bg-amber-300',
  error: 'bg-red-300',
  idle: 'bg-zinc-600',
  closed: 'bg-zinc-600',
};

function normalizeStatus(status: string | undefined): TerminalStatus {
  if (status === 'connecting' || status === 'running' || status === 'stale' || status === 'error' || status === 'closed') {
    return status;
  }
  return 'idle';
}

export function IntegratedTerminal({
  conversationId,
  workspacePath,
  active,
  dock,
  chrome = 'full',
}: IntegratedTerminalProps) {
  const terminalState = useConversationTerminal(conversationId);
  const updateTerminalState = useStore((s) => s.updateTerminalState);
  const appendTerminalBuffer = useStore((s) => s.appendTerminalBuffer);
  const clearTerminalBuffer = useStore((s) => s.clearTerminalBuffer);
  const containerRef = useRef<HTMLDivElement>(null);
  const terminalRef = useRef<Terminal | null>(null);
  const fitAddonRef = useRef<FitAddon | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const socketGenerationRef = useRef(0);
  const resizeObserverRef = useRef<ResizeObserver | null>(null);
  const dragStartRef = useRef<{ x: number; y: number; width: number; height: number } | null>(null);
  const bufferRef = useRef('');
  const lastSocketStatusRef = useRef<TerminalStatus>('idle');
  const [isRestarting, setIsRestarting] = useState(false);

  useEffect(() => {
    bufferRef.current = terminalState?.buffer || '';
  }, [terminalState?.buffer]);

  const replaceTerminalBuffer = useCallback((nextBuffer: string) => {
    updateTerminalState(conversationId, { buffer: nextBuffer.slice(-120000) });
  }, [conversationId, updateTerminalState]);

  const ensureTerminal = useCallback(async () => {
    if (!containerRef.current || !terminalState?.isOpen || !active) {
      return null;
    }
    updateTerminalState(conversationId, { status: 'connecting' });
    const term = terminalRef.current;
    const cols = term?.cols || 120;
    const rows = term?.rows || 30;
    const session = await createTerminalSession(conversationId, {
      workspace_path: workspacePath.trim() || undefined,
      cols,
      rows,
    });
    updateTerminalState(conversationId, {
      session,
      status: session.status === 'running' ? 'running' : 'stale',
      buffer: session.replay_buffer || '',
    });
    fitAddonRef.current?.fit();
    return session;
  }, [active, conversationId, terminalState?.isOpen, updateTerminalState, workspacePath]);

  const connectSocket = useCallback((sessionId: string) => {
    if (!active || !terminalState?.isOpen) {
      return;
    }

    const generation = socketGenerationRef.current + 1;
    socketGenerationRef.current = generation;
    socketRef.current?.close();
    lastSocketStatusRef.current = 'connecting';

    const ws = createTerminalWebSocket(conversationId, sessionId);
    socketRef.current = ws;

    const isCurrentSocket = () => socketRef.current === ws && socketGenerationRef.current === generation;

    ws.onopen = () => {
      if (!isCurrentSocket()) return;
      lastSocketStatusRef.current = 'running';
      updateTerminalState(conversationId, { connected: true, status: 'running' });
      const term = terminalRef.current;
      if (term) {
        term.focus();
        ws.send(JSON.stringify({ type: 'resize', cols: term.cols, rows: term.rows }));
      }
    };

    ws.onmessage = (event) => {
      if (!isCurrentSocket()) return;
      let payload: { type: string; data?: string; status?: string };
      try {
        payload = JSON.parse(event.data) as { type: string; data?: string; status?: string };
      } catch {
        updateTerminalState(conversationId, { connected: false, status: 'error' });
        return;
      }

      if (payload.type === 'output' && payload.data) {
        terminalRef.current?.write(payload.data);
        appendTerminalBuffer(conversationId, payload.data);
      } else if (payload.type === 'replay') {
        const replay = payload.data || '';
        terminalRef.current?.clear();
        if (replay) {
          terminalRef.current?.write(replay);
        }
        replaceTerminalBuffer(replay);
      } else if (payload.type === 'status') {
        const nextStatus = normalizeStatus(payload.status);
        lastSocketStatusRef.current = nextStatus;
        updateTerminalState(conversationId, {
          connected: nextStatus === 'running',
          status: nextStatus,
        });
      } else if (payload.type === 'exit') {
        lastSocketStatusRef.current = 'closed';
        updateTerminalState(conversationId, { connected: false, status: 'closed' });
      }
    };

    ws.onclose = () => {
      if (!isCurrentSocket()) return;
      socketRef.current = null;
      const lastStatus = lastSocketStatusRef.current;
      updateTerminalState(conversationId, {
        connected: false,
        status: lastStatus === 'stale' || lastStatus === 'closed' ? lastStatus : 'error',
      });
    };

    ws.onerror = () => {
      if (!isCurrentSocket()) return;
      lastSocketStatusRef.current = 'error';
      updateTerminalState(conversationId, { connected: false, status: 'error' });
    };
  }, [
    active,
    appendTerminalBuffer,
    conversationId,
    replaceTerminalBuffer,
    terminalState?.isOpen,
    updateTerminalState,
  ]);

  useEffect(() => {
    if (!containerRef.current || !terminalState?.isOpen || !active) {
      return;
    }
    let cancelled = false;
    const term = new Terminal({
      cursorBlink: true,
      convertEol: false,
      fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
      fontSize: 12,
      theme: {
        background: '#0c0c0e',
        foreground: '#e4e4e7',
        cursor: '#f5f7fb',
      },
      scrollback: 5000,
    });
    const fitAddon = new FitAddon();
    term.loadAddon(fitAddon);
    term.open(containerRef.current);
    fitAddon.fit();
    term.focus();
    terminalRef.current = term;
    fitAddonRef.current = fitAddon;
    if (bufferRef.current) {
      term.write(bufferRef.current);
    }
    const disposable = term.onData((data) => {
      const socket = socketRef.current;
      if (socket?.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: 'input', data }));
      }
    });
    resizeObserverRef.current = new ResizeObserver(() => {
      if (!fitAddonRef.current || !terminalRef.current) return;
      fitAddonRef.current.fit();
      const socket = socketRef.current;
      if (socket?.readyState === WebSocket.OPEN) {
        socket.send(
          JSON.stringify({
            type: 'resize',
            cols: terminalRef.current.cols,
            rows: terminalRef.current.rows,
          })
        );
      }
    });
    resizeObserverRef.current.observe(containerRef.current);
    requestAnimationFrame(() => {
      fitAddon.fit();
      term.focus();
    });
    const delayedFit = window.setTimeout(() => {
      if (cancelled) return;
      fitAddon.fit();
      term.focus();
      const socket = socketRef.current;
      if (socket?.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: 'resize', cols: term.cols, rows: term.rows }));
      }
    }, 80);
    ensureTerminal()
      .then((session) => {
        if (cancelled) return;
        if (session?.session_id) {
          connectSocket(session.session_id);
        }
      })
      .catch(() => {
        if (!cancelled) {
          updateTerminalState(conversationId, { connected: false, status: 'error' });
        }
      });

    return () => {
      cancelled = true;
      resizeObserverRef.current?.disconnect();
      resizeObserverRef.current = null;
      window.clearTimeout(delayedFit);
      disposable.dispose();
      socketGenerationRef.current += 1;
      socketRef.current?.close();
      socketRef.current = null;
      term.dispose();
      terminalRef.current = null;
      fitAddonRef.current = null;
    };
  }, [active, connectSocket, conversationId, ensureTerminal, terminalState?.isOpen, updateTerminalState]);

  useEffect(() => {
    if (!terminalState?.isOpen || !active) {
      return;
    }

    const syncLayout = () => {
      const fitAddon = fitAddonRef.current;
      const term = terminalRef.current;
      if (!fitAddon || !term) return;
      fitAddon.fit();
      const socket = socketRef.current;
      if (socket?.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: 'resize', cols: term.cols, rows: term.rows }));
      }
    };

    const raf = requestAnimationFrame(() => {
      syncLayout();
      requestAnimationFrame(syncLayout);
    });

    return () => cancelAnimationFrame(raf);
  }, [active, dock, terminalState?.height, terminalState?.isOpen, terminalState?.width]);

  const handleReconnect = useCallback(() => {
    const sessionId = terminalState?.session?.session_id;
    if (!sessionId) return;
    updateTerminalState(conversationId, { status: 'connecting' });
    connectSocket(sessionId);
  }, [connectSocket, conversationId, terminalState?.session?.session_id, updateTerminalState]);

  const handleRestart = useCallback(async () => {
    if (!terminalState) return;
    setIsRestarting(true);
    try {
      socketGenerationRef.current += 1;
      socketRef.current?.close();
      socketRef.current = null;
      terminalRef.current?.clear();
      clearTerminalBuffer(conversationId);
      const term = terminalRef.current;
      const nextSession = await restartTerminalSession(conversationId, {
        workspace_path: workspacePath.trim() || undefined,
        cols: term?.cols || 120,
        rows: term?.rows || 30,
      });
      updateTerminalState(conversationId, {
        session: nextSession,
        buffer: nextSession.replay_buffer || '',
        status: nextSession.status === 'running' ? 'running' : 'stale',
      });
      connectSocket(nextSession.session_id);
    } finally {
      setIsRestarting(false);
    }
  }, [clearTerminalBuffer, connectSocket, conversationId, terminalState, updateTerminalState, workspacePath]);

  const handleClear = useCallback(() => {
    clearTerminalBuffer(conversationId);
    terminalRef.current?.clear();
  }, [clearTerminalBuffer, conversationId]);

  const handleVerticalResize = useCallback((event: ReactMouseEvent<HTMLDivElement>) => {
    if (!terminalState) return;
    dragStartRef.current = {
      x: event.clientX,
      y: event.clientY,
      width: terminalState.width,
      height: terminalState.height,
    };
    const onMove = (moveEvent: MouseEvent) => {
      if (!dragStartRef.current) return;
      const nextHeight = Math.min(
        MAX_HEIGHT,
        Math.max(MIN_HEIGHT, dragStartRef.current.height - (moveEvent.clientY - dragStartRef.current.y))
      );
      updateTerminalState(conversationId, { height: nextHeight });
      requestAnimationFrame(() => fitAddonRef.current?.fit());
    };
    const onUp = () => {
      dragStartRef.current = null;
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  }, [conversationId, terminalState, updateTerminalState]);

  const handleHorizontalResize = useCallback((event: ReactMouseEvent<HTMLDivElement>) => {
    if (!terminalState) return;
    dragStartRef.current = {
      x: event.clientX,
      y: event.clientY,
      width: terminalState.width,
      height: terminalState.height,
    };
    const onMove = (moveEvent: MouseEvent) => {
      if (!dragStartRef.current) return;
      const maxWidth = typeof window === 'undefined'
        ? MAX_WIDTH
        : Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, Math.floor(window.innerWidth * 0.58)));
      const nextWidth = Math.min(
        maxWidth,
        Math.max(MIN_WIDTH, dragStartRef.current.width - (moveEvent.clientX - dragStartRef.current.x))
      );
      updateTerminalState(conversationId, { width: nextWidth });
      requestAnimationFrame(() => fitAddonRef.current?.fit());
    };
    const onUp = () => {
      dragStartRef.current = null;
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  }, [conversationId, terminalState, updateTerminalState]);

  const workspaceMismatch = useMemo(() => {
    const activeWorkspace = workspacePath.trim();
    if (!activeWorkspace || !terminalState?.session?.workspace_path) return false;
    return terminalState.session.workspace_path !== activeWorkspace;
  }, [terminalState?.session?.workspace_path, workspacePath]);

  if (!terminalState?.isOpen || !active) {
    return null;
  }

  const status = normalizeStatus(terminalState.status);
  const isRightDock = dock === 'right';
  const isEmbedded = chrome === 'embedded';
  const pathLabel = terminalState.session?.workspace_path || workspacePath || '~';
  const canReconnect = !!terminalState.session?.session_id && (status === 'error' || status === 'stale' || status === 'closed');
  const handleDockToggle = (nextDock: TerminalDock) => {
    updateTerminalState(conversationId, { dock: nextDock });
    requestAnimationFrame(() => fitAddonRef.current?.fit());
  };

  return (
    <div
      className={cn(
        'flex min-h-0 flex-shrink-0 overflow-hidden bg-[#0c0c0e]',
        isEmbedded
          ? 'h-full w-full'
          : isRightDock
            ? 'h-full border-l border-white/[0.08]'
            : 'flex-col border-t border-white/[0.08]'
      )}
      style={
        isEmbedded
          ? undefined
          : isRightDock
            ? { width: terminalState.width }
            : { height: terminalState.height }
      }
    >
      {!isEmbedded && isRightDock && (
        <div
          className="ui-transition relative h-full w-2 cursor-col-resize bg-white/[0.025] hover:bg-white/[0.06]"
          onMouseDown={handleHorizontalResize}
        />
      )}
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        {!isEmbedded && !isRightDock && (
          <div
            className="ui-transition h-1.5 cursor-row-resize bg-white/[0.025] hover:bg-white/[0.06]"
            onMouseDown={handleVerticalResize}
          />
        )}
        <div
          className={cn(
            'flex items-center justify-between gap-3 border-b border-white/[0.06] px-3 text-[12px] text-zinc-500',
            isEmbedded ? 'h-8' : 'h-9'
          )}
        >
          <div className="flex min-w-0 items-center gap-2">
            <span className={cn('h-1.5 w-1.5 rounded-full', STATUS_DOT_STYLES[status])} />
            <span className={cn(status === 'error' && 'text-red-300', status === 'stale' && 'text-amber-300')}>
              {workspaceMismatch ? 'workspace changed' : status}
            </span>
            {!isEmbedded ? (
              <>
                <span className="text-zinc-700">·</span>
                <span className="truncate" title={pathLabel}>{pathLabel}</span>
              </>
            ) : null}
          </div>

          <div className="flex shrink-0 items-center gap-2">
            {!isEmbedded ? (
              <>
                <button
                  onClick={() => handleDockToggle('bottom')}
                  className={cn('ui-transition', terminalState.dock === 'bottom' ? 'text-cyan-100' : 'text-zinc-500 hover:text-zinc-200')}
                  type="button"
                >
                  bottom
                </button>
                <button
                  onClick={() => handleDockToggle('right')}
                  className={cn('ui-transition', terminalState.dock === 'right' ? 'text-cyan-100' : 'text-zinc-500 hover:text-zinc-200')}
                  type="button"
                >
                  right
                </button>
                <span className="text-zinc-800">|</span>
              </>
            ) : null}
            <button onClick={handleClear} className="ui-transition hover:text-zinc-200" type="button">
              clear
            </button>
            {canReconnect && (
              <button onClick={handleReconnect} className="ui-transition text-amber-300/85 hover:text-amber-200" type="button">
                reconnect
              </button>
            )}
            <button
              onClick={handleRestart}
              className="ui-transition hover:text-zinc-200 disabled:cursor-wait disabled:text-zinc-700"
              type="button"
              disabled={isRestarting}
            >
              {isRestarting ? 'restarting...' : 'restart'}
            </button>
            {!isEmbedded ? (
              <button
                onClick={() => updateTerminalState(conversationId, { isOpen: false })}
                className="ui-transition hover:text-zinc-200"
                type="button"
              >
                close
              </button>
            ) : null}
          </div>
        </div>
        <div className="min-h-0 min-w-0 flex-1 bg-[#0c0c0e]">
          <div
            ref={containerRef}
            className="h-full min-w-0 w-full px-3 py-2"
            onClick={() => terminalRef.current?.focus()}
          />
        </div>
      </div>
    </div>
  );
}
