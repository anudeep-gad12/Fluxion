// Conversation list - grouped by workspace folder

import { useEffect, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent, MouseEvent as ReactMouseEvent, ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { deleteConversation, listConversations, patchConversation } from '@/api/client';
import { useStore, useHasActiveRun } from '@/hooks/useStore';
import { Button } from '@/components/ui/button';
import {
  ConfirmDialog,
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { WorkspacePickerDialog } from '@/components/WorkspacePickerDialog';
import { isLocalDesktopApp, openNativeWorkspacePicker } from '@/lib/platform';
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

type ThreadStatus = 'idle' | 'running' | 'failed';

function threadStatusForConversation(
  runs: Run[],
  streamingRunId: string | null
): ThreadStatus {
  if (streamingRunId && runs.some((run) => run.run_id === streamingRunId)) {
    return 'running';
  }
  if (runs.some((run) => run.status === 'running')) {
    return 'running';
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
  threadStatus,
  onClick,
  onContextMenu,
  onDelete,
  onToggleCheck,
}: {
  conversation: Conversation;
  isSelected: boolean;
  isSelectMode: boolean;
  isChecked: boolean;
  threadStatus: ThreadStatus;
  onClick: () => void;
  onContextMenu: (event: ReactMouseEvent<HTMLDivElement>) => void;
  onDelete: () => void;
  onToggleCheck: () => void;
}) {
  const pinned = isConversationPinned(conversation);

  return (
    <div
      className={cn(
        'desktop-list-item ui-transition group flex min-h-[36px] cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5',
        isSelected && 'desktop-list-item-selected',
        isChecked && !isSelected && 'bg-white/[0.05]'
      )}
      onClick={isSelectMode ? onToggleCheck : onClick}
      onContextMenu={isSelectMode ? undefined : onContextMenu}
    >
      {isSelectMode && (
        <div className="shrink-0">
          {isChecked ? (
            <CheckSquare className="h-4 w-4 text-zinc-400" />
          ) : (
            <Square className="h-4 w-4 text-zinc-500" />
          )}
        </div>
      )}
        <div className="min-w-0 flex-1">
          <p
            className={cn(
              'flex items-center gap-2 truncate text-[13px] leading-5',
              isSelected ? 'font-medium text-zinc-50' : 'text-zinc-300'
            )}
          >
            <span
              className={cn(
                'h-1.5 w-1.5 shrink-0 rounded-full',
                threadStatus === 'running' && 'bg-cyan-400 shadow-[0_0_6px_rgba(121,230,255,0.55)]',
                threadStatus === 'failed' && 'bg-red-400/90',
                threadStatus === 'idle' && 'bg-zinc-600'
              )}
              aria-hidden
            />
            <span className="truncate">
              {conversation.title ? truncate(conversation.title, 50) : 'New conversation'}
            </span>
            {pinned && (
              <Pin className="h-3 w-3 shrink-0 fill-zinc-500 text-zinc-500" aria-label="Pinned" />
            )}
          </p>
        <p className="truncate text-[11px] text-zinc-600">
          {formatRelativeTime(conversationActivityAt(conversation))}
        </p>
      </div>
      {!isSelectMode && (
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7 shrink-0 rounded-md text-zinc-600 opacity-0 hover:bg-white/[0.06] hover:text-zinc-300 group-hover:opacity-100"
          onClick={(e) => {
            e.stopPropagation();
            onDelete();
          }}
          aria-label="Delete conversation"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      )}
    </div>
  );
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
    <div className="space-y-0.5">
      <div className="flex items-center gap-1 px-1 py-1">
        <button
          type="button"
          onClick={onToggle}
          className="ui-transition flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-zinc-500 hover:bg-white/[0.06] hover:text-zinc-300"
          title={isOpen ? 'Collapse workspace' : 'Expand workspace'}
        >
          {isOpen ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
        </button>
        <button
          type="button"
          ref={headerButtonRef}
          onClick={onToggle}
          onKeyDown={onHeaderKeyDown}
          className="min-w-0 flex-1 truncate text-left text-[12px] font-semibold text-zinc-500"
          title={group.workspacePath || group.label}
        >
          {group.label}
        </button>
        <span className="shrink-0 text-[11px] tabular-nums text-zinc-600">
          {group.conversations.length}
        </span>
        {!group.isGeneral && (
          <Button
            size="icon"
            variant="ghost"
            className="h-6 w-6 shrink-0 rounded-md text-zinc-500 hover:text-zinc-300"
            onClick={onNewConversation}
            title="New conversation in this workspace"
          >
            <Plus className="h-3.5 w-3.5" />
          </Button>
        )}
      </div>
      {isOpen && <div className="space-y-0.5 pl-1">{children}</div>}
    </div>
  );
}

interface ConversationListProps {
  workspacePickerOpen?: boolean;
  onWorkspacePickerOpenChange?: (open: boolean) => void;
}

export function ConversationList({
  workspacePickerOpen: controlledPickerOpen,
  onWorkspacePickerOpenChange: setControlledPickerOpen,
}: ConversationListProps = {}) {
  const navigate = useNavigate();
  const conversations = useStore((s) => s.conversations);
  const runsByConversation = useStore((s) => s.runsByConversation);
  const streamingRunId = useStore((s) => s.streamingRunId);
  const selectedConversationId = useStore((s) => s.selectedConversationId);
  const setConversations = useStore((s) => s.setConversations);
  const updateConversation = useStore((s) => s.updateConversation);
  const removeConversation = useStore((s) => s.removeConversation);
  const setDraftWorkspacePath = useStore((s) => s.setDraftWorkspacePath);
  const bumpDraftConversation = useStore((s) => s.bumpDraftConversation);
  const rememberWorkspacePath = useStore((s) => s.rememberWorkspacePath);
  const draftWorkspacePath = useStore((s) => s.draftWorkspacePath);
  const hasActiveRun = useHasActiveRun();
  const [isLoading, setIsLoading] = useState(false);
  const [internalPickerOpen, setInternalPickerOpen] = useState(false);
  const pickerControlled = setControlledPickerOpen !== undefined;
  const workspacePickerOpen = controlledPickerOpen ?? internalPickerOpen;
  const setWorkspacePickerOpen = setControlledPickerOpen ?? setInternalPickerOpen;
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

    for (const conversation of conversations) {
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
  }, [conversations]);

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
    if (hasActiveRun) return;
    rememberWorkspacePath(workspacePath);
    setDraftWorkspacePath(workspacePath);
    bumpDraftConversation();
    setWorkspaceSectionsOpen((current) => ({ ...current, [workspacePath]: true }));
    navigate('/conversations');
  };

  const openWorkspacePicker = async () => {
    if (hasActiveRun) return;
    if (isLocalDesktopApp()) {
      const selectedPath = await openNativeWorkspacePicker();
      if (selectedPath) {
        startWorkspaceDraft(selectedPath);
      }
      return;
    }
    setWorkspacePickerOpen(true);
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
      <div className="border-b border-white/[0.06] px-2 py-2">
        <div className="flex items-center justify-between gap-2">
          <div className="text-[12px] font-semibold text-zinc-500">Workspaces</div>
          <div className="flex items-center gap-1">
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setAllWorkspaceSections(!allWorkspaceSectionsOpen)}
              disabled={workspaceGroups.length === 0}
              className="h-9 w-9 rounded-lg p-0 text-zinc-400 hover:bg-white/[0.055] hover:text-zinc-100"
              title={allWorkspaceSectionsOpen ? 'Collapse all' : 'Expand all'}
            >
              {allWorkspaceSectionsOpen ? (
                <ChevronDown className="h-4 w-4" />
              ) : (
                <ChevronRight className="h-4 w-4" />
              )}
            </Button>
            {isSelectMode && (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  if (selectedIds.size === conversations.length) {
                    setSelectedIds(new Set());
                  } else {
                    setSelectedIds(
                      new Set(
                        conversations.map((conversation) => conversation.conversation_id)
                      )
                    );
                  }
                }}
                title={selectedIds.size === conversations.length ? 'Deselect all' : 'Select all'}
                className="h-9 rounded-lg px-2 text-zinc-300 hover:bg-white/[0.055] hover:text-zinc-100 sm:h-8"
              >
                {selectedIds.size === conversations.length ? 'None' : 'All'}
              </Button>
            )}
            <Button
              size="sm"
              variant={isSelectMode ? 'secondary' : 'ghost'}
              onClick={toggleSelectMode}
              title={isSelectMode ? 'Cancel selection' : 'Select conversations'}
              className="h-9 w-9 rounded-lg sm:h-8 sm:w-8"
            >
              {isSelectMode ? <X className="h-4 w-4" /> : <CheckSquare className="h-4 w-4" />}
            </Button>
          </div>
        </div>
      </div>

      {isSelectMode && selectedIds.size > 0 && (
        <div className="flex items-center justify-between border-b border-white/10 bg-white/[0.035] px-3 py-2 sm:px-4">
          <span className="text-sm text-zinc-300">{selectedIds.size} selected</span>
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

      <div className="flex-1 space-y-3 overflow-y-auto p-2">
        {isLoading && conversations.length === 0 ? (
          <div className="text-sm text-muted-foreground">Loading conversations...</div>
        ) : workspaceGroups.length === 0 ? (
          <div className="space-y-3 rounded-[1rem] border border-dashed border-white/14 bg-white/[0.025] px-4 py-6 text-sm text-zinc-300">
            <div>No workspaces yet.</div>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => void openWorkspacePicker()}
              disabled={hasActiveRun}
              className="h-8 rounded-lg px-2 text-zinc-400 hover:bg-white/[0.055] hover:text-zinc-100"
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
                    threadStatus={threadStatusForConversation(
                      runsByConversation[conversation.conversation_id] ?? [],
                      streamingRunId
                    )}
                    onClick={() => navigate(`/conversations/${conversation.conversation_id}`)}
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

      {!pickerControlled && (
        <WorkspacePickerDialog
          open={workspacePickerOpen}
          onOpenChange={setWorkspacePickerOpen}
          value={draftWorkspacePath}
          onSelect={(workspacePath) => {
            rememberWorkspacePath(workspacePath);
            setDraftWorkspacePath(workspacePath);
            bumpDraftConversation();
            navigate('/conversations');
          }}
        />
      )}

      {contextMenu && (
        <div
          className="fixed z-[2147482100] w-52 rounded-xl border border-white/10 bg-zinc-950/98 p-1 shadow-2xl shadow-black/40 backdrop-blur"
          style={{ left: contextMenu.x, top: contextMenu.y }}
          onClick={(event) => event.stopPropagation()}
        >
          <button
            type="button"
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-[12px] text-zinc-300 hover:bg-white/[0.06] hover:text-zinc-50"
            onClick={() => openRenameDialog(contextMenu.conversation)}
          >
            <Pencil className="h-3.5 w-3.5" />
            Rename chat
          </button>
          <button
            type="button"
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-[12px] text-zinc-300 hover:bg-white/[0.06] hover:text-zinc-50"
            onClick={() => handleTogglePin(contextMenu.conversation)}
          >
            <Pin className="h-3.5 w-3.5" />
            {isConversationPinned(contextMenu.conversation) ? 'Unpin chat' : 'Pin chat'}
          </button>
          <button
            type="button"
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-[12px] text-zinc-300 hover:bg-white/[0.06] hover:text-zinc-50"
            onClick={() => handleCopySessionId(contextMenu.conversation)}
          >
            <Copy className="h-3.5 w-3.5" />
            Copy session-id
          </button>
          <div className="my-1 border-t border-white/10" />
          <button
            type="button"
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-[12px] text-red-300 hover:bg-red-500/[0.10] hover:text-red-200"
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
            className="w-full rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2 text-sm text-zinc-100 outline-none placeholder:text-zinc-600 focus:border-cyan-300/35"
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
