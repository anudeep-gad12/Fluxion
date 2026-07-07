import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router-dom';
import {
  FolderPlus,
  MessageSquare,
  MessageSquarePlus,
  Monitor,
  Moon,
  PanelBottom,
  Sparkles,
  Sun,
  type LucideIcon,
} from 'lucide-react';
import { useStore } from '@/hooks/useStore';
import { useMountTransition } from '@/hooks/useMountTransition';
import { useTheme } from '@/hooks/useTheme';
import { useTerminalPanelToggle } from '@/components/desktop/TerminalPanel';
import { truncate } from '@/lib/utils';
import type { Conversation } from '@/types';

const MAX_CONVERSATIONS = 15;

interface PaletteAction {
  id: string;
  title: string;
  meta?: string;
  keywords: string;
  icon: LucideIcon;
  shortcut?: string;
  run: () => void;
}

function isHiddenConversation(conversation: Conversation): boolean {
  return (
    conversation.metadata?.hidden === true ||
    conversation.metadata?.hide_from_sidebar === true
  );
}

function conversationActivityAt(conversation: Conversation): string {
  return conversation.updated_at || conversation.created_at;
}

function workspaceName(workspacePath?: string | null): string | null {
  if (!workspacePath) return null;
  return workspacePath.split('/').filter(Boolean).pop() || null;
}

