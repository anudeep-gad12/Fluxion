// Main application component with collapsible sidebar

import { useState, useRef, useCallback, useEffect } from 'react';
import { Routes, Route, Navigate, useParams, useSearchParams, useNavigate } from 'react-router-dom';
import { Toaster } from 'sonner';
import { ConversationList } from '@/components/ConversationList';
import { ConversationView, isConversationMissing } from '@/components/ConversationView';
import { WorkspacePickerDialog } from '@/components/WorkspacePickerDialog';
import { TerminalPanel } from '@/components/desktop/TerminalPanel';
import { DesktopTitlebar } from '@/components/desktop/DesktopTitlebar';
import { AppBrandIcon } from '@/components/AppBrandIcon';
import { DesktopSidebarBrand } from '@/components/desktop/DesktopSidebarBrand';
import { startWindowDrag } from '@/lib/windowDrag';
import { useStore, useHasActiveRun } from '@/hooks/useStore';
import { getApiBase } from '@/api/client';
import { isLocalDesktopApp, openNativeWorkspacePicker } from '@/lib/platform';
import { cn } from '@/lib/utils';
import { PanelLeftClose, PanelLeft, GripVertical, FolderPlus } from 'lucide-react';
import { Button } from '@/components/ui/button';

const OWNER_TOKEN_KEY = 'reasoner_owner_token';
const SIDEBAR_PREF_KEY = 'reasoner_sidebar_pref';
const DESKTOP_SIDEBAR_DEFAULT = 272;
const DESKTOP_SIDEBAR_MIN = 240;
const DESKTOP_SIDEBAR_MAX = 360;

function ConversationSync() {
  const { conversationId } = useParams<{ conversationId: string }>();
  const navigate = useNavigate();
  const selectedConversationId = useStore((s) => s.selectedConversationId);
  const selectConversation = useStore((s) => s.selectConversation);

  useEffect(() => {
    if (conversationId && isConversationMissing(conversationId)) {
      if (selectedConversationId) {
        selectConversation(null);
      }
      navigate('/conversations', { replace: true });
      return;
    }
    if (conversationId && conversationId !== selectedConversationId) {
      selectConversation(conversationId);
    } else if (!conversationId && selectedConversationId) {
      selectConversation(null);
    }
  }, [conversationId, navigate, selectedConversationId, selectConversation]);

  return <ConversationView />;
}

function NewConversationView() {
  const selectConversation = useStore((s) => s.selectConversation);

  useEffect(() => {
    selectConversation(null);
  }, [selectConversation]);

  return <ConversationView />;
}

