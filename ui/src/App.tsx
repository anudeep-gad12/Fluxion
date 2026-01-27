// Main application component with collapsible sidebar

import { useState, useRef, useCallback, useEffect } from 'react';
import { Routes, Route, Navigate, useParams, useSearchParams, useNavigate } from 'react-router-dom';
import { ConversationList } from '@/components/ConversationList';
import { ConversationView } from '@/components/ConversationView';
import { DetailPanel } from '@/components/DetailPanel';
import { BenchmarksPage } from '@/components/BenchmarksPage';
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
  const selectedConversationId = useStore((s) => s.selectedConversationId);
  const selectConversation = useStore((s) => s.selectConversation);

  useEffect(() => {
    // Sync URL → store when URL changes
    if (conversationId && conversationId !== selectedConversationId) {
      selectConversation(conversationId);
    } else if (!conversationId && selectedConversationId) {
      // URL has no conversation, but store does - navigate to it
      // This is handled by the parent, just clear the store selection
    }
  }, [conversationId, selectedConversationId, selectConversation]);

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
  const detailPanelOpen = useStore((s) => s.detailPanelOpen);
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
  const [sidebarWidth, setSidebarWidth] = useState(320); // default 320px
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
    const newWidth = Math.min(Math.max(e.clientX, 200), 500); // min 200, max 500
    setSidebarWidth(newWidth);
  }, []);

  const handleMouseUp = useCallback(() => {
    isResizing.current = false;
    document.removeEventListener('mousemove', handleMouseMove);
    document.removeEventListener('mouseup', handleMouseUp);
  }, [handleMouseMove]);

  return (
    <div className="h-screen flex bg-gradient-to-br from-slate-50 via-white to-blue-50">
      {/* Mobile header - only show on mobile */}
      {isMobile && (
        <header className="fixed top-0 left-0 right-0 h-14 bg-white border-b flex items-center justify-between px-4 z-40">
          <div className="flex items-center gap-2">
            {/* Hamburger menu - respect demo mode restrictions */}
            {(isOwner || !isDemoMode) && (
              <button
                onClick={() => handleSidebarToggle(false)}
                className="p-2 -ml-2 hover:bg-slate-100 rounded-md transition-colors"
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
          "border-r flex flex-col flex-shrink-0 transition-all duration-300 relative bg-white",
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
        <div className="p-4 border-b flex items-center justify-between">
          <div>
            <h1 className="text-lg font-bold">Reasoner</h1>
            <p className="text-xs text-muted-foreground">Local AI Chat</p>
          </div>
          {/* Mobile: close button, Desktop: collapse button */}
          <Button
            variant="ghost"
            size="icon"
            onClick={() => handleSidebarToggle(true)}
            className="h-8 w-8"
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
            className="absolute right-0 top-0 bottom-0 w-1 cursor-col-resize hover:bg-blue-400 transition-colors group"
            onMouseDown={handleMouseDown}
          >
            <div className="absolute right-0 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity">
              <GripVertical className="h-6 w-6 text-blue-400" />
            </div>
          </div>
        )}
      </aside>

      {/* Collapsed sidebar strip with New Chat button - hide on mobile */}
      {sidebarCollapsed && !isMobile && (
        <div className="border-r p-2 flex flex-col items-center gap-2">
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
          className="fixed inset-0 bg-black/20 z-40"
          onClick={() => handleSidebarToggle(true)}
        />
      )}

      {/* Main content - Chat with Routes */}
      <main
        className={cn(
          "flex-1 overflow-hidden transition-all duration-300",
          // Mobile: add top padding for fixed header
          isMobile && "pt-14",
          // Desktop: add right margin when detail panel is open
          detailPanelOpen && "lg:mr-[400px]"
        )}
      >
        <Routes>
          <Route path="/" element={<Navigate to="/conversations" replace />} />
          <Route path="/conversations" element={<NewConversationView />} />
          <Route path="/conversations/:conversationId" element={<ConversationSync />} />
        </Routes>
      </main>

      {/* Right Detail Panel - Trace JSON */}
      <DetailPanel />
    </div>
  );
}

function App() {
  return (
    <Routes>
      <Route path="/benchmarks" element={<BenchmarksPage />} />
      <Route path="/*" element={<AppLayout />} />
    </Routes>
  );
}

export default App;

