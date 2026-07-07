// Conversation list - grouped by workspace folder

import { useEffect, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent, MouseEvent as ReactMouseEvent, ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { withViewTransition } from '@/lib/viewTransition';
import { deleteConversation, listConversations, patchConversation } from '@/api/client';
import { useStore, conversationAttention } from '@/hooks/useStore';
import type { AgentUIState } from '@/types/agent';
import { Button } from '@/components/ui/button';
import { Tooltip } from '@/components/ui/tooltip';
import {
  ConfirmDialog,
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { openNativeWorkspacePicker } from '@/lib/platform';
import { cn, formatRelativeTime, truncate } from '@/lib/utils';
import {
  CheckSquare,
  ChevronDown,
  ChevronRight,
  Copy,
  Pencil,
  Pin,
  Plus,
  Square,
  Trash2,
  X,
} from 'lucide-react';
import type { Conversation, Run } from '@/types';
import { toast } from 'sonner';

type ThreadStatus = 'idle' | 'running' | 'needs-attention' | 'failed';

function threadStatusForConversation(
  runs: Run[],
  streamingRunId: string | null,
  agentRunState: Record<string, AgentUIState>,
  attention: ReturnType<typeof conversationAttention>,
): ThreadStatus {
  if (attention) {
    return 'needs-attention';
  }
  if (streamingRunId && runs.some((run) => run.run_id === streamingRunId)) {
    return 'running';
  }
  // Live agent state wins over run.status, which can be stale for
  // backgrounded runs until their SSE stream delivers the terminal event.
  for (const run of runs) {
    const live = agentRunState[run.run_id];
    if (live ? live.isActive : run.status === 'running') {
      return 'running';
    }
  }
  const latest = runs[0];
  if (latest?.status === 'failed') {
    return 'failed';
  }
  return 'idle';
}

function workspaceLabel(workspacePath: string): string {
  return workspacePath.split('/').filter(Boolean).pop() || workspacePath;
}

function conversationActivityAt(conversation: Conversation): string {
  return conversation.updated_at || conversation.created_at;
}

function isConversationPinned(conversation: Conversation): boolean {
  return Boolean(conversation.metadata?.pinned_at);
}

function isHiddenConversation(conversation: Conversation): boolean {
  return conversation.metadata?.hidden === true
    || conversation.metadata?.hide_from_sidebar === true;
}

type WorkspaceGroup = {
  workspacePath: string;
  label: string;
  conversations: Conversation[];
  latestCreatedAt: string;
  isGeneral?: boolean;
};

function ConversationCard({
  conversation,
  isSelected,
  isSelectMode,
  isChecked,
  onClick,
  onContextMenu,
  onDelete,
  onToggleCheck,
}: {
  conversation: Conversation;
  isSelected: boolean;
  isSelectMode: boolean;
  isChecked: boolean;
  onClick: () => void;
  onContextMenu: (event: ReactMouseEvent<HTMLDivElement>) => void;
  onDelete: () => void;
  onToggleCheck: () => void;
}) {
  const pinned = isConversationPinned(conversation);

  return (
    <div
      className={cn(
        'desktop-conversation-row',
        isSelected && 'is-selected',
        isChecked && !isSelected && 'is-checked'
      )}
      onClick={isSelectMode ? onToggleCheck : onClick}
      onContextMenu={isSelectMode ? undefined : onContextMenu}
      title={formatRelativeTime(conversationActivityAt(conversation))}
    >
      {isSelectMode && (
        <div className="shrink-0">
          {isChecked ? (
            <CheckSquare className="h-4 w-4 text-[var(--desktop-text-secondary)]" />
          ) : (
            <Square className="h-4 w-4 text-[var(--desktop-text-tertiary)]" />
          )}
        </div>
      )}
      <ConversationStatusDot conversationId={conversation.conversation_id} />
      <span
        className={cn(
          'desktop-conversation-title',
          isSelected && 'is-selected'
        )}
      >
        {conversation.title ? truncate(conversation.title, 50) : 'New conversation'}
      </span>
      {pinned && (
        <Pin className="desktop-conversation-pin" aria-label="Pinned" />
      )}
      {!isSelectMode && (
        <button
          type="button"
          className="desktop-conversation-delete"
          onClick={(e) => {
            e.stopPropagation();
            onDelete();
          }}
          aria-label="Delete conversation"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  );
}

function useConversationThreadStatus(conversationId: string): ThreadStatus {
  return useStore((state) =>
    threadStatusForConversation(
      state.runsByConversation[conversationId] ?? [],
      state.streamingRunId,
      state.agentRunState,
      conversationAttention(state, conversationId),
    )
  );
}

function ConversationStatusDot({ conversationId }: { conversationId: string }) {
  const threadStatus = useConversationThreadStatus(conversationId);
  const dot = (
    <span
      className="desktop-conversation-status"
      data-status={threadStatus}
      aria-label={threadStatus === 'needs-attention' ? 'Waiting for your approval' : undefined}
      aria-hidden={threadStatus !== 'needs-attention'}
    />
  );

  if (threadStatus === 'needs-attention') {
    return <Tooltip content="Waiting for your approval">{dot}</Tooltip>;
  }

  return dot;
}

function WorkspaceSection({
  group,
  isOpen,
  onToggle,
  onNewConversation,
  headerButtonRef,
  onHeaderKeyDown,
  children,
}: {
  group: WorkspaceGroup;
  isOpen: boolean;
  onToggle: () => void;
  onNewConversation: () => void;
  headerButtonRef?: (node: HTMLButtonElement | null) => void;
  onHeaderKeyDown?: (event: ReactKeyboardEvent<HTMLButtonElement>) => void;
  children: ReactNode;
}) {
  return (
    <div className="desktop-workspace-section">
      <div className="desktop-workspace-header">
        <Tooltip content={isOpen ? 'Collapse workspace' : 'Expand workspace'}>
          <button
            type="button"
            onClick={onToggle}
            className="desktop-workspace-disclosure"
            aria-label={isOpen ? 'Collapse workspace' : 'Expand workspace'}
          >
            {isOpen ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
          </button>
        </Tooltip>
        <button
          type="button"
          ref={headerButtonRef}
          onClick={onToggle}
          onKeyDown={onHeaderKeyDown}
          className="desktop-workspace-title"
          title={group.workspacePath || group.label}
        >
          {group.label}
        </button>
        <span className="desktop-workspace-count">
          {group.conversations.length}
        </span>
        {!group.isGeneral && (
          <Tooltip content="New conversation in this workspace">
            <Button
              size="icon"
              variant="ghost"
              className="desktop-workspace-add"
              onClick={onNewConversation}
              aria-label="New conversation in this workspace"
            >
              <Plus className="h-3 w-3" />
            </Button>
          </Tooltip>
        )}
      </div>
      {isOpen && <div className="desktop-workspace-list">{children}</div>}
    </div>
  );
}

export function ConversationList() {
  const navigate = useNavigate();
  const conversations = useStore((s) => s.conversations);
  const selectedConversationId = useStore((s) => s.selectedConversationId);
  const setConversations = useStore((s) => s.setConversations);
  const updateConversation = useStore((s) => s.updateConversation);
  const removeConversation = useStore((s) => s.removeConversation);
  const beginWorkspaceDraft = useStore((s) => s.beginWorkspaceDraft);
  const [isLoading, setIsLoading] = useState(true);
  const [workspaceSectionsOpen, setWorkspaceSectionsOpen] = useState<Record<string, boolean>>({});
  const workspaceHeaderRefs = useRef<Record<string, HTMLButtonElement | null>>({});

  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [conversationToDelete, setConversationToDelete] = useState<string | null>(null);
  const [renameModalOpen, setRenameModalOpen] = useState(false);
  const [conversationToRename, setConversationToRename] = useState<Conversation | null>(null);
  const [renameTitle, setRenameTitle] = useState('');
  const [contextMenu, setContextMenu] = useState<{
    conversation: Conversation;
    x: number;
    y: number;
  } | null>(null);

  const [isSelectMode, setIsSelectMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [bulkDeleteModalOpen, setBulkDeleteModalOpen] = useState(false);
  const visibleConversations = useMemo(
    () => conversations.filter((conversation) => !isHiddenConversation(conversation)),
    [conversations]
  );

  useEffect(() => {
    async function fetchConversations() {
      setIsLoading(true);
      try {
        const data = await listConversations(undefined, 100);
        setConversations(data.conversations);
      } catch (error) {
        console.error('Failed to fetch conversations:', error);
      } finally {
        setIsLoading(false);
      }
    }

    fetchConversations();
  }, [setConversations]);

  useEffect(() => {
    if (!contextMenu) return;

    const close = () => setContextMenu(null);
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') close();
    };

    window.addEventListener('click', close);
    window.addEventListener('scroll', close, true);
    window.addEventListener('keydown', onKeyDown);
    return () => {
      window.removeEventListener('click', close);
      window.removeEventListener('scroll', close, true);
      window.removeEventListener('keydown', onKeyDown);
    };
  }, [contextMenu]);

  const workspaceGroups = useMemo(() => {
    const groups = new Map<string, WorkspaceGroup>();
    const generalConversations: Conversation[] = [];

    for (const conversation of visibleConversations) {
      const workspacePath = conversation.workspace_path?.trim();
      if (!workspacePath) {
        generalConversations.push(conversation);
        continue;
      }
      const existing = groups.get(workspacePath);
      if (existing) {
        existing.conversations.push(conversation);
        const activityAt = conversationActivityAt(conversation);
        if (activityAt > existing.latestCreatedAt) {
          existing.latestCreatedAt = activityAt;
        }
      } else {
        groups.set(workspacePath, {
          workspacePath,
          label: workspaceLabel(workspacePath),
          conversations: [conversation],
          latestCreatedAt: conversationActivityAt(conversation),
        });
      }
    }

    if (generalConversations.length > 0) {
      groups.set('__general__', {
        workspacePath: '',
        label: 'General',
        conversations: generalConversations,
        latestCreatedAt: generalConversations.reduce(
          (latest, conversation) => {
            const activityAt = conversationActivityAt(conversation);
            return activityAt > latest ? activityAt : latest;
          },
          ''
        ),
        isGeneral: true,
      });
    }

    return Array.from(groups.values())
      .map((group) => ({
        ...group,
        conversations: [...group.conversations].sort((a, b) => {
          const pinnedDelta = Number(isConversationPinned(b)) - Number(isConversationPinned(a));
          if (pinnedDelta !== 0) return pinnedDelta;
          return conversationActivityAt(b).localeCompare(conversationActivityAt(a));
        }),
      }))
      .sort((a, b) => b.latestCreatedAt.localeCompare(a.latestCreatedAt));
  }, [visibleConversations]);

  useEffect(() => {
    setWorkspaceSectionsOpen((current) => {
      const next = { ...current };
      let changed = false;
      for (const group of workspaceGroups) {
        if (!(group.workspacePath in next)) {
          next[group.workspacePath] = group.conversations.length > 0;
          changed = true;
        }
      }
      return changed ? next : current;
    });
  }, [workspaceGroups]);

  const startWorkspaceDraft = (workspacePath: string) => {
    const normalized = workspacePath.trim();
    if (!normalized) return;
    beginWorkspaceDraft(normalized);
    navigate('/conversations', { replace: true });
    setWorkspaceSectionsOpen((current) => ({ ...current, [normalized]: true }));
  };

  const openWorkspacePicker = async () => {
    const selectedPath = await openNativeWorkspacePicker();
    if (selectedPath) {
      startWorkspaceDraft(selectedPath);
    }
  };

  const handleDeleteClick = (conversationId: string) => {
    setContextMenu(null);
    setConversationToDelete(conversationId);
    setDeleteModalOpen(true);
  };

  const handleConversationContextMenu = (
    event: ReactMouseEvent<HTMLDivElement>,
    conversation: Conversation,
  ) => {
    event.preventDefault();
    event.stopPropagation();
    setContextMenu({
      conversation,
      x: Math.min(event.clientX, window.innerWidth - 210),
      y: Math.min(event.clientY, window.innerHeight - 180),
    });
  };

  const openRenameDialog = (conversation: Conversation) => {
    setContextMenu(null);
    setConversationToRename(conversation);
    setRenameTitle(conversation.title || '');
    setRenameModalOpen(true);
  };

  const handleRenameConversation = async () => {
    if (!conversationToRename) return;
    const nextTitle = renameTitle.trim() || 'New conversation';
    try {
      const updated = await patchConversation(conversationToRename.conversation_id, {
        title: nextTitle,
      });
      updateConversation(conversationToRename.conversation_id, updated);
      setRenameModalOpen(false);
      setConversationToRename(null);
    } catch (error) {
      console.error('Failed to rename conversation:', error);
      toast.error('Failed to rename chat');
    }
  };

  const handleCopySessionId = async (conversation: Conversation) => {
    setContextMenu(null);
    try {
      await navigator.clipboard.writeText(conversation.conversation_id);
      toast.success('session-id copied');
    } catch {
      toast.error('copy failed');
    }
  };

  const handleTogglePin = async (conversation: Conversation) => {
    setContextMenu(null);
    const nextPinnedAt = isConversationPinned(conversation) ? null : new Date().toISOString();
    try {
      const updated = await patchConversation(conversation.conversation_id, {
        metadata: { pinned_at: nextPinnedAt },
      });
      updateConversation(conversation.conversation_id, updated);
    } catch (error) {
      console.error('Failed to update pinned state:', error);
      toast.error('Failed to update pinned chat');
    }
  };

  const handleConfirmDelete = async () => {
    if (!conversationToDelete) return;
    const wasSelected = conversationToDelete === selectedConversationId;
    try {
      await deleteConversation(conversationToDelete);
      removeConversation(conversationToDelete);
      if (wasSelected) {
        navigate('/conversations');
      }
    } catch (error) {
      console.error('Failed to delete conversation:', error);
    }
    setConversationToDelete(null);
  };

  const toggleSelectMode = () => {
    setIsSelectMode(!isSelectMode);
    setSelectedIds(new Set());
  };

  const toggleCheck = (id: string) => {
    const newSet = new Set(selectedIds);
    if (newSet.has(id)) {
      newSet.delete(id);
    } else {
      newSet.add(id);
    }
    setSelectedIds(newSet);
  };

  const handleBulkDelete = async () => {
    for (const id of selectedIds) {
      try {
        await deleteConversation(id);
        removeConversation(id);
      } catch (error) {
        console.error('Failed to delete:', error);
      }
    }
    setSelectedIds(new Set());
    setIsSelectMode(false);
  };

  const allWorkspaceSectionsOpen = useMemo(
    () =>
      workspaceGroups.length > 0
      && workspaceGroups.every((group) => workspaceSectionsOpen[group.workspacePath] ?? false),
    [workspaceGroups, workspaceSectionsOpen]
  );

  const setAllWorkspaceSections = (isOpen: boolean) => {
    setWorkspaceSectionsOpen(
      Object.fromEntries(
        workspaceGroups.map((group) => [group.workspacePath, isOpen])
      )
    );
  };

  const focusWorkspaceHeader = (workspacePath: string) => {
    workspaceHeaderRefs.current[workspacePath]?.focus();
  };

  const handleWorkspaceHeaderKeyDown = (
    event: ReactKeyboardEvent<HTMLButtonElement>,
    workspacePath: string,
  ) => {
    const currentIndex = workspaceGroups.findIndex((group) => group.workspacePath === workspacePath);
    if (currentIndex === -1) return;

    if (event.key === 'ArrowDown') {
      event.preventDefault();
      const nextGroup = workspaceGroups[Math.min(currentIndex + 1, workspaceGroups.length - 1)];
      if (nextGroup) {
        focusWorkspaceHeader(nextGroup.workspacePath);
      }
      return;
    }

    if (event.key === 'ArrowUp') {
      event.preventDefault();
      const previousGroup = workspaceGroups[Math.max(currentIndex - 1, 0)];
      if (previousGroup) {
        focusWorkspaceHeader(previousGroup.workspacePath);
      }
      return;
    }

    if (!event.metaKey && !event.ctrlKey && !event.altKey && !event.shiftKey && event.key.toLowerCase() === 'n') {
      event.preventDefault();
      if (!workspacePath) return;
      startWorkspaceDraft(workspacePath);
    }
  };

  return (
    <div className="h-full flex flex-col">
      <div className="border-b border-[var(--desktop-border-subtle)] px-2 py-1.5">
        <div className="flex items-center justify-between gap-2">
          <div className="px-1 text-[11px] font-medium uppercase tracking-[0.08em] text-[var(--desktop-text-tertiary)]">Workspaces</div>
          <div className="flex items-center gap-0.5">
            <Tooltip content={allWorkspaceSectionsOpen ? 'Collapse all' : 'Expand all'}>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setAllWorkspaceSections(!allWorkspaceSectionsOpen)}
                disabled={workspaceGroups.length === 0}
                className="h-7 w-7 rounded-md p-0 text-[var(--desktop-text-tertiary)] hover:bg-[var(--desktop-hover)] hover:text-[var(--desktop-text-primary)]"
                aria-label={allWorkspaceSectionsOpen ? 'Collapse all' : 'Expand all'}
              >
                {allWorkspaceSectionsOpen ? (
                  <ChevronDown className="h-3.5 w-3.5" />
                ) : (
                  <ChevronRight className="h-3.5 w-3.5" />
                )}
              </Button>
            </Tooltip>
            {isSelectMode && (
              <Tooltip content={selectedIds.size === visibleConversations.length ? 'Deselect all' : 'Select all'}>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    if (selectedIds.size === visibleConversations.length) {
                      setSelectedIds(new Set());
                    } else {
                      setSelectedIds(
                        new Set(
                          visibleConversations.map((conversation) => conversation.conversation_id)
                        )
                      );
                    }
                  }}
                  className="h-7 rounded-md px-2 text-[var(--desktop-text-secondary)] hover:bg-[var(--desktop-hover)] hover:text-[var(--desktop-text-primary)]"
                >
                  {selectedIds.size === visibleConversations.length ? 'None' : 'All'}
                </Button>
              </Tooltip>
            )}
            <Tooltip content={isSelectMode ? 'Cancel selection' : 'Select conversations'}>
              <Button
                size="sm"
                variant={isSelectMode ? 'secondary' : 'ghost'}
                onClick={toggleSelectMode}
                aria-label={isSelectMode ? 'Cancel selection' : 'Select conversations'}
                className="h-7 w-7 rounded-md"
              >
                {isSelectMode ? <X className="h-3.5 w-3.5" /> : <CheckSquare className="h-3.5 w-3.5" />}
              </Button>
            </Tooltip>
          </div>
        </div>
      </div>

      {isSelectMode && selectedIds.size > 0 && (
        <div className="flex items-center justify-between border-b border-[var(--desktop-border-strong)] bg-[var(--desktop-hover)] px-3 py-2 sm:px-4">
          <span className="text-sm text-[var(--desktop-text-secondary)]">{selectedIds.size} selected</span>
          <Button
            size="sm"
            variant="destructive"
            onClick={() => setBulkDeleteModalOpen(true)}
            className="h-9 rounded-lg sm:h-8"
          >
            <Trash2 className="h-4 w-4" />
            Delete
          </Button>
        </div>
      )}

      <div className="flex-1 space-y-2 overflow-y-auto p-2">
        {isLoading && visibleConversations.length === 0 ? (
          <div className="space-y-3 p-1" aria-label="Loading conversations" aria-busy="true">
            {Array.from({ length: 3 }).map((_, groupIndex) => (
              <div key={groupIndex} className="space-y-2">
                <div className="ui-skeleton h-3.5 w-24 rounded-md" />
                <div className="ui-skeleton h-8 w-full rounded-lg" />
                <div className="ui-skeleton h-8 w-[85%] rounded-lg" />
              </div>
            ))}
          </div>
        ) : workspaceGroups.length === 0 ? (
          <div className="space-y-3 rounded-xl border border-dashed border-[var(--desktop-border-strong)] bg-[var(--desktop-hover)] px-4 py-6 text-sm text-[var(--desktop-text-secondary)]">
            <div>No workspaces yet.</div>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => void openWorkspacePicker()}
              className="h-8 rounded-lg px-2 text-[var(--desktop-text-secondary)] hover:bg-[var(--desktop-hover)] hover:text-[var(--desktop-text-primary)]"
            >
              <Plus className="h-3.5 w-3.5" />
              Add workspace
            </Button>
          </div>
        ) : (
          <>
            {workspaceGroups.map((group) => (
              <WorkspaceSection
                key={group.workspacePath}
                group={group}
                isOpen={workspaceSectionsOpen[group.workspacePath] ?? false}
                onToggle={() => setWorkspaceSectionsOpen((current) => ({
                  ...current,
                  [group.workspacePath]: !(current[group.workspacePath] ?? false),
                }))}
                onNewConversation={() => startWorkspaceDraft(group.workspacePath)}
                headerButtonRef={(node) => {
                  workspaceHeaderRefs.current[group.workspacePath] = node;
                }}
                onHeaderKeyDown={(event) => handleWorkspaceHeaderKeyDown(event, group.workspacePath)}
              >
                {group.conversations.map((conversation) => (
                  <ConversationCard
                    key={conversation.conversation_id}
                    conversation={conversation}
                    isSelected={conversation.conversation_id === selectedConversationId}
                    isSelectMode={isSelectMode}
                    isChecked={selectedIds.has(conversation.conversation_id)}
                    onClick={() =>
                      withViewTransition(() =>
                        navigate(`/conversations/${conversation.conversation_id}`)
                      )
                    }
                    onContextMenu={(event) => handleConversationContextMenu(event, conversation)}
                    onDelete={() => handleDeleteClick(conversation.conversation_id)}
                    onToggleCheck={() => toggleCheck(conversation.conversation_id)}
                  />
                ))}
              </WorkspaceSection>
            ))}
          </>
        )}
      </div>

      {contextMenu && (
        <div
          className="fixed z-[var(--z-context)] w-52 rounded-xl border border-[var(--desktop-border-strong)] bg-[var(--desktop-panel-overlay)] p-1 shadow-[var(--shadow-menu)] backdrop-blur"
          style={{ left: contextMenu.x, top: contextMenu.y }}
          onClick={(event) => event.stopPropagation()}
        >
          <button
            type="button"
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-xs text-[var(--desktop-text-secondary)] hover:bg-[var(--desktop-hover)] hover:text-[var(--desktop-text-primary)]"
            onClick={() => openRenameDialog(contextMenu.conversation)}
          >
            <Pencil className="h-3.5 w-3.5" />
            Rename chat
          </button>
          <button
            type="button"
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-xs text-[var(--desktop-text-secondary)] hover:bg-[var(--desktop-hover)] hover:text-[var(--desktop-text-primary)]"
            onClick={() => handleTogglePin(contextMenu.conversation)}
          >
            <Pin className="h-3.5 w-3.5" />
            {isConversationPinned(contextMenu.conversation) ? 'Unpin chat' : 'Pin chat'}
          </button>
          <button
            type="button"
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-xs text-[var(--desktop-text-secondary)] hover:bg-[var(--desktop-hover)] hover:text-[var(--desktop-text-primary)]"
            onClick={() => handleCopySessionId(contextMenu.conversation)}
          >
            <Copy className="h-3.5 w-3.5" />
            Copy session-id
          </button>
          <div className="my-1 border-t border-[var(--desktop-border-strong)]" />
          <button
            type="button"
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-xs text-[var(--desktop-danger)] hover:bg-[var(--desktop-danger-hover)] hover:text-[var(--desktop-danger-text)]"
            onClick={() => handleDeleteClick(contextMenu.conversation.conversation_id)}
          >
            <Trash2 className="h-3.5 w-3.5" />
            Delete chat
          </button>
        </div>
      )}

      <Dialog
        open={renameModalOpen}
        onOpenChange={(open) => {
          setRenameModalOpen(open);
          if (!open) setConversationToRename(null);
        }}
      >
        <DialogHeader>
          <DialogTitle>Rename chat</DialogTitle>
        </DialogHeader>
        <DialogContent>
          <input
            autoFocus
            value={renameTitle}
            onChange={(event) => setRenameTitle(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault();
                void handleRenameConversation();
              }
            }}
            className="w-full rounded-xl border border-[var(--desktop-border-strong)] bg-[var(--desktop-hover)] px-3 py-2 text-sm text-[var(--desktop-text-primary)] outline-none placeholder:text-[var(--desktop-text-tertiary)] focus:border-[rgb(var(--desktop-accent-rgb)/0.35)]"
            placeholder="Chat title"
          />
        </DialogContent>
        <DialogFooter>
          <Button
            variant="ghost"
            onClick={() => setRenameModalOpen(false)}
          >
            Cancel
          </Button>
          <Button onClick={() => void handleRenameConversation()}>
            Rename
          </Button>
        </DialogFooter>
      </Dialog>

      <ConfirmDialog
        open={deleteModalOpen}
        onOpenChange={setDeleteModalOpen}
        title="Delete Conversation"
        description="This will permanently delete this conversation and all its messages. This action cannot be undone."
        confirmLabel="Delete"
        cancelLabel="Cancel"
        onConfirm={handleConfirmDelete}
        variant="destructive"
      />

      <ConfirmDialog
        open={bulkDeleteModalOpen}
        onOpenChange={setBulkDeleteModalOpen}
        title={`Delete ${selectedIds.size} Conversations`}
        description={`This will permanently delete ${selectedIds.size} conversation(s) and all their messages. This action cannot be undone.`}
        confirmLabel="Delete All"
        cancelLabel="Cancel"
        onConfirm={handleBulkDelete}
        variant="destructive"
      />
    </div>
  );
}
