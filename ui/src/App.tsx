// Main application component with collapsible sidebar

import { useState, useRef, useCallback, useEffect } from 'react';
import { Routes, Route, Navigate, useParams, useSearchParams, useNavigate } from 'react-router-dom';
import { Toaster } from 'sonner';
import { ConversationList } from '@/components/ConversationList';
import { ConversationView, isConversationMissing } from '@/components/ConversationView';
import { useStore, useHasActiveRun } from '@/hooks/useStore';
import { cn } from '@/lib/utils';
import { PanelLeftClose, PanelLeft, GripVertical, Plus, Menu, X } from 'lucide-react';
import { Button } from '@/components/ui/button';

// LocalStorage keys for demo mode
const OWNER_TOKEN_KEY = 'reasoner_owner_token';
const SIDEBAR_PREF_KEY = 'reasoner_sidebar_pref';

// Component to sync URL params with store
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
    // Sync URL → store when URL changes
    if (conversationId && conversationId !== selectedConversationId) {
      selectConversation(conversationId);
    } else if (!conversationId && selectedConversationId) {
      selectConversation(null);
    }
  }, [conversationId, navigate, selectedConversationId, selectConversation]);

  return <ConversationView />;
}

// Component for /conversations route - shows "new conversation" empty state
// This clears selection so user can type first message (lazy creation)
function NewConversationView() {
  const selectConversation = useStore((s) => s.selectConversation);

  useEffect(() => {
    // Clear any selected conversation when on this route
    selectConversation(null);
  }, [selectConversation]);

  return <ConversationView />;
}

