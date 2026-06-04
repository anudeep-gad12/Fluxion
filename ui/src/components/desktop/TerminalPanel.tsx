import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { GripVertical, PanelRightClose } from 'lucide-react';
import { toast } from 'sonner';

import { IntegratedTerminal } from '@/components/IntegratedTerminal';
import { BrowserPane } from '@/components/desktop/BrowserPane';
import { DesktopTitlebar } from '@/components/desktop/DesktopTitlebar';
import { TerminalSessionRail, type ToolTab } from '@/components/desktop/TerminalSessionRail';
import {
  ApiError,
  closeDraftTerminalSession,
  closeTerminalSession,
  createDraftTerminalSession,
  createTerminalSession,
  listDraftTerminalSessions,
  listTerminalSessions,
  type TerminalSessionResponse,
} from '@/api/client';
import { DRAFT_TERMINAL_CONVERSATION_ID, useStore, useConversationTerminal, type BrowserTabState } from '@/hooks/useStore';
import { isLocalDesktopApp } from '@/lib/platform';
import { Button } from '@/components/ui/button';

const PANEL_WIDTH_KEY = 'reasoner_tools_panel_width';
const LEGACY_TERMINAL_WIDTH_KEY = 'reasoner_terminal_panel_width';
const DEFAULT_WIDTH = 460;
const MIN_WIDTH = 340;
const MAX_WIDTH = 860;

function maxPanelWidth(): number {
  if (typeof window === 'undefined') return MAX_WIDTH;
  return Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, Math.floor(window.innerWidth * 0.55)));
}

function clampPanelWidth(width: number): number {
  return Math.min(maxPanelWidth(), Math.max(MIN_WIDTH, width));
}

function readPanelWidth(): number {
  if (typeof window === 'undefined') return DEFAULT_WIDTH;
  const stored = Number(
    localStorage.getItem(PANEL_WIDTH_KEY) || localStorage.getItem(LEGACY_TERMINAL_WIDTH_KEY),
  );
  if (!Number.isFinite(stored)) return DEFAULT_WIDTH;
  return clampPanelWidth(stored);
}

function workspaceFolderLabel(workspacePath: string): string {
  const trimmed = workspacePath.trim();
  if (!trimmed) return '';
  return trimmed.split('/').filter(Boolean).pop() || trimmed;
}

function terminalTabId(sessionId: string): string {
  return `terminal:${sessionId}`;
}

function browserTabId(tabId: string): string {
  return `browser:${tabId}`;
}

function sessionLabel(session: TerminalSessionResponse): string {
  if (session.title?.trim()) return session.title.trim();
  const shell = session.shell || '';
  const parts = shell.split('/');
  return parts[parts.length - 1] || 'shell';
}

function browserLabel(tab: BrowserTabState): string {
  if (tab.title?.trim()) return tab.title.trim();
  if (!tab.url) return 'Browser';
  try {
    const parsed = new URL(tab.url);
    return parsed.hostname || 'Browser';
  } catch {
    return 'Browser';
  }
}

function browserTitle(url: string): string {
  if (!url) return 'Browser';
  try {
    const parsed = new URL(url);
    return parsed.hostname || 'Browser';
  } catch {
    return 'Browser';
  }
}

function makeBrowserTab(url = ''): BrowserTabState {
  const id = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  return {
    id,
    webviewLabel: `fluxion-browser-${id}`,
    url,
    title: browserTitle(url),
    status: url ? 'loading' : 'idle',
    error: null,
  };
}

function isToolTabValid(
  tabId: string | null | undefined,
  sessions: TerminalSessionResponse[],
  browserTabs: BrowserTabState[],
): boolean {
  if (!tabId) return false;
  if (tabId.startsWith('terminal:')) {
    const sessionId = tabId.slice('terminal:'.length);
    return sessions.some((session) => session.session_id === sessionId);
  }
  if (tabId.startsWith('browser:')) {
    const id = tabId.slice('browser:'.length);
    return browserTabs.some((tab) => tab.id === id);
  }
  return false;
}