export function CommandPalette() {
  const navigate = useNavigate();
  const open = useStore((s) => s.commandPaletteOpen);
  const setOpen = useStore((s) => s.setCommandPaletteOpen);
  const setDesktopOverlayOpen = useStore((s) => s.setDesktopOverlayOpen);
  const conversations = useStore((s) => s.conversations);
  const workspacePaths = useStore((s) => s.workspacePaths);
  const beginWorkspaceDraft = useStore((s) => s.beginWorkspaceDraft);
  const bumpDraftConversation = useStore((s) => s.bumpDraftConversation);
  const setConversationMode = useStore((s) => s.setConversationMode);
  const toggleTerminalPanel = useTerminalPanelToggle();
  const { setPreference } = useTheme();
  const { mounted, closing } = useMountTransition(open);

  const [query, setQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const paletteRef = useRef<HTMLDivElement>(null);
  const restoreFocusRef = useRef<HTMLElement | null>(null);

  const close = useCallback(() => setOpen(false), [setOpen]);

  const startNewConversation = useCallback(
    (workspacePath?: string) => {
      if (workspacePath) {
        beginWorkspaceDraft(workspacePath);
      } else {
        bumpDraftConversation();
      }
      navigate('/conversations', { replace: true });
    },
    [beginWorkspaceDraft, bumpDraftConversation, navigate],
  );

  // ⌘K toggles from anywhere, including text inputs.
  useEffect(() => {
    const handleKeyDown = (event: globalThis.KeyboardEvent) => {
      if (
        (event.metaKey || event.ctrlKey) &&
        !event.shiftKey &&
        !event.altKey &&
        event.key.toLowerCase() === 'k'
      ) {
        event.preventDefault();
        setOpen(!useStore.getState().commandPaletteOpen);
        return;
      }
      if (event.key === 'Escape' && useStore.getState().commandPaletteOpen) {
        event.preventDefault();
        event.stopPropagation();
        setOpen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [setOpen]);

  // Hide native browser webviews while the palette is up; reset on open.
  // ConversationView owns clearing the aggregate overlay flag so closing this
  // palette cannot expose a webview beneath another open dialog.
  useEffect(() => {
    if (!open) return;
    restoreFocusRef.current = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    setDesktopOverlayOpen(true);
    setQuery('');
    setActiveIndex(0);
    const raf = requestAnimationFrame(() => inputRef.current?.focus());
    return () => {
      cancelAnimationFrame(raf);
      restoreFocusRef.current?.focus({ preventScroll: true });
      restoreFocusRef.current = null;
    };
  }, [open, setDesktopOverlayOpen]);

  const actions = useMemo<PaletteAction[]>(() => {
    const items: PaletteAction[] = [
      {
        id: 'new-conversation',
        title: 'New conversation',
        keywords: 'new conversation chat start create',
        icon: MessageSquarePlus,
        run: () => startNewConversation(),
      },
    ];
    for (const workspacePath of workspacePaths) {
      const name = workspaceName(workspacePath);
      if (!name) continue;
      items.push({
        id: `workspace-${workspacePath}`,
        title: `New conversation in ${name}`,
        meta: 'Workspace',
        keywords: `new workspace conversation ${name} ${workspacePath}`,
        icon: FolderPlus,
        run: () => startNewConversation(workspacePath),
      });
    }
    items.push(
      {
        id: 'toggle-terminal',
        title: 'Toggle terminal panel',
        keywords: 'terminal panel tools browser toggle',
        icon: PanelBottom,
        run: toggleTerminalPanel,
      },
      {
        id: 'mode-agent',
        title: 'Switch to Agent mode',
        meta: 'Mode',
        keywords: 'agent mode switch tools',
        icon: Sparkles,
        shortcut: '⌘1',
        run: () => setConversationMode('agent'),
      },
      {
        id: 'mode-chat',
        title: 'Switch to Chat mode',
        meta: 'Mode',
        keywords: 'chat mode switch conversation',
        icon: MessageSquare,
        shortcut: '⌘2',
        run: () => setConversationMode('chat'),
      },
      {
        id: 'theme-light',
        title: 'Theme: Light',
        meta: 'Appearance',
        keywords: 'theme light appearance color',
        icon: Sun,
        run: () => setPreference('light'),
      },
      {
        id: 'theme-dark',
        title: 'Theme: Dark',
        meta: 'Appearance',
        keywords: 'theme dark appearance color',
        icon: Moon,
        run: () => setPreference('dark'),
      },
      {
        id: 'theme-system',
        title: 'Theme: System',
        meta: 'Appearance',
        keywords: 'theme system appearance auto',
        icon: Monitor,
        run: () => setPreference('system'),
      },
    );
    return items;
  }, [
    setConversationMode,
    setPreference,
    startNewConversation,
    toggleTerminalPanel,
    workspacePaths,
  ]);

  const recentConversations = useMemo(
    () =>
      conversations
        .filter((conversation) => !isHiddenConversation(conversation))
        .slice()
        .sort(
          (a, b) =>
            new Date(conversationActivityAt(b)).getTime() -
            new Date(conversationActivityAt(a)).getTime(),
        )
        .slice(0, MAX_CONVERSATIONS),
    [conversations],
  );

  const { filteredActions, filteredConversations } = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) {
      return { filteredActions: actions, filteredConversations: recentConversations };
    }
    const matchedActions = actions.filter((action) =>
      `${action.title} ${action.keywords}`.toLowerCase().includes(q),
    );
    const matchedConversations = recentConversations.filter((conversation) => {
      const name = workspaceName(conversation.workspace_path);
      return `${conversation.title ?? ''} ${name ?? ''}`.toLowerCase().includes(q);
    });
    return {
      filteredActions: matchedActions,
      filteredConversations: matchedConversations,
    };
  }, [actions, query, recentConversations]);

  // Flat list drives keyboard selection across both sections.
  const flatItems = useMemo(
    () => [
      ...filteredActions.map((action) => ({ kind: 'action' as const, action })),
      ...filteredConversations.map((conversation) => ({
        kind: 'conversation' as const,
        conversation,
      })),
    ],
    [filteredActions, filteredConversations],
  );

  useEffect(() => {
    setActiveIndex(0);
  }, [query]);

  useEffect(() => {
    if (activeIndex >= flatItems.length && flatItems.length > 0) {
      setActiveIndex(flatItems.length - 1);
    }
  }, [activeIndex, flatItems.length]);

  const runItem = useCallback(
    (index: number) => {
      const item = flatItems[index];
      if (!item) return;
      if (item.kind === 'action') {
        item.action.run();
      } else {
        navigate(`/conversations/${item.conversation.conversation_id}`);
      }
      close();
    },
    [close, flatItems, navigate],
  );

  const handleInputKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLInputElement>) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        close();
        return;
      }
      if (event.key === 'ArrowDown') {
        event.preventDefault();
        setActiveIndex((current) =>
          flatItems.length === 0 ? 0 : (current + 1) % flatItems.length,
        );
        return;
      }
      if (event.key === 'ArrowUp') {
        event.preventDefault();
        setActiveIndex((current) =>
          flatItems.length === 0 ? 0 : (current - 1 + flatItems.length) % flatItems.length,
        );
        return;
      }
      if (event.key === 'Enter') {
        event.preventDefault();
        runItem(activeIndex);
      }
    },
    [activeIndex, close, flatItems.length, runItem],
  );

  const handlePaletteKeyDown = useCallback((event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== 'Tab') return;
    const focusable = Array.from(
      paletteRef.current?.querySelectorAll<HTMLElement>(
        'input:not([disabled]), button:not([disabled]), [tabindex]:not([tabindex="-1"])',
      ) ?? [],
    );
    if (focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }, []);

  // Keep the active row scrolled into view during keyboard nav.
  useEffect(() => {
    if (!open) return;
    const node = listRef.current?.querySelector<HTMLElement>('[data-active="true"]');
    node?.scrollIntoView({ block: 'nearest' });
  }, [activeIndex, open]);

  if (!mounted) return null;

  let runningIndex = -1;
  const renderRow = (
    key: string,
    icon: LucideIcon,
    title: ReactNode,
    meta: ReactNode,
    shortcut?: string,
  ) => {
    runningIndex += 1;
    const index = runningIndex;
    const Icon = icon;
    const active = index === activeIndex;
    return (
      <button
        key={key}
        type="button"
        role="option"
        aria-selected={active}
        data-active={active ? 'true' : undefined}
        className="desktop-command-palette-item"
        onMouseMove={() => setActiveIndex(index)}
        onClick={() => runItem(index)}
      >
        <Icon className="desktop-command-palette-item-icon h-4 w-4" aria-hidden />
        <span className="desktop-command-palette-item-title">{title}</span>
        {meta ? <span className="desktop-command-palette-item-meta">{meta}</span> : null}
        {shortcut ? <kbd className="desktop-command-palette-item-kbd">{shortcut}</kbd> : null}
      </button>
    );
  };

  return createPortal(
    <div
      className="desktop-command-palette-backdrop"
      data-state={closing ? 'closing' : 'open'}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) close();
      }}
    >
      <div
        ref={paletteRef}
        className="desktop-command-palette"
        data-state={closing ? 'closing' : 'open'}
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        onKeyDown={handlePaletteKeyDown}
      >
        <input
          ref={inputRef}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={handleInputKeyDown}
          placeholder="Search commands and conversations…"
          className="desktop-command-palette-input"
          spellCheck={false}
          autoComplete="off"
        />
        <div ref={listRef} className="desktop-command-palette-list" role="listbox">
          {flatItems.length === 0 ? (
            <div className="desktop-command-palette-empty">No matches</div>
          ) : (
            <>
              {filteredActions.length > 0 ? (
                <div className="desktop-command-palette-section">
                  <div className="desktop-command-palette-section-label">Actions</div>
                  {filteredActions.map((action) =>
                    renderRow(action.id, action.icon, action.title, action.meta, action.shortcut),
                  )}
                </div>
              ) : null}
              {filteredConversations.length > 0 ? (
                <div className="desktop-command-palette-section">
                  <div className="desktop-command-palette-section-label">Conversations</div>
                  {filteredConversations.map((conversation) =>
                    renderRow(
                      conversation.conversation_id,
                      MessageSquare,
                      conversation.title
                        ? truncate(conversation.title, 52)
                        : 'New conversation',
                      workspaceName(conversation.workspace_path),
                    ),
                  )}
                </div>
              ) : null}
            </>
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}
