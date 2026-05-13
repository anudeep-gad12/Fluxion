// Conversation list - grouped by workspace folder

import { useEffect, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent, ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { deleteConversation, listConversations } from '@/api/client';
import { useStore, useHasActiveRun } from '@/hooks/useStore';
import { Button } from '@/components/ui/button';
import { ConfirmDialog } from '@/components/ui/dialog';
import { WorkspacePickerDialog } from '@/components/WorkspacePickerDialog';
import { cn, formatRelativeTime, truncate } from '@/lib/utils';
import {
  CheckSquare,
  ChevronDown,
  ChevronRight,
  Plus,
  Square,
  Trash2,
  X,
} from 'lucide-react';
import type { Conversation } from '@/types';

function workspaceLabel(workspacePath: string): string {
  return workspacePath.split('/').filter(Boolean).pop() || workspacePath;
}

function workspacePathPreview(workspacePath: string): string {
  const normalized = workspacePath.trim();
  if (!normalized) return '';
  const parts = normalized.split('/').filter(Boolean);
  if (parts.length <= 3) {
    return normalized;
  }
  return `…/${parts.slice(-3).join('/')}`;
}

type WorkspaceGroup = {
  workspacePath: string;
  label: string;
  conversations: Conversation[];
  latestCreatedAt: string;
};

function ConversationCard({
  conversation,
  isSelected,
  isSelectMode,
  isChecked,
  onClick,
  onDelete,
  onToggleCheck,
}: {
  conversation: Conversation;
  isSelected: boolean;
  isSelectMode: boolean;
  isChecked: boolean;
  onClick: () => void;
  onDelete: () => void;
  onToggleCheck: () => void;
}) {
  return (
    <div
      className={cn(
        'ui-transition cursor-pointer rounded-[0.9rem] border border-zinc-800/90 bg-zinc-950/66 px-3.5 py-3.5',
        'min-h-[60px] sm:min-h-0',
        isSelected && 'border-cyan-500/35 bg-zinc-950/98 ring-1 ring-cyan-500/10',
        !isSelected && 'hover:border-zinc-700/95 hover:bg-zinc-950/82',
        isChecked && 'border-zinc-600/95 bg-zinc-950/90'
      )}
      onClick={isSelectMode ? onToggleCheck : onClick}
    >
      <div className="flex items-start justify-between gap-3">
        {isSelectMode && (
          <div className="pt-1.5">
            {isChecked ? (
              <CheckSquare className="h-5 w-5 sm:h-4 sm:w-4 text-zinc-400" />
            ) : (
              <Square className="h-5 w-5 sm:h-4 sm:w-4 text-zinc-400" />
            )}
          </div>
        )}
        <div className="min-w-0 flex-1">
          <p className={cn("truncate text-[13px] font-medium leading-6", isSelected ? 'text-zinc-50' : 'text-zinc-100')}>
            {conversation.title ? truncate(conversation.title, 50) : 'New conversation'}
          </p>
          <p className="mt-1 text-[11px] tracking-[0.01em] text-zinc-500">
            {formatRelativeTime(conversation.created_at)}
          </p>
        </div>
        {!isSelectMode && (
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 flex-shrink-0 rounded-xl text-zinc-500 hover:bg-zinc-900 hover:text-cyan-100"
            onClick={(e) => {
              e.stopPropagation();
              onDelete();
            }}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        )}
      </div>
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
    <div className="space-y-2.5">
      <div
        role="button"
        tabIndex={0}
        onClick={onToggle}
        onKeyDown={(event) => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            onToggle();
          }
        }}
        className="ui-transition group ui-panel block w-full rounded-[1rem] border border-zinc-800/90 px-3.5 py-3.5 text-left hover:border-cyan-500/25"
      >
        <div className="flex items-start gap-3.5">
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              onToggle();
            }}
            onMouseDown={(event) => event.stopPropagation()}
            className="ui-transition mt-0.5 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-xl border border-zinc-800 bg-zinc-950/95 text-zinc-400 hover:border-cyan-500/30 hover:text-cyan-100"
            title={isOpen ? 'Collapse workspace' : 'Expand workspace'}
          >
            {isOpen ? (
              <ChevronDown className="h-3.5 w-3.5" />
            ) : (
              <ChevronRight className="h-3.5 w-3.5" />
            )}
          </button>
          <div className="min-w-0 flex-1">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <button
                  type="button"
                  ref={headerButtonRef}
                  onClick={(event) => {
                    event.stopPropagation();
                    onToggle();
                  }}
                  onKeyDown={onHeaderKeyDown}
                  className="block min-w-0 text-left"
                  title={group.workspacePath}
                >
                  <div className="truncate pr-2 text-[14px] font-medium leading-6 tracking-[0.01em] text-zinc-50">
                    {group.label}
                  </div>
                </button>
                <div className="mt-1 truncate pr-2 font-mono text-[11px] leading-5 text-zinc-500">
                  {workspacePathPreview(group.workspacePath)}
                </div>
              </div>
              <div className="flex flex-shrink-0 items-center gap-2 pt-0.5">
                <span className="inline-flex h-6 min-w-6 items-center justify-center rounded-full border border-zinc-800 bg-zinc-950/95 px-1.5 text-[10px] text-zinc-400">
                  {group.conversations.length}
                </span>
                <Button
                  size="icon"
                  variant="ghost"
                  className="h-8 w-8 flex-shrink-0 rounded-xl text-zinc-500 hover:bg-zinc-900 hover:text-cyan-100"
                  onClick={(event) => {
                    event.stopPropagation();
                    onNewConversation();
                  }}
                  title="New conversation in this workspace"
                >
                  <Plus className="h-4 w-4" />
                </Button>
              </div>
            </div>
          </div>
        </div>
      </div>
      {isOpen && <div className="space-y-2 pl-4">{children}</div>}
    </div>
  );
}