function nextActiveToolId(
  currentActive: string | null | undefined,
  closingId: string,
  previousTabs: ToolTab[],
  nextTabs: ToolTab[],
): string | null {
  if (currentActive && currentActive !== closingId && nextTabs.some((tab) => tab.id === currentActive)) {
    return currentActive;
  }
  if (nextTabs.length === 0) return null;
  const previousIndex = Math.max(0, previousTabs.findIndex((tab) => tab.id === closingId));
  return nextTabs[Math.min(previousIndex, nextTabs.length - 1)]?.id ?? nextTabs[0]?.id ?? null;
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
  const desktopOverlayOpen = useStore((s) => s.desktopOverlayOpen);

  const terminalKey = selectedConversationId || DRAFT_TERMINAL_CONVERSATION_ID;
  const terminalState = useConversationTerminal(terminalKey);
  const [panelWidth, setPanelWidth] = useState(readPanelWidth);
  const [toolMenuOpen, setToolMenuOpen] = useState(false);
  const isResizing = useRef(false);

  const conversation = conversations.find(
    (item) => item.conversation_id === selectedConversationId,
  );
  const workspacePath = conversation?.workspace_path?.trim() || draftWorkspacePath.trim();
  const terminalAvailable = localDesktop && agentModeActive && !!workspacePath;
  const storageScope = selectedConversationId || terminalKey;

  useEffect(() => {
    if (!terminalAvailable || terminalState) return;
    initTerminalState(terminalKey, { dock: 'right', isOpen: false, width: panelWidth });
  }, [terminalKey, terminalAvailable, initTerminalState, terminalState, panelWidth]);

  const isOpen = terminalAvailable && !!terminalState?.isOpen;
  const sessions = terminalState?.sessions ?? [];
  const browserTabs = terminalState?.browserTabs ?? [];
  const activeSessionId = terminalState?.activeSessionId ?? null;
  const maxSessions = terminalState?.maxSessionsPerConversation ?? 10;
  const maxBrowserTabs = terminalState?.maxBrowserTabsPerConversation ?? 10;
  const terminalAtLimit = sessions.length >= maxSessions;
  const browserAtLimit = browserTabs.length >= maxBrowserTabs;

  const tabs = useMemo<ToolTab[]>(() => {
    const stateActive = terminalState?.activeToolTabId ?? null;
    const fallback = activeSessionId ? terminalTabId(activeSessionId) : browserTabs[0] ? browserTabId(browserTabs[0].id) : null;
    const activeToolTabId = isToolTabValid(stateActive, sessions, browserTabs) ? stateActive : fallback;
    return [
      ...sessions.map((session) => ({
        id: terminalTabId(session.session_id),
        kind: 'terminal' as const,
        label: sessionLabel(session),
        active: activeToolTabId === terminalTabId(session.session_id),
        canClose: true,
      })),
      ...browserTabs.map((tab) => ({
        id: browserTabId(tab.id),
        kind: 'browser' as const,
        label: browserLabel(tab),
        active: activeToolTabId === browserTabId(tab.id),
        canClose: true,
      })),
    ];
  }, [activeSessionId, browserTabs, sessions, terminalState?.activeToolTabId]);

  const activeToolTabId = tabs.find((tab) => tab.active)?.id ?? tabs[0]?.id ?? null;
  const activeTerminalSessionId = activeToolTabId?.startsWith('terminal:')
    ? activeToolTabId.slice('terminal:'.length)
    : null;
  const activeKind = activeToolTabId?.startsWith('browser:') ? 'Browser' : 'Terminal';

  useEffect(() => {
    if (!isOpen || !terminalAvailable) return;
    let cancelled = false;

    const loadSessions = async () => {
      try {
        const listed = selectedConversationId
          ? await listTerminalSessions(selectedConversationId)
          : await listDraftTerminalSessions(workspacePath);
        if (cancelled) return;

        const currentState = useStore.getState().terminalByConversation[terminalKey];
        const existingBrowserTabs = currentState?.browserTabs ?? [];
        let nextSessions = listed.sessions;
        let activeId = localStorage.getItem(`reasoner_terminal_active_session:${storageScope}`);

        if (nextSessions.length === 0 && existingBrowserTabs.length === 0) {
          const request = {
            workspace_path: workspacePath.trim() || undefined,
            cols: 120,
            rows: 30,
          };
          const created = selectedConversationId
            ? await createTerminalSession(selectedConversationId, request)
            : await createDraftTerminalSession(request);
          if (cancelled) return;
          nextSessions = [created];
          activeId = created.session_id;
        }

        const activeSession =
          nextSessions.find((item) => item.session_id === activeId) ?? nextSessions[0] ?? null;
        const resolvedId = activeSession?.session_id ?? null;
        const storedTool = localStorage.getItem(`reasoner_tools_active_tab:${storageScope}`);
        const currentTool = currentState?.activeToolTabId;
        const fallbackTool = resolvedId
          ? terminalTabId(resolvedId)
          : existingBrowserTabs[0]
            ? browserTabId(existingBrowserTabs[0].id)
            : null;
        const resolvedTool = isToolTabValid(storedTool, nextSessions, existingBrowserTabs)
          ? storedTool
          : isToolTabValid(currentTool, nextSessions, existingBrowserTabs)
            ? currentTool
            : fallbackTool;

        updateTerminalState(terminalKey, {
          sessions: nextSessions,
          activeSessionId: resolvedId,
          activeToolTabId: resolvedTool,
          session: activeSession,
          maxSessionsPerConversation: listed.max_sessions_per_conversation,
          maxBrowserTabsPerConversation: listed.max_browser_tabs_per_conversation,
          buffer: activeSession?.replay_buffer ?? '',
          status: activeSession?.status === 'running' ? 'running' : 'idle',
          width: panelWidth,
        });
        if (resolvedId) {
          localStorage.setItem(`reasoner_terminal_active_session:${storageScope}`, resolvedId);
        }
        if (resolvedTool) {
          localStorage.setItem(`reasoner_tools_active_tab:${storageScope}`, resolvedTool);
        }
      } catch {
        if (!cancelled) {
          updateTerminalState(terminalKey, { status: 'error' });
        }
      }
    };

    void loadSessions();
    return () => {
      cancelled = true;
    };
  }, [isOpen, selectedConversationId, storageScope, terminalAvailable, terminalKey, updateTerminalState, workspacePath, panelWidth]);

  const persistActiveTool = useCallback((toolId: string | null) => {
    const storageKey = `reasoner_tools_active_tab:${storageScope}`;
    if (toolId) localStorage.setItem(storageKey, toolId);
    else localStorage.removeItem(storageKey);
  }, [storageScope]);

  const handleSelectTool = useCallback((tabId: string) => {
    if (tabId.startsWith('terminal:')) {
      const sessionId = tabId.slice('terminal:'.length);
      setActiveTerminalSession(terminalKey, sessionId);
      localStorage.setItem(`reasoner_terminal_active_session:${storageScope}`, sessionId);
    }
    updateTerminalState(terminalKey, { activeToolTabId: tabId });
    persistActiveTool(tabId);
  }, [persistActiveTool, setActiveTerminalSession, storageScope, terminalKey, updateTerminalState]);

  const handleNewTerminal = useCallback(async () => {
    if (terminalAtLimit) {
      toast.error(`Maximum ${maxSessions} terminals for this conversation`);
      return;
    }
    try {
      const request = {
        workspace_path: workspacePath.trim() || undefined,
        cols: 120,
        rows: 30,
      };
      const created = selectedConversationId
        ? await createTerminalSession(selectedConversationId, request)
        : await createDraftTerminalSession(request);
      const nextSessions = [...sessions, created];
      const nextTool = terminalTabId(created.session_id);
      updateTerminalState(terminalKey, {
        sessions: nextSessions,
        activeSessionId: created.session_id,
        activeToolTabId: nextTool,
        session: created,
        buffer: created.replay_buffer || '',
        status: created.status === 'running' ? 'running' : 'stale',
      });
      localStorage.setItem(`reasoner_terminal_active_session:${storageScope}`, created.session_id);
      persistActiveTool(nextTool);
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        toast.error(`Maximum ${maxSessions} terminals for this conversation`);
        return;
      }
      toast.error('Could not create terminal');
    }
  }, [maxSessions, persistActiveTool, selectedConversationId, sessions, storageScope, terminalAtLimit, terminalKey, updateTerminalState, workspacePath]);

  const handleNewBrowser = useCallback(() => {
    if (browserAtLimit) {
      toast.error(`Maximum ${maxBrowserTabs} browsers for this conversation`);
      return;
    }
    const tab = makeBrowserTab();
    const nextTool = browserTabId(tab.id);
    updateTerminalState(terminalKey, {
      browserTabs: [...browserTabs, tab],
      activeToolTabId: nextTool,
    });
    persistActiveTool(nextTool);
  }, [browserAtLimit, browserTabs, maxBrowserTabs, persistActiveTool, terminalKey, updateTerminalState]);

  const openBrowserUrl = useCallback((url: string, options: { reuseExisting?: boolean } = {}) => {
    const reuseExisting = options.reuseExisting ?? true;
    const current = useStore.getState().terminalByConversation[terminalKey];
    const currentBrowserTabs = current?.browserTabs ?? [];
    const activeTool = current?.activeToolTabId ?? activeToolTabId;
    const activeBrowserId = activeTool?.startsWith('browser:')
      ? activeTool.slice('browser:'.length)
      : null;
    const targetTab = reuseExisting
      ? currentBrowserTabs.find((tab) => tab.id === activeBrowserId)
        ?? currentBrowserTabs.find((tab) => !tab.url)
      : null;

    if (targetTab) {
      const nextTool = browserTabId(targetTab.id);
      updateTerminalState(terminalKey, {
        browserTabs: currentBrowserTabs.map((tab) => (
          tab.id === targetTab.id
            ? { ...tab, url, title: browserTitle(url), status: 'loading', error: null }
            : tab
        )),
        activeToolTabId: nextTool,
      });
      persistActiveTool(nextTool);
      return;
    }

    const maxTabs = current?.maxBrowserTabsPerConversation ?? maxBrowserTabs;
    if (currentBrowserTabs.length >= maxTabs) {
      toast.error(`Maximum ${maxTabs} browsers for this conversation`);
      return;
    }

    const tab = makeBrowserTab(url);
    const nextTool = browserTabId(tab.id);
    updateTerminalState(terminalKey, {
      browserTabs: [...currentBrowserTabs, tab],
      activeToolTabId: nextTool,
    });
    persistActiveTool(nextTool);
  }, [activeToolTabId, maxBrowserTabs, persistActiveTool, terminalKey, updateTerminalState]);

  const handleOpenTerminalUrl = useCallback((url: string) => {
    openBrowserUrl(url, { reuseExisting: true });
  }, [openBrowserUrl]);

  const handleOpenBrowserNewTab = useCallback((url: string) => {
    openBrowserUrl(url, { reuseExisting: false });
  }, [openBrowserUrl]);

  const handleBrowserUpdate = useCallback((tabId: string, updates: Partial<BrowserTabState>) => {
    const current = useStore.getState().terminalByConversation[terminalKey];
    if (!current) return;
    updateTerminalState(terminalKey, {
      browserTabs: current.browserTabs.map((tab) => (
        tab.id === tabId ? { ...tab, ...updates } : tab
      )),
    });
  }, [terminalKey, updateTerminalState]);

  const handleCloseTool = useCallback(async (tabId: string, kind: ToolTab['kind']) => {
    const previousTabs = tabs;

    if (kind === 'browser') {
      const rawId = tabId.slice('browser:'.length);
      const nextBrowserTabs = browserTabs.filter((tab) => tab.id !== rawId);
      const nextTabs = previousTabs.filter((tab) => tab.id !== tabId);
      const nextTool = nextActiveToolId(activeToolTabId, tabId, previousTabs, nextTabs);
      updateTerminalState(terminalKey, {
        browserTabs: nextBrowserTabs,
        activeToolTabId: nextTool,
      });
      persistActiveTool(nextTool);
      return;
    }

    const sessionId = tabId.slice('terminal:'.length);
    try {
      if (selectedConversationId) {
        await closeTerminalSession(selectedConversationId, sessionId);
      } else {
        await closeDraftTerminalSession(sessionId, { workspace_path: workspacePath.trim() || undefined });
      }
      const nextSessions = sessions.filter((item) => item.session_id !== sessionId);
      const nextTabs = previousTabs.filter((tab) => tab.id !== tabId);
      const nextTool = nextActiveToolId(activeToolTabId, tabId, previousTabs, nextTabs);
      const nextActiveTerminalId = nextTool?.startsWith('terminal:')
        ? nextTool.slice('terminal:'.length)
        : activeSessionId === sessionId
          ? (nextSessions[0]?.session_id ?? null)
          : activeSessionId;
      const current = useStore.getState().terminalByConversation[terminalKey];
      const bufferBySessionId = { ...(current?.bufferBySessionId ?? {}) };
      delete bufferBySessionId[sessionId];
      const activeSession = nextActiveTerminalId
        ? nextSessions.find((item) => item.session_id === nextActiveTerminalId) ?? null
        : null;
      updateTerminalState(terminalKey, {
        sessions: nextSessions,
        activeSessionId: nextActiveTerminalId,
        activeToolTabId: nextTool,
        session: activeSession,
        buffer: nextActiveTerminalId ? (bufferBySessionId[nextActiveTerminalId] ?? '') : '',
        bufferBySessionId,
        connected: false,
        status: 'idle',
      });
      if (nextActiveTerminalId) {
        localStorage.setItem(`reasoner_terminal_active_session:${storageScope}`, nextActiveTerminalId);
      } else {
        localStorage.removeItem(`reasoner_terminal_active_session:${storageScope}`);
      }
      persistActiveTool(nextTool);
    } catch {
      toast.error('Could not close terminal');
    }
  }, [activeSessionId, activeToolTabId, browserTabs, persistActiveTool, selectedConversationId, sessions, storageScope, tabs, terminalKey, updateTerminalState, workspacePath]);

  const handleToggleOpen = useCallback(() => {
    if (!terminalAvailable) return;
    updateTerminalState(terminalKey, { isOpen: !terminalState?.isOpen });
  }, [terminalAvailable, terminalKey, terminalState?.isOpen, updateTerminalState]);

  const handleMouseMove = useCallback((e: MouseEvent) => {
    if (!isResizing.current) return;
    const next = clampPanelWidth(window.innerWidth - e.clientX);
    setPanelWidth(next);
    localStorage.setItem(PANEL_WIDTH_KEY, String(next));
    if (terminalState?.isOpen) {
      updateTerminalState(terminalKey, { width: next });
    }
  }, [terminalKey, terminalState?.isOpen, updateTerminalState]);

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

  useEffect(() => {
    const handleResize = () => {
      setPanelWidth((current) => {
        const next = clampPanelWidth(current);
        if (next !== current) localStorage.setItem(PANEL_WIDTH_KEY, String(next));
        return next;
      });
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  if (!localDesktop) return null;

  const folderLabel = workspaceFolderLabel(workspacePath);

  if (!isOpen) return null;

  return (
    <aside
      className="desktop-shell-right ui-panel relative flex flex-shrink-0 flex-col"
      style={{ width: panelWidth }}
    >
      <DesktopTitlebar className="desktop-terminal-header flex h-[var(--titlebar-height)] items-center justify-between border-b border-white/[0.05] px-3">
        <div className="desktop-titlebar-content min-w-0">
          <div className="pointer-events-none text-[12px] font-medium text-zinc-400">{activeKind}</div>
          {folderLabel ? (
            <div className="pointer-events-none truncate text-[11px] text-zinc-600" title={workspacePath}>
              {folderLabel}
            </div>
          ) : null}
        </div>
        <Button
          variant="ghost"
          size="icon"
          onClick={handleToggleOpen}
          className="desktop-no-drag relative z-10 h-8 w-8 text-zinc-500"
          aria-label="Collapse tools panel"
        >
          <PanelRightClose className="h-4 w-4" />
        </Button>
      </DesktopTitlebar>
      <div className="flex min-h-0 flex-1 flex-col">
        {terminalAvailable ? (
          <>
            <TerminalSessionRail
              tabs={tabs}
              terminalAtLimit={terminalAtLimit}
              browserAtLimit={browserAtLimit}
              maxTerminals={maxSessions}
              maxBrowsers={maxBrowserTabs}
              onSelect={handleSelectTool}
              onNewTerminal={() => void handleNewTerminal()}
              onNewBrowser={handleNewBrowser}
              onClose={(tabId, kind) => void handleCloseTool(tabId, kind)}
              menuOpen={toolMenuOpen}
              onMenuOpenChange={setToolMenuOpen}
            />
            <div className="relative min-h-0 min-w-0 flex-1">
              {activeTerminalSessionId ? (
                <IntegratedTerminal
                  key={activeTerminalSessionId}
                  conversationId={terminalKey}
                  sessionId={activeTerminalSessionId}
                  workspacePath={workspacePath}
                  active={terminalAvailable && activeToolTabId === terminalTabId(activeTerminalSessionId)}
                  dock="right"
                  onOpenUrl={handleOpenTerminalUrl}
                  chrome="embedded"
                />
              ) : null}
              {browserTabs.map((tab) => (
                <BrowserPane
                  key={tab.id}
                  conversationId={terminalKey}
                  tab={tab}
                  active={activeToolTabId === browserTabId(tab.id)}
                  obscured={toolMenuOpen || desktopOverlayOpen}
                  onUpdate={handleBrowserUpdate}
                  onOpenNewTab={handleOpenBrowserNewTab}
                />
              ))}
              {tabs.length === 0 ? (
                <div className="flex h-full items-center justify-center px-4 text-center text-[12px] text-zinc-600">
                  Use + to open a terminal or browser.
                </div>
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
  );
}

/** Opens terminal/tools panel from toolbar; exported hook pattern via store is enough */
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
