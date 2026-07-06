// Main application component with collapsible sidebar

import { useState, useRef, useCallback, useEffect, type MouseEvent as ReactMouseEvent } from 'react';
import { Routes, Route, Navigate, useParams, useNavigate } from 'react-router-dom';
import { Toaster } from 'sonner';
import { ConversationList } from '@/components/ConversationList';
import { ConversationView, isConversationMissing } from '@/components/ConversationView';
import { TerminalPanel } from '@/components/desktop/TerminalPanel';
import { DesktopTitlebar } from '@/components/desktop/DesktopTitlebar';
import { DesktopSidebarBrand } from '@/components/desktop/DesktopSidebarBrand';
import { FloatingOverlay } from '@/components/desktop/FloatingOverlay';
import { startWindowDrag } from '@/lib/windowDrag';
import { useStore } from '@/hooks/useStore';
import { getApiBase } from '@/api/client';
import { openNativeWorkspacePicker } from '@/lib/platform';
import { cn } from '@/lib/utils';
import { PanelLeftClose, PanelLeft, GripVertical, FolderPlus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ThemeToggle } from '@/components/ThemeToggle';
import { CommandPalette } from '@/components/CommandPalette';
import { useTheme } from '@/hooks/useTheme';

const SIDEBAR_PREF_KEY = 'reasoner_sidebar_pref';
const DESKTOP_SIDEBAR_DEFAULT = 272;
const DESKTOP_SIDEBAR_MIN = 240;
const DESKTOP_SIDEBAR_MAX = 360;

function ConversationSync() {
  const { conversationId } = useParams<{ conversationId: string }>();
  const navigate = useNavigate();
  const selectedConversationId = useStore((s) => s.selectedConversationId);
  const routeSyncSuppressedConversationId = useStore((s) => s.routeSyncSuppressedConversationId);
  const selectConversation = useStore((s) => s.selectConversation);
  const clearRouteSyncSuppression = useStore((s) => s.clearRouteSyncSuppression);

  useEffect(() => {
    if (!conversationId) {
      if (routeSyncSuppressedConversationId) {
        clearRouteSyncSuppression();
      }
      if (selectedConversationId) {
        selectConversation(null);
      }
      return;
    }
    if (conversationId === routeSyncSuppressedConversationId) {
      navigate('/conversations', { replace: true });
      return;
    }
    if (conversationId && isConversationMissing(conversationId)) {
      if (selectedConversationId) {
        selectConversation(null);
      }
      navigate('/conversations', { replace: true });
      return;
    }
    if (conversationId !== selectedConversationId) {
      selectConversation(conversationId);
    }
  }, [
    clearRouteSyncSuppression,
    conversationId,
    navigate,
    routeSyncSuppressedConversationId,
    selectedConversationId,
    selectConversation,
  ]);

  return <ConversationView />;
}

function NewConversationView() {
  const selectConversation = useStore((s) => s.selectConversation);

  useEffect(() => {
    selectConversation(null);
  }, [selectConversation]);

  return <ConversationView />;
}


function DesktopWindowDragFrame() {
  const handleMouseDown = useCallback((event: ReactMouseEvent<HTMLDivElement>) => {
    void startWindowDrag(event);
  }, []);

  return (
    <div className="desktop-window-drag-frame" aria-hidden>
      <div className="desktop-window-drag-strip desktop-window-drag-strip-top" data-tauri-drag-region onMouseDown={handleMouseDown} />
      <div className="desktop-window-drag-strip desktop-window-drag-strip-left" data-tauri-drag-region onMouseDown={handleMouseDown} />
      <div className="desktop-window-drag-strip desktop-window-drag-strip-right" data-tauri-drag-region onMouseDown={handleMouseDown} />
      <div className="desktop-window-drag-strip desktop-window-drag-strip-bottom" data-tauri-drag-region onMouseDown={handleMouseDown} />
    </div>
  );
}

