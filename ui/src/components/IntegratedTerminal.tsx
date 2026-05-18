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

interface IntegratedTerminalProps {
  conversationId: string;
  workspacePath: string;
  active: boolean;
  dock: TerminalDock;
}

const STATUS_STYLES: Record<string, string> = {
  connecting: 'border-cyan-500/22 bg-cyan-500/[0.08] text-cyan-200',
  running: 'border-emerald-500/20 bg-emerald-500/[0.08] text-emerald-300',
  stale: 'border-amber-500/20 bg-amber-500/[0.08] text-amber-300',
  error: 'border-red-500/20 bg-red-500/[0.08] text-red-300',
  idle: 'border-white/10 bg-white/[0.035] text-zinc-400',
  closed: 'border-white/10 bg-white/[0.035] text-zinc-400',
};

export function IntegratedTerminal({
  conversationId,
  workspacePath,
  active,
  dock,
}: IntegratedTerminalProps) {
  const terminalState = useConversationTerminal(conversationId);
  const updateTerminalState = useStore((s) => s.updateTerminalState);
  const appendTerminalBuffer = useStore((s) => s.appendTerminalBuffer);
  const clearTerminalBuffer = useStore((s) => s.clearTerminalBuffer);
  const containerRef = useRef<HTMLDivElement>(null);
  const terminalRef = useRef<Terminal | null>(null);
  const fitAddonRef = useRef<FitAddon | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const resizeObserverRef = useRef<ResizeObserver | null>(null);
  const dragStartRef = useRef<{ x: number; y: number; width: number; height: number } | null>(null);
  const bufferRef = useRef('');
  const [isRestarting, setIsRestarting] = useState(false);

  useEffect(() => {
    bufferRef.current = terminalState?.buffer || '';
  }, [terminalState?.buffer]);

  const ensureTerminal = useCallback(async () => {
    if (!containerRef.current || !terminalState?.isOpen || !active) {
      return null;
    }
    updateTerminalState(conversationId, { status: 'connecting' });
    const fitAddon = fitAddonRef.current;
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
    if (term) {
      term.clear();
      if (session.replay_buffer) {
        term.write(session.replay_buffer);
      }
    }
    if (fitAddon) {
      fitAddon.fit();
    }
    return session;
  }, [active, conversationId, terminalState?.isOpen, updateTerminalState, workspacePath]);

  const connectSocket = useCallback((sessionId: string) => {
    if (!active || !terminalState?.isOpen) {
      return;
    }
    socketRef.current?.close();
    const ws = createTerminalWebSocket(conversationId, sessionId);
    socketRef.current = ws;
    ws.onopen = () => {
      updateTerminalState(conversationId, { connected: true, status: 'running' });
      const term = terminalRef.current;
      if (term) {
        term.focus();
        ws.send(JSON.stringify({ type: 'resize', cols: term.cols, rows: term.rows }));
      }
    };
    ws.onmessage = (event) => {
      const payload = JSON.parse(event.data) as {
        type: string;
        data?: string;
        status?: string;
      };
      if (payload.type === 'output' && payload.data) {
        terminalRef.current?.write(payload.data);
        appendTerminalBuffer(conversationId, payload.data);
      } else if (payload.type === 'status') {
        updateTerminalState(conversationId, {
          status: payload.status === 'stale' ? 'stale' : 'running',
        });
      } else if (payload.type === 'exit') {
        updateTerminalState(conversationId, { connected: false, status: 'closed' });
      }
    };
    ws.onclose = () => {
      socketRef.current = null;
      updateTerminalState(conversationId, {
        connected: false,
        status: 'closed',
      });
    };
    ws.onerror = () => {
      updateTerminalState(conversationId, { connected: false, status: 'error' });
    };
  }, [
    active,
    appendTerminalBuffer,
    conversationId,
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
        background: '#07080a',
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
      if (socketRef.current?.readyState === WebSocket.OPEN) {
        socketRef.current.send(JSON.stringify({ type: 'input', data }));
      }
    });
    resizeObserverRef.current = new ResizeObserver(() => {
      if (!fitAddonRef.current || !terminalRef.current) return;
      fitAddonRef.current.fit();
      if (socketRef.current?.readyState === WebSocket.OPEN) {
        socketRef.current.send(
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
      if (cancelled) {
        return;
      }
      fitAddon.fit();
      term.focus();
      if (socketRef.current?.readyState === WebSocket.OPEN) {
        socketRef.current.send(
          JSON.stringify({
            type: 'resize',
            cols: term.cols,
            rows: term.rows,
          })
        );
      }
    }, 80);
    ensureTerminal()
      .then((session) => {
        if (cancelled) {
          return;
        }
        if (session?.session_id) {
          connectSocket(session.session_id);
        }
      })
      .catch(() => {
        if (!cancelled) {
          updateTerminalState(conversationId, { status: 'error' });
        }
      });

    return () => {
      cancelled = true;
      resizeObserverRef.current?.disconnect();
      resizeObserverRef.current = null;
      window.clearTimeout(delayedFit);
      disposable.dispose();
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
      if (!fitAddon || !term) {
        return;
      }
      fitAddon.fit();
      if (socketRef.current?.readyState === WebSocket.OPEN) {
        socketRef.current.send(
          JSON.stringify({
            type: 'resize',
            cols: term.cols,
            rows: term.rows,
          })
        );
      }
    };

    const raf = requestAnimationFrame(() => {
      syncLayout();
      requestAnimationFrame(syncLayout);
    });

    return () => cancelAnimationFrame(raf);
  }, [active, dock, terminalState?.height, terminalState?.isOpen, terminalState?.width]);

  const handleRestart = useCallback(async () => {
    if (!terminalState) return;
    setIsRestarting(true);
    try {
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
      if (nextSession.replay_buffer) {
        terminalRef.current?.write(nextSession.replay_buffer);
      }
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

  const statusClassName = STATUS_STYLES[terminalState.status] || STATUS_STYLES.idle;
  const isRightDock = dock === 'right';
  const handleDockToggle = (nextDock: TerminalDock) => {
    updateTerminalState(conversationId, { dock: nextDock });
    requestAnimationFrame(() => fitAddonRef.current?.fit());
  };

  return (
    <div
      className={cn(
        'fluxion-card-strong flex min-h-0 flex-shrink-0 overflow-hidden bg-black/96',
        isRightDock ? 'h-full border-l border-white/10' : 'flex-col border-t border-white/10'
      )}
      style={isRightDock ? { width: terminalState.width } : { height: terminalState.height }}
    >
      {isRightDock && (
        <div
          className="ui-transition relative h-full w-3 cursor-col-resize border-r border-white/10 bg-black/35 hover:bg-white/[0.055]"
          onMouseDown={handleHorizontalResize}
        >
          <span className="absolute left-1/2 top-1/2 h-16 w-px -translate-x-1/2 -translate-y-1/2 bg-zinc-700/80" />
        </div>
      )}
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        {!isRightDock && (
          <div
            className="ui-transition h-2 cursor-row-resize bg-black/35 hover:bg-white/[0.055]"
            onMouseDown={handleVerticalResize}
          />
        )}
        <div className="border-b border-white/10 bg-black/30 px-3 py-2.5 font-mono text-xs">
          <div className="flex flex-col gap-2">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0 flex-1 space-y-1.5">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded-full border border-white/10 bg-white/[0.035] px-2 py-0.5 text-[10px] uppercase tracking-[0.16em] text-zinc-300">
                    terminal
                  </span>
                  <span className={cn('rounded-full px-2 py-0.5 text-[10px] uppercase tracking-[0.16em]', statusClassName)}>
                    {terminalState.status}
                  </span>
                  <div className="flex overflow-hidden rounded-full border border-white/10 bg-white/[0.025]">
                    <button
                      onClick={() => handleDockToggle('bottom')}
                      className={cn(
                        'ui-transition px-2 py-0.5 text-[10px] uppercase tracking-[0.16em]',
                        terminalState.dock === 'bottom'
                          ? 'bg-cyan-300/[0.08] text-cyan-100'
                          : 'text-zinc-500 hover:text-zinc-200'
                      )}
                      type="button"
                    >
                      bottom
                    </button>
                    <button
                      onClick={() => handleDockToggle('right')}
                      className={cn(
                        'ui-transition border-l border-white/10 px-2 py-0.5 text-[10px] uppercase tracking-[0.16em]',
                        terminalState.dock === 'right'
                          ? 'bg-cyan-300/[0.08] text-cyan-100'
                          : 'text-zinc-500 hover:text-zinc-200'
                      )}
                      type="button"
                    >
                      right
                    </button>
                  </div>
                </div>
              </div>

              <div className="flex shrink-0 items-center gap-1.5">
                <button
                  onClick={handleClear}
                  className="premium-subtle-button px-2.5 py-1"
                  type="button"
                >
                  clear
                </button>
                <button
                  onClick={handleRestart}
                  className="premium-subtle-button px-2.5 py-1"
                  type="button"
                  disabled={isRestarting}
                >
                  {isRestarting ? 'restarting...' : 'restart'}
                </button>
                <button
                  onClick={() => updateTerminalState(conversationId, { isOpen: false })}
                  className="premium-subtle-button px-2.5 py-1"
                  type="button"
                >
                  collapse
                </button>
              </div>
            </div>
            <div className="truncate text-[11px] text-zinc-500">
              {terminalState.session?.workspace_path || workspacePath || '~'}
            </div>
          </div>

          {workspaceMismatch && (
            <div className="mt-2 rounded-[0.8rem] border border-amber-500/20 bg-amber-500/[0.06] px-3 py-2 text-[11px] leading-5 text-amber-200/85">
              Workspace changed. Restart the terminal to attach it to the new path.
            </div>
          )}
        </div>
        <div className="min-h-0 min-w-0 flex-1 bg-[#07080a]">
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