function AppLayout() {
  const hasActiveRun = useHasActiveRun();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();

  // Owner detection - check localStorage for owner token
  const [isOwner, setIsOwner] = useState(() => {
    const token = localStorage.getItem(OWNER_TOKEN_KEY);
    return Boolean(token && token.length >= 16);
  });

  // Demo mode state - fetched from backend
  const [isDemoMode, setIsDemoMode] = useState(false);

  // Sidebar state - defaults to collapsed for non-owners in demo mode
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    // If owner, respect their saved preference
    if (localStorage.getItem(OWNER_TOKEN_KEY)) {
      return localStorage.getItem(SIDEBAR_PREF_KEY) === 'collapsed';
    }
    // For non-owners, start collapsed (demo mode will enforce this)
    return true;
  });
  const [sidebarWidth, setSidebarWidth] = useState(392); // default 392px
  const isResizing = useRef(false);

  // Mobile detection - below md: breakpoint (768px)
  const [isMobile, setIsMobile] = useState(() => {
    return typeof window !== 'undefined' && window.innerWidth < 768;
  });

  // Check for owner secret in URL params (?owner=<secret>)
  useEffect(() => {
    const ownerParam = searchParams.get('owner');
    if (ownerParam && ownerParam.length >= 16) {
      // Store the token
      localStorage.setItem(OWNER_TOKEN_KEY, ownerParam);
      setIsOwner(true);
      // Open sidebar for owner
      setSidebarCollapsed(false);
      // Remove param from URL (clean up)
      searchParams.delete('owner');
      setSearchParams(searchParams, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  // Fetch demo mode status from backend
  useEffect(() => {
    fetch('/api/config')
      .then((res) => res.json())
      .then((data) => {
        setIsDemoMode(data.demo?.enabled ?? false);
      })
      .catch(() => {
        // Default to non-demo if config fails
        setIsDemoMode(false);
      });
  }, []);

  // Enforce sidebar collapsed for non-owners in demo mode
  useEffect(() => {
    if (isDemoMode && !isOwner) {
      setSidebarCollapsed(true);
    }
  }, [isDemoMode, isOwner]);

  // Mobile detection on resize
  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth < 768);
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // Handle sidebar toggle with demo mode enforcement
  const handleSidebarToggle = useCallback(
    (collapsed: boolean) => {
      // Prevent non-owners from opening sidebar in demo mode
      if (!collapsed && isDemoMode && !isOwner) {
        return;
      }
      setSidebarCollapsed(collapsed);
      // Save preference for owners
      if (isOwner) {
        localStorage.setItem(SIDEBAR_PREF_KEY, collapsed ? 'collapsed' : 'open');
      }
    },
    [isDemoMode, isOwner]
  );

  // Navigate to new conversation (blocked during active run)
  const handleNewConversation = useCallback(() => {
    if (hasActiveRun) return;
    navigate('/conversations');
  }, [navigate, hasActiveRun]);

  const handleMouseDown = useCallback(() => {
    isResizing.current = true;
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
  }, []);

  const handleMouseMove = useCallback((e: MouseEvent) => {
    if (!isResizing.current) return;
    const newWidth = Math.min(Math.max(e.clientX, 280), 520); // min 280, max 520
    setSidebarWidth(newWidth);
  }, []);

  const handleMouseUp = useCallback(() => {
    isResizing.current = false;
    document.removeEventListener('mousemove', handleMouseMove);
    document.removeEventListener('mouseup', handleMouseUp);
  }, [handleMouseMove]);

  return (
    <div className="fluxion-app-bg h-[100dvh] flex text-zinc-100">
      {/* Mobile header - only show on mobile */}
      {isMobile && (
        <header className="fluxion-topbar fixed top-0 left-0 right-0 z-40 flex h-14 items-center justify-between border-b px-4">
          <div className="flex items-center gap-2">
            {/* Hamburger menu - respect demo mode restrictions */}
            {(isOwner || !isDemoMode) && (
              <button
                onClick={() => handleSidebarToggle(false)}
                className="ui-transition -ml-2 rounded-xl p-2 text-zinc-400 hover:bg-white/[0.055] hover:text-cyan-100"
                aria-label="Open menu"
              >
                <Menu className="h-6 w-6" />
              </button>
            )}
          </div>
          {/* New Chat button - disabled during active run */}
          <span title={hasActiveRun ? "Active run in progress — cannot start new conversation until complete" : "New conversation"}>
            <Button
              variant="ghost"
              size="icon"
              onClick={handleNewConversation}
              disabled={hasActiveRun}
              className="h-9 w-9"
            >
              <Plus className="h-5 w-5" />
            </Button>
          </span>
        </header>
      )}

      {/* Left Sidebar - Conversation List */}
      <aside
        className={cn(
          "ui-panel border-r border-white/10 flex flex-col flex-shrink-0 ui-transition relative",
          // Mobile: fixed overlay drawer
          isMobile && "fixed md:static inset-y-0 left-0 z-50 w-[80vw] max-w-[320px]",
          isMobile && (sidebarCollapsed ? "-translate-x-full" : "translate-x-0"),
          // Desktop: normal sidebar behavior
          !isMobile && (sidebarCollapsed ? "w-0 overflow-hidden" : ""),
          // Mobile: add padding for fixed header
          isMobile && "pt-14"
        )}
        style={!isMobile && !sidebarCollapsed ? { width: sidebarWidth } : undefined}
      >
        <div className="flex items-center justify-between border-b border-white/10 px-4 py-4">
          <h1 className="font-mono text-lg font-semibold tracking-[-0.04em] text-zinc-50">fluxion&gt;</h1>
          {/* Mobile: close button, Desktop: collapse button */}
          <Button
            variant="ghost"
            size="icon"
            onClick={() => handleSidebarToggle(true)}
            className="h-8 w-8 text-zinc-500"
          >
            {isMobile ? <X className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
          </Button>
        </div>
        <div className="flex-1 overflow-hidden">
          <ConversationList />
        </div>

        {/* Resize handle - only show on desktop */}
        {!isMobile && (
          <div
            className="group absolute right-0 top-0 bottom-0 w-1 cursor-col-resize ui-transition hover:bg-white/10"
            onMouseDown={handleMouseDown}
          >
            <div className="absolute right-0 top-1/2 -translate-y-1/2 opacity-0 ui-transition group-hover:opacity-100">
              <GripVertical className="h-6 w-6 text-zinc-600" />
            </div>
          </div>
        )}
      </aside>

      {/* Collapsed sidebar strip with New Chat button - hide on mobile */}
      {sidebarCollapsed && !isMobile && (
        <div className="ui-panel flex flex-col items-center gap-2 border-r border-white/10 p-2.5">
          {/* Expand button - only show for owners or when not in demo mode */}
          {(isOwner || !isDemoMode) && (
            <Button
              variant="ghost"
              size="icon"
              onClick={() => handleSidebarToggle(false)}
              title="Open sidebar"
            >
              <PanelLeft className="h-4 w-4" />
            </Button>
          )}
          {/* New Chat button - always visible, disabled during active run */}
          <span title={hasActiveRun ? "Active run in progress — cannot start new conversation until complete" : "New conversation"}>
            <Button
              variant="ghost"
              size="icon"
              onClick={handleNewConversation}
              disabled={hasActiveRun}
            >
              <Plus className="h-4 w-4" />
            </Button>
          </span>
        </div>
      )}

      {/* Mobile backdrop - overlay when sidebar is open */}
      {isMobile && !sidebarCollapsed && (
        <div
          className="fixed inset-0 z-40 bg-black/65 backdrop-blur-[2px]"
          onClick={() => handleSidebarToggle(true)}
        />
      )}

      {/* Main content - Chat with Routes */}
      <main
        className={cn(
          "flex-1 overflow-hidden flex flex-col",
          // Mobile: add top padding for fixed header
          isMobile && "pt-14"
        )}
      >
        <Routes>
          <Route path="/" element={<Navigate to="/conversations" replace />} />
          <Route path="/conversations" element={<NewConversationView />} />
          <Route path="/conversations/:conversationId" element={<ConversationSync />} />
        </Routes>
      </main>
    </div>
  );
}

function App() {
  return (
    <>
      <Toaster position="top-right" richColors closeButton duration={4000} theme="dark" />
      <Routes>
        <Route path="/*" element={<AppLayout />} />
      </Routes>
    </>
  );
}

export default App;
