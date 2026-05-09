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

interface IntegratedTerminalProps {
  conversationId: string;
  workspacePath: string;
  active: boolean;
}

const STATUS_STYLES: Record<string, string> = {
  connecting: 'border-cyan-500/25 bg-cyan-500/[0.10] text-cyan-200',
  running: 'border-emerald-500/22 bg-emerald-500/[0.10] text-emerald-300',
  stale: 'border-amber-500/22 bg-amber-500/[0.10] text-amber-300',
  error: 'border-red-500/22 bg-red-500/[0.10] text-red-300',
  idle: 'border-zinc-800/90 bg-zinc-950/70 text-zinc-400',
  closed: 'border-zinc-800/90 bg-zinc-950/70 text-zinc-400',
};

export function IntegratedTerminal({
  conversationId,
  workspacePath,
  active,
}: IntegratedTerminalProps) {
  const terminalState = useConversationTerminal(conversationId);
  const initTerminalState = useStore((s) => s.initTerminalState);
  const updateTerminalState = useStore((s) => s.updateTerminalState);
  const appendTerminalBuffer = useStore((s) => s.appendTerminalBuffer);
  const clearTerminalBuffer = useStore((s) => s.clearTerminalBuffer);
  const containerRef = useRef<HTMLDivElement>(null);
  const terminalRef = useRef<Terminal | null>(null);
  const fitAddonRef = useRef<FitAddon | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const resizeObserverRef = useRef<ResizeObserver | null>(null);
  const dragStartRef = useRef<{ y: number; height: number } | null>(null);
  const bufferRef = useRef('');
  const [isRestarting, setIsRestarting] = useState(false);

  useEffect(() => {
    initTerminalState(conversationId, {
      isOpen: localStorage.getItem(`reasoner_terminal_open:${conversationId}`) === 'true',
      height: Number(localStorage.getItem('reasoner_terminal_height') || '260'),
    });
  }, [conversationId, initTerminalState]);

  useEffect(() => {
    if (!terminalState) return;
    localStorage.setItem(`reasoner_terminal_open:${conversationId}`, String(terminalState.isOpen));
    localStorage.setItem('reasoner_terminal_height', String(terminalState.height));
  }, [conversationId, terminalState?.height, terminalState?.isOpen]);

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
    const ws = createTerminalWebSocket(conversationId, sessionId);
    socketRef.current = ws;
    ws.onopen = () => {
      updateTerminalState(conversationId, { connected: true, status: 'running' });
      const term = terminalRef.current;
      if (term) {
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
    const term = new Terminal({
      cursorBlink: true,
      convertEol: false,
      fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
      fontSize: 12,
      theme: {
        background: '#09090b',
        foreground: '#e4e4e7',
        cursor: '#fafafa',
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
    ensureTerminal()
      .then((session) => {
        if (session?.session_id) {
          connectSocket(session.session_id);
        }
      })
      .catch(() => updateTerminalState(conversationId, { status: 'error' }));

    return () => {
      resizeObserverRef.current?.disconnect();
      resizeObserverRef.current = null;
      disposable.dispose();
      socketRef.current?.close();
      socketRef.current = null;
      term.dispose();
      terminalRef.current = null;
      fitAddonRef.current = null;
    };
  }, [active, connectSocket, conversationId, ensureTerminal, terminalState?.isOpen, updateTerminalState]);

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

  const handleMouseDown = useCallback((event: ReactMouseEvent<HTMLDivElement>) => {
    if (!terminalState) return;
    dragStartRef.current = { y: event.clientY, height: terminalState.height };
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

  const workspaceMismatch = useMemo(() => {
    const activeWorkspace = workspacePath.trim();
    if (!activeWorkspace || !terminalState?.session?.workspace_path) return false;
    return terminalState.session.workspace_path !== activeWorkspace;
  }, [terminalState?.session?.workspace_path, workspacePath]);

  if (!terminalState?.isOpen || !active) {
    return null;
  }

  const statusClassName = STATUS_STYLES[terminalState.status] || STATUS_STYLES.idle;

  return (
    <div
      className="flex flex-shrink-0 flex-col border-t border-zinc-800/90 bg-black/96"
      style={{ height: terminalState.height }}
    >
      <div
        className="ui-transition h-2 cursor-row-resize bg-zinc-950 hover:bg-zinc-900"
        onMouseDown={handleMouseDown}
      />
      <div className="border-b border-zinc-800/85 bg-zinc-950/88 px-3.5 py-3 font-mono text-xs">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0 space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-full border border-zinc-800/90 bg-zinc-900/85 px-2.5 py-1 text-[10px] uppercase tracking-[0.18em] text-zinc-300">
                terminal
              </span>
              <span className={cn('rounded-full px-2.5 py-1 text-[10px] uppercase tracking-[0.18em]', statusClassName)}>
                {terminalState.status}
              </span>
            </div>
            <div className="truncate text-[11px] text-zinc-500">
              {terminalState.session?.workspace_path || workspacePath || '~'}
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleClear}
              className="premium-subtle-button px-3 py-1"
              type="button"
            >
              clear
            </button>
            <button
              onClick={handleRestart}
              className="premium-subtle-button px-3 py-1"
              type="button"
              disabled={isRestarting}
            >
              {isRestarting ? 'restarting...' : 'restart'}
            </button>
            <button
              onClick={() => updateTerminalState(conversationId, { isOpen: false })}
              className="premium-subtle-button px-3 py-1"
              type="button"
            >
              collapse
            </button>
          </div>
        </div>

        {workspaceMismatch && (
          <div className="mt-3 rounded-[0.95rem] border border-amber-500/22 bg-amber-500/[0.08] px-3 py-2 text-[11px] leading-5 text-amber-200/85">
            Workspace changed. Restart the terminal to attach it to the new path.
          </div>
        )}
      </div>
      <div className="min-h-0 flex-1 bg-black">
        <div
          ref={containerRef}
          className="h-full w-full px-3 py-2"
          onClick={() => terminalRef.current?.focus()}
        />
      </div>
    </div>
  );
}