function AppLayout() {
  const navigate = useNavigate();

  const conversationMode = useStore((s) => s.conversationMode);
  const selectedConversationId = useStore((s) => s.selectedConversationId);
  const beginWorkspaceDraft = useStore((s) => s.beginWorkspaceDraft);

  const [sidebarCollapsed, setSidebarCollapsed] = useState(
    () => localStorage.getItem(SIDEBAR_PREF_KEY) === 'collapsed'
  );

  const [sidebarWidth, setSidebarWidth] = useState(DESKTOP_SIDEBAR_DEFAULT);
  const isResizing = useRef(false);

  const startWorkspaceDraft = useCallback((workspacePath: string) => {
    const normalized = workspacePath.trim();
    if (!normalized) return;
    beginWorkspaceDraft(normalized);
    navigate('/conversations', { replace: true });
  }, [beginWorkspaceDraft, navigate]);

  const handleOpenWorkspacePicker = useCallback(async () => {
    const selectedPath = await openNativeWorkspacePicker();
    if (selectedPath) {
      startWorkspaceDraft(selectedPath);
    }
  }, [startWorkspaceDraft]);

  useEffect(() => {
    void fetch(`${getApiBase()}/health`)
      .then((response) => (response.ok ? response.json() : null))
      .then((payload: { ui?: { built_at?: string } } | null) => {
        const serverBuiltAt = payload?.ui?.built_at;
        if (serverBuiltAt && serverBuiltAt !== __UI_BUILD_AT__) {
          console.warn(
            '[Fluxion] API is serving a different UI build than this page loaded. Run ./dev.sh desktop and restart Tauri.',
            { loaded: __UI_BUILD_AT__, server: serverBuiltAt }
          );
        }
      })
      .catch(() => {});
  }, []);

  const handleSidebarToggle = useCallback((collapsed: boolean) => {
    setSidebarCollapsed(collapsed);
    localStorage.setItem(SIDEBAR_PREF_KEY, collapsed ? 'collapsed' : 'open');
  }, []);

  const handleMouseMove = useCallback((e: MouseEvent) => {
    if (!isResizing.current) return;
    setSidebarWidth(
      Math.min(Math.max(e.clientX, DESKTOP_SIDEBAR_MIN), DESKTOP_SIDEBAR_MAX)
    );
  }, []);

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
  const emptyDesktopWindow = !selectedConversationId;
  const handleMainWindowDrag = useCallback((event: ReactMouseEvent<HTMLElement>) => {
    if (emptyDesktopWindow) {
      void startWindowDrag(event);
    }
  }, [emptyDesktopWindow]);

  const sidebarContent = (
    <>
      <DesktopTitlebar className="desktop-sidebar-header flex flex-shrink-0 flex-col">
          <div
            className="desktop-sidebar-traffic-spacer h-[var(--titlebar-height)] w-full shrink-0"
            aria-hidden
          />
          <div
            className={cn(
              'desktop-sidebar-brand-band flex h-10 w-full shrink-0 items-center',
              sidebarCollapsed
                ? 'justify-center'
                : 'justify-between gap-2 pr-2 pl-[var(--desktop-traffic-light-inset)]'
            )}
          >
            <DesktopSidebarBrand collapsed={sidebarCollapsed} />
            {!sidebarCollapsed ? (
              <div className="desktop-no-drag flex items-center gap-1">
                <ThemeToggle />
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => handleSidebarToggle(true)}
                  className="desktop-no-drag desktop-sidebar-toggle relative z-10 h-8 w-8 shrink-0 text-[var(--desktop-text-tertiary)]"
                  aria-label="Collapse sidebar"
                >
                  <PanelLeftClose className="h-4 w-4" />
                </Button>
              </div>
            ) : null}
          </div>
          {sidebarCollapsed ? (
            <div className="desktop-sidebar-toggle-row flex justify-center gap-1 pb-3">
              <ThemeToggle menuAlign="left" />
              <Button
                variant="ghost"
                size="icon"
                onClick={() => handleSidebarToggle(false)}
                className="desktop-no-drag desktop-sidebar-toggle relative z-10 h-8 w-8 shrink-0 text-[var(--desktop-text-tertiary)]"
                aria-label="Open sidebar"
              >
                <PanelLeft className="h-4 w-4" />
              </Button>
            </div>
          ) : null}
        </DesktopTitlebar>

      <div
        className={cn(
          'desktop-sidebar-body px-2 pb-1 pt-2',
          sidebarCollapsed && 'desktop-sidebar-body-collapsed'
        )}
      >
        <Button
          variant="ghost"
          onClick={() => void handleOpenWorkspacePicker()}
          className={cn(
            'h-8 w-full justify-start gap-2 rounded-lg px-2.5 text-[13px] font-normal',
            'text-[var(--desktop-text-secondary)] hover:bg-[var(--desktop-hover)] hover:text-[var(--desktop-text-primary)]'
          )}
          title="Add a workspace folder"
        >
          <FolderPlus className="h-4 w-4 opacity-70" />
          New workspace
        </Button>
      </div>

      <div
        className={cn(
          'desktop-sidebar-body flex-1 overflow-hidden',
          sidebarCollapsed && 'desktop-sidebar-body-collapsed'
        )}
      >
        <ConversationList />
      </div>

    </>
  );

  const body = (
    <div className="flex min-h-0 flex-1">
      <aside
        className={cn(
          'desktop-shell-left ui-panel relative flex flex-shrink-0 flex-col',
          'transition-[width] duration-[var(--duration-ui)] ease-[var(--ease-ui)]',
          sidebarCollapsed && 'desktop-sidebar-collapsed overflow-hidden'
        )}
        style={{
          width: sidebarCollapsed
            ? 'var(--desktop-traffic-light-inset)'
            : sidebarWidth,
        }}
      >
        {sidebarContent}
        {!sidebarCollapsed && (
          <div
            className="group absolute bottom-0 right-0 top-0 w-1 cursor-col-resize hover:bg-[var(--desktop-hover-strong)]"
            onMouseDown={handleMouseDown}
          >
            <div className="absolute right-0 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100">
              <GripVertical className="h-6 w-6 text-[var(--desktop-text-tertiary)]" />
            </div>
          </div>
        )}
      </aside>

      <main
        data-tauri-drag-region={emptyDesktopWindow ? true : undefined}
        onMouseDown={handleMainWindowDrag}
        className={cn(
          'desktop-shell-main flex min-w-0 flex-1 flex-col overflow-hidden',
          emptyDesktopWindow && 'desktop-empty-window-drag-surface'
        )}
      >
        <Routes>
          <Route path="/" element={<Navigate to="/conversations" replace />} />
          <Route path="/conversations" element={<NewConversationView />} />
          <Route path="/conversations/:conversationId" element={<ConversationSync />} />
        </Routes>
      </main>

      <TerminalPanel agentModeActive={conversationMode === 'agent'} />
    </div>
  );

  return (
    <div className="fluxion-app-bg flex h-[100dvh] flex-col text-[var(--desktop-text-primary)]">
      {body}
      <CommandPalette />
      <DesktopWindowDragFrame />
    </div>
  );
}

function App() {
  const { theme } = useTheme();
  const floating = typeof window !== 'undefined' && new URLSearchParams(window.location.search).get('floating') === '1';

  return (
    <>
      <Toaster
        position="top-right"
        richColors
        closeButton
        duration={4000}
        theme={theme}
        toastOptions={{
          className: 'sonner-toast border border-[var(--desktop-border-strong)] bg-zinc-900 text-[var(--desktop-text-primary)]',
        }}
      />
      {floating ? (
        <FloatingOverlay key={typeof window !== 'undefined' ? window.location.search : 'floating'} />
      ) : (
        <Routes>
          <Route path="/*" element={<AppLayout />} />
        </Routes>
      )}
    </>
  );
}

export default App;
