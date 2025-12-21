// Main application component with collapsible sidebar

import { useState, useRef, useCallback } from 'react';
import { ConversationList } from '@/components/ConversationList';
import { ConversationView } from '@/components/ConversationView';
import { DetailPanel } from '@/components/DetailPanel';
import { useStore } from '@/hooks/useStore';
import { cn } from '@/lib/utils';
import { PanelLeftClose, PanelLeft, GripVertical } from 'lucide-react';
import { Button } from '@/components/ui/button';

function App() {
  const detailPanelOpen = useStore((s) => s.detailPanelOpen);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [sidebarWidth, setSidebarWidth] = useState(320); // default 320px
  const isResizing = useRef(false);

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
      {/* Left Sidebar - Conversation List */}
      <aside
        className={cn(
          "border-r flex flex-col flex-shrink-0 transition-all duration-300 relative",
          sidebarCollapsed ? "w-0 overflow-hidden" : ""
        )}
        style={{ width: sidebarCollapsed ? 0 : sidebarWidth }}
      >
        <div className="p-4 border-b flex items-center justify-between">
          <div>
            <h1 className="text-lg font-bold">Reasoner</h1>
            <p className="text-xs text-muted-foreground">Local AI Chat</p>
          </div>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setSidebarCollapsed(true)}
            className="h-8 w-8"
          >
            <PanelLeftClose className="h-4 w-4" />
          </Button>
        </div>
        <div className="flex-1 overflow-hidden">
          <ConversationList />
        </div>

        {/* Resize handle */}
        <div
          className="absolute right-0 top-0 bottom-0 w-1 cursor-col-resize hover:bg-blue-400 transition-colors group"
          onMouseDown={handleMouseDown}
        >
          <div className="absolute right-0 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity">
            <GripVertical className="h-6 w-6 text-blue-400" />
          </div>
        </div>
      </aside>

      {/* Collapsed sidebar toggle */}
      {sidebarCollapsed && (
        <div className="border-r p-2 flex flex-col items-center">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setSidebarCollapsed(false)}
          >
            <PanelLeft className="h-4 w-4" />
          </Button>
        </div>
      )}

      {/* Main content - Chat */}
      <main
        className={cn(
          "flex-1 overflow-hidden transition-all duration-300",
          detailPanelOpen && "lg:mr-[400px]"
        )}
      >
        <ConversationView />
      </main>

      {/* Right Detail Panel - Trace JSON */}
      <DetailPanel />
    </div>
  );
}

export default App;