export function ConversationList() {
  const navigate = useNavigate();
  const conversations = useStore((s) => s.conversations);
  const selectedConversationId = useStore((s) => s.selectedConversationId);
  const setConversations = useStore((s) => s.setConversations);
  const removeConversation = useStore((s) => s.removeConversation);
  const selectConversation = useStore((s) => s.selectConversation);
  const setDraftWorkspacePath = useStore((s) => s.setDraftWorkspacePath);
  const rememberWorkspacePath = useStore((s) => s.rememberWorkspacePath);
  const draftWorkspacePath = useStore((s) => s.draftWorkspacePath);
  const workspacePaths = useStore((s) => s.workspacePaths);
  const hasActiveRun = useHasActiveRun();
  const [isLoading, setIsLoading] = useState(false);
  const [workspacePickerOpen, setWorkspacePickerOpen] = useState(false);
  const [workspaceSectionsOpen, setWorkspaceSectionsOpen] = useState<Record<string, boolean>>({});
  const workspaceHeaderRefs = useRef<Record<string, HTMLButtonElement | null>>({});

  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [conversationToDelete, setConversationToDelete] = useState<string | null>(null);

  const [isSelectMode, setIsSelectMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [bulkDeleteModalOpen, setBulkDeleteModalOpen] = useState(false);

  useEffect(() => {
    async function fetchConversations() {
      setIsLoading(true);
      try {
        const data = await listConversations();
        const workspaceConversations = data.conversations.filter((conversation) =>
          Boolean(conversation.workspace_path?.trim())
        );
        setConversations(workspaceConversations);
      } catch (error) {
        console.error('Failed to fetch conversations:', error);
      } finally {
        setIsLoading(false);
      }
    }

    fetchConversations();
  }, [setConversations]);

  const workspaceGroups = useMemo(() => {
    const groups = new Map<string, WorkspaceGroup>();
    for (const workspacePath of workspacePaths) {
      const normalized = workspacePath.trim();
      if (!normalized || groups.has(normalized)) continue;
      groups.set(normalized, {
        workspacePath: normalized,
        label: workspaceLabel(normalized),
        conversations: [],
        latestCreatedAt: '',
      });
    }

    for (const conversation of conversations) {
      const workspacePath = conversation.workspace_path?.trim();
      if (!workspacePath) continue;
      const existing = groups.get(workspacePath);
      if (existing) {
        existing.conversations.push(conversation);
        if (conversation.created_at > existing.latestCreatedAt) {
          existing.latestCreatedAt = conversation.created_at;
        }
      } else {
        groups.set(workspacePath, {
          workspacePath,
          label: workspaceLabel(workspacePath),
          conversations: [conversation],
          latestCreatedAt: conversation.created_at,
        });
      }
    }

    return Array.from(groups.values())
      .map((group) => ({
        ...group,
        conversations: [...group.conversations].sort((a, b) => b.created_at.localeCompare(a.created_at)),
      }))
      .sort((a, b) => b.latestCreatedAt.localeCompare(a.latestCreatedAt));
  }, [conversations, workspacePaths]);

  useEffect(() => {
    setWorkspaceSectionsOpen((current) => {
      const next = { ...current };
      let changed = false;
      for (const group of workspaceGroups) {
        if (!(group.workspacePath in next)) {
          next[group.workspacePath] = false;
          changed = true;
        }
      }
      return changed ? next : current;
    });
  }, [workspaceGroups]);

  const startWorkspaceDraft = (workspacePath: string) => {
    if (hasActiveRun) return;
    selectConversation(null);
    rememberWorkspacePath(workspacePath);
    setDraftWorkspacePath(workspacePath);
    setWorkspaceSectionsOpen((current) => ({ ...current, [workspacePath]: true }));
    navigate('/conversations');
  };

  const handleDeleteClick = (conversationId: string) => {
    setConversationToDelete(conversationId);
    setDeleteModalOpen(true);
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
      startWorkspaceDraft(workspacePath);
    }
  };

  return (
    <div className="h-full flex flex-col">
      <div className="border-b border-zinc-900 px-3 py-3 sm:px-4">
        <div className="flex items-center justify-between gap-3">
          <div className="text-[11px] font-medium uppercase tracking-[0.14em] text-zinc-300">
            Workspaces
          </div>
          <div className="flex items-center gap-1">
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setAllWorkspaceSections(!allWorkspaceSectionsOpen)}
              disabled={workspaceGroups.length === 0}
              className="h-9 w-9 rounded-lg p-0 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100"
              title={allWorkspaceSectionsOpen ? 'Collapse all' : 'Expand all'}
            >
              {allWorkspaceSectionsOpen ? (
                <ChevronDown className="h-4 w-4" />
              ) : (
                <ChevronRight className="h-4 w-4" />
              )}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setWorkspacePickerOpen(true)}
              disabled={hasActiveRun}
              className="h-9 w-9 rounded-lg p-0 text-zinc-300 hover:bg-zinc-800 hover:text-zinc-100"
              title="Create workspace"
            >
              <Plus className="h-4 w-4" />
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
                className="h-9 rounded-lg px-2 text-zinc-300 hover:bg-zinc-800 hover:text-zinc-100 sm:h-8"
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
        <div className="flex items-center justify-between border-b border-zinc-600 bg-zinc-950/92 px-3 py-2 sm:px-4">
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

      <div className="flex-1 space-y-4 overflow-y-auto bg-[radial-gradient(circle_at_top,_rgba(255,255,255,0.03),_transparent_40%)] p-3 sm:p-4">
        {isLoading && conversations.length === 0 ? (
          <div className="text-sm text-muted-foreground">Loading conversations...</div>
        ) : workspaceGroups.length === 0 ? (
          <div className="rounded-xl border border-dashed border-zinc-600 bg-zinc-950/70 px-4 py-6 text-sm text-zinc-300">
            No workspaces yet.
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
                {group.conversations.length === 0 ? (
                  <button
                    onClick={() => startWorkspaceDraft(group.workspacePath)}
                    className="w-full rounded-xl border border-dashed border-zinc-600 bg-zinc-950/70 px-3 py-3 text-left text-xs text-zinc-300 transition-colors hover:border-zinc-600 hover:bg-zinc-950/72 hover:text-zinc-300"
                  >
                    New conversation
                  </button>
                ) : (
                  group.conversations.map((conversation) => (
                    <ConversationCard
                      key={conversation.conversation_id}
                      conversation={conversation}
                      isSelected={conversation.conversation_id === selectedConversationId}
                      isSelectMode={isSelectMode}
                      isChecked={selectedIds.has(conversation.conversation_id)}
                      onClick={() => navigate(`/conversations/${conversation.conversation_id}`)}
                      onDelete={() => handleDeleteClick(conversation.conversation_id)}
                      onToggleCheck={() => toggleCheck(conversation.conversation_id)}
                    />
                  ))
                )}
              </WorkspaceSection>
            ))}
          </>
        )}
      </div>

      <WorkspacePickerDialog
        open={workspacePickerOpen}
        onOpenChange={setWorkspacePickerOpen}
        value={draftWorkspacePath}
        onSelect={(workspacePath) => {
          selectConversation(null);
          rememberWorkspacePath(workspacePath);
          setDraftWorkspacePath(workspacePath);
          navigate('/conversations');
        }}
      />

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