function AppLayout() {
  const hasActiveRun = useHasActiveRun();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();

  const localDesktop = isLocalDesktopApp();
  const conversationMode = useStore((s) => s.conversationMode);
  const draftWorkspacePath = useStore((s) => s.draftWorkspacePath);
  const selectConversation = useStore((s) => s.selectConversation);
  const rememberWorkspacePath = useStore((s) => s.rememberWorkspacePath);
  const setDraftWorkspacePath = useStore((s) => s.setDraftWorkspacePath);

  const [isOwner, setIsOwner] = useState(() => {
    if (localDesktop) return true;
    const token = localStorage.getItem(OWNER_TOKEN_KEY);
    return Boolean(token && token.length >= 16);
  });

  const [isDemoMode, setIsDemoMode] = useState(false);
  const [workspacePickerOpen, setWorkspacePickerOpen] = useState(false);

  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    if (localDesktop) {
      return localStorage.getItem(SIDEBAR_PREF_KEY) === 'collapsed';
    }
    if (localStorage.getItem(OWNER_TOKEN_KEY)) {
      return localStorage.getItem(SIDEBAR_PREF_KEY) === 'collapsed';
    }
    return true;
  });

  const [sidebarWidth, setSidebarWidth] = useState(
    localDesktop ? DESKTOP_SIDEBAR_DEFAULT : 392
  );
  const isResizing = useRef(false);

  const [isMobile, setIsMobile] = useState(() => {
    if (localDesktop) return false;
    return typeof window !== 'undefined' && window.innerWidth < 768;
  });

  const startWorkspaceDraft = useCallback((workspacePath: string) => {
    const normalized = workspacePath.trim();
    if (!normalized || hasActiveRun) return;
    selectConversation(null);
    rememberWorkspacePath(normalized);
    setDraftWorkspacePath(normalized);
    navigate('/conversations');
  }, [hasActiveRun, navigate, rememberWorkspacePath, selectConversation, setDraftWorkspacePath]);

  const handleOpenWorkspacePicker = useCallback(async () => {
    if (hasActiveRun) return;
    if (localDesktop) {
      const selectedPath = await openNativeWorkspacePicker();
      if (selectedPath) {
        startWorkspaceDraft(selectedPath);
      }
      return;
    }
    setWorkspacePickerOpen(true);
  }, [hasActiveRun, localDesktop, startWorkspaceDraft]);

  useEffect(() => {
    const ownerParam = searchParams.get('owner');
    if (ownerParam && ownerParam.length >= 16) {
      localStorage.setItem(OWNER_TOKEN_KEY, ownerParam);
      setIsOwner(true);
      setSidebarCollapsed(false);
      searchParams.delete('owner');
      setSearchParams(searchParams, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  useEffect(() => {
    if (!localDesktop) return;
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
  }, [localDesktop]);

  useEffect(() => {
    if (localDesktop) {
      setIsOwner(true);
      setIsDemoMode(false);
      return;
    }
    fetch(`${getApiBase()}/config`)
      .then((res) => res.json())
      .then((data) => {
        if (data.local_app) {
          setIsOwner(true);
          setIsDemoMode(false);
          return;
        }
        setIsDemoMode(data.demo?.enabled ?? false);
      })
      .catch(() => {
        setIsDemoMode(false);
      });
  }, [localDesktop]);

  useEffect(() => {
    if (localDesktop) return;
    if (isDemoMode && !isOwner) {
      setSidebarCollapsed(true);
    }
  }, [isDemoMode, isOwner, localDesktop]);

  useEffect(() => {
    if (localDesktop) return;
    const handleResize = () => {
      setIsMobile(window.innerWidth < 768);
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [localDesktop]);

  const handleSidebarToggle = useCallback(
    (collapsed: boolean) => {
      if (!collapsed && isDemoMode && !isOwner) {
        return;
      }
      setSidebarCollapsed(collapsed);
      if (isOwner || localDesktop) {
        localStorage.setItem(SIDEBAR_PREF_KEY, collapsed ? 'collapsed' : 'open');
      }
    },
    [isDemoMode, isOwner, localDesktop]
  );

  const handleMouseMove = useCallback(
    (e: MouseEvent) => {
      if (!isResizing.current) return;
      const min = localDesktop ? DESKTOP_SIDEBAR_MIN : 280;
      const max = localDesktop ? DESKTOP_SIDEBAR_MAX : 520;
      setSidebarWidth(Math.min(Math.max(e.clientX, min), max));
    },
    [localDesktop]
  );

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

  const sidebarContent = (
    <>
      {localDesktop ? (
        <DesktopTitlebar className="desktop-sidebar-header flex flex-shrink-0 flex-col">
          <div
            className="desktop-sidebar-traffic-spacer h-[var(--titlebar-height)] w-full shrink-0"
            aria-hidden
          />
          <div
            className={cn(
              'desktop-sidebar-brand-band desktop-no-drag flex h-10 w-full shrink-0 items-center',
              sidebarCollapsed
                ? 'justify-center'
                : 'justify-between gap-2 pr-2 pl-[var(--desktop-traffic-light-inset)]'
            )}
          >
            <DesktopSidebarBrand collapsed={sidebarCollapsed} />
            {!sidebarCollapsed ? (
              <Button
                variant="ghost"
                size="icon"
                onClick={() => handleSidebarToggle(true)}
                className="desktop-sidebar-toggle relative z-10 h-8 w-8 shrink-0 text-zinc-500"
                aria-label="Collapse sidebar"
              >
                <PanelLeftClose className="h-4 w-4" />
              </Button>
            ) : null}
          </div>
          {sidebarCollapsed ? (
            <div className="desktop-sidebar-toggle-row desktop-no-drag flex justify-center pb-3">
              <Button
                variant="ghost"
                size="icon"
                onClick={() => handleSidebarToggle(false)}
                className="desktop-sidebar-toggle relative z-10 h-8 w-8 shrink-0 text-zinc-500"
                aria-label="Open sidebar"
              >
                <PanelLeft className="h-4 w-4" />
              </Button>
            </div>
          ) : null}
        </DesktopTitlebar>
      ) : (
      <div className="relative flex flex-shrink-0 items-center justify-between px-4 py-4">
        <div className="flex min-w-0 flex-1 items-center gap-2.5">
          <AppBrandIcon className="h-7 w-7" />
          <span className="truncate text-[15px] font-semibold tracking-tight text-zinc-50">
            Fluxion
          </span>
        </div>
        <Button
          variant="ghost"
          size="icon"
          onClick={() => handleSidebarToggle(true)}
          className="h-8 w-8 shrink-0 text-zinc-500"
          aria-label="Collapse sidebar"
        >
          <PanelLeftClose className="h-4 w-4" />
        </Button>
      </div>
      )}

      {localDesktop && (
        <div
          className={cn(
            'desktop-sidebar-body px-2 pb-1 pt-2',
            sidebarCollapsed && 'desktop-sidebar-body-collapsed'
          )}
        >
          <Button
            variant="ghost"
            onClick={() => void handleOpenWorkspacePicker()}
            disabled={hasActiveRun}
            className={cn(
              'h-8 w-full justify-start gap-2 rounded-lg px-2.5 text-[13px] font-normal',
              'text-zinc-400 hover:bg-white/[0.05] hover:text-zinc-100'
            )}
            title={
              hasActiveRun
                ? 'Active run in progress'
                : 'Add a workspace folder'
            }
          >
            <FolderPlus className="h-4 w-4 opacity-70" />
            New workspace
          </Button>
        </div>
      )}

      <div
        className={cn(
          'flex-1 overflow-hidden',
          localDesktop && 'desktop-sidebar-body',
          localDesktop && sidebarCollapsed && 'desktop-sidebar-body-collapsed'
        )}
      >
        <ConversationList
          workspacePickerOpen={workspacePickerOpen}
          onWorkspacePickerOpenChange={setWorkspacePickerOpen}
        />
      </div>

    </>
  );

  const body = (
    <div className="flex min-h-0 flex-1">
      <aside
        className={cn(
          'desktop-shell-left ui-panel relative flex flex-shrink-0 flex-col',
          isMobile && 'fixed inset-y-0 left-0 z-50 w-[80vw] max-w-[320px]',
          isMobile && (sidebarCollapsed ? '-translate-x-full' : 'translate-x-0'),
          !isMobile && !localDesktop && sidebarCollapsed && 'w-0 overflow-hidden',
          localDesktop &&
            !isMobile &&
            'transition-[width] duration-200 ease-[cubic-bezier(0.4,0,0.2,1)]',
          localDesktop && !isMobile && sidebarCollapsed && 'desktop-sidebar-collapsed overflow-hidden'
        )}
        style={
          !isMobile
            ? {
                width: localDesktop
                  ? sidebarCollapsed
                    ? 'var(--desktop-traffic-light-inset)'
                    : sidebarWidth
                  : sidebarCollapsed
                    ? undefined
                    : sidebarWidth,
              }
            : undefined
        }
      >
        {sidebarContent}
        {!isMobile && !sidebarCollapsed && (
          <div
            className="group absolute bottom-0 right-0 top-0 w-1 cursor-col-resize hover:bg-white/10"
            onMouseDown={handleMouseDown}
          >
            <div className="absolute right-0 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100">
              <GripVertical className="h-6 w-6 text-zinc-600" />
            </div>
          </div>
        )}
      </aside>

      {sidebarCollapsed && !isMobile && !localDesktop && (
        <div
          className="desktop-panel-rail desktop-shell-left ui-panel relative flex flex-shrink-0 flex-col items-center py-3"
          style={{ width: 'var(--desktop-traffic-light-inset)' }}
          data-tauri-drag-region
          onMouseDown={(event) => void startWindowDrag(event)}
        >
          {(isOwner || !isDemoMode) && (
            <Button
              variant="ghost"
              size="icon"
              onClick={() => handleSidebarToggle(false)}
              className="desktop-no-drag relative z-10 mt-1"
              title="Open sidebar"
              aria-label="Open sidebar"
            >
              <PanelLeft className="h-4 w-4" />
            </Button>
          )}
        </div>
      )}

      {isMobile && !sidebarCollapsed && (
        <div
          className="fixed inset-0 z-40 bg-black/65 backdrop-blur-[2px]"
          onClick={() => handleSidebarToggle(true)}
        />
      )}

      <main className="desktop-shell-main flex min-w-0 flex-1 flex-col overflow-hidden">
        <Routes>
          <Route path="/" element={<Navigate to="/conversations" replace />} />
          <Route path="/conversations" element={<NewConversationView />} />
          <Route path="/conversations/:conversationId" element={<ConversationSync />} />
        </Routes>
      </main>

      {localDesktop && (
        <TerminalPanel agentModeActive={conversationMode === 'agent'} />
      )}
    </div>
  );

  const workspacePicker = (
    <WorkspacePickerDialog
      open={workspacePickerOpen}
      onOpenChange={setWorkspacePickerOpen}
      value={draftWorkspacePath}
      onSelect={startWorkspaceDraft}
    />
  );

  if (localDesktop) {
    return (
      <div className="fluxion-app-bg flex h-[100dvh] flex-col text-zinc-100">
        {body}
        {workspacePicker}
      </div>
    );
  }

  return (
    <div className="fluxion-app-bg flex h-[100dvh] flex-col text-zinc-100">
      <div className={cn('flex min-h-0 flex-1 flex-col')}>{body}</div>
      {workspacePicker}
    </div>
  );
}

function App() {
  const desktop = isLocalDesktopApp();

  return (
    <>
      <Toaster
        position="top-right"
        richColors
        closeButton
        duration={4000}
        theme="dark"
        toastOptions={{
          className: desktop ? 'sonner-toast border border-white/10 bg-zinc-900 text-zinc-100' : undefined,
        }}
      />
      <Routes>
        <Route path="/*" element={<AppLayout />} />
      </Routes>
    </>
  );
}

export default App;
