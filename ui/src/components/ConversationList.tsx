// Conversation list - grouped by workspace folder

import { useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
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
  FolderCode,
  Plus,
  Square,
  Trash2,
  X,
} from 'lucide-react';
import type { Conversation } from '@/types';

function workspaceLabel(workspacePath: string): string {
  return workspacePath.split('/').filter(Boolean).pop() || workspacePath;
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
        'rounded-none border px-3 py-3 sm:py-2 cursor-pointer transition-colors',
        'min-h-[60px] sm:min-h-0',
        isSelected ? 'border-zinc-400 bg-zinc-900' : 'hover:bg-zinc-800',
        isChecked && 'bg-zinc-800 border-zinc-500'
      )}
      onClick={isSelectMode ? onToggleCheck : onClick}
    >
      <div className="flex items-start justify-between gap-3">
        {isSelectMode && (
          <div className="pt-1">
            {isChecked ? (
              <CheckSquare className="h-5 w-5 sm:h-4 sm:w-4 text-zinc-400" />
            ) : (
              <Square className="h-5 w-5 sm:h-4 sm:w-4 text-zinc-600" />
            )}
          </div>
        )}
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium truncate">
            {conversation.title ? truncate(conversation.title, 50) : 'New conversation'}
          </p>
          <p className="text-xs text-muted-foreground mt-1">
            {formatRelativeTime(conversation.created_at)}
          </p>
        </div>
        {!isSelectMode && (
          <Button
            variant="ghost"
            size="icon"
            className="h-9 w-9 sm:h-8 sm:w-8 flex-shrink-0"
            onClick={(e) => {
              e.stopPropagation();
              onDelete();
            }}
          >
            <Trash2 className="h-4 w-4 text-zinc-500 hover:text-zinc-200" />
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
  children,
}: {
  group: WorkspaceGroup;
  isOpen: boolean;
  onToggle: () => void;
  onNewConversation: () => void;
  children: ReactNode;
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 rounded-none border border-zinc-900 bg-zinc-950/60 px-2 py-2">
        <button
          onClick={onToggle}
          className="flex min-w-0 flex-1 items-center gap-2 text-left"
        >
          {isOpen ? (
            <ChevronDown className="h-4 w-4 text-zinc-600" />
          ) : (
            <ChevronRight className="h-4 w-4 text-zinc-600" />
          )}
          <FolderCode className="h-4 w-4 text-zinc-400" />
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm text-zinc-200">{group.label}</div>
            <div className="truncate text-[10px] text-zinc-600">{group.workspacePath}</div>
          </div>
          <span className="text-[10px] text-zinc-600">{group.conversations.length}</span>
        </button>
        <Button
          size="icon"
          variant="ghost"
          className="h-8 w-8 flex-shrink-0"
          onClick={onNewConversation}
          title="New conversation in this workspace"
        >
          <Plus className="h-4 w-4" />
        </Button>
      </div>
      {isOpen && <div className="space-y-2 pl-3">{children}</div>}
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
        const generalConversationIds = data.conversations
          .filter((conversation) => !conversation.workspace_path?.trim())
          .map((conversation) => conversation.conversation_id);
        setConversations(workspaceConversations);
        if (generalConversationIds.length > 0) {
          await Promise.allSettled(generalConversationIds.map((conversationId) => deleteConversation(conversationId)));
        }
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
          next[group.workspacePath] = true;
          changed = true;
        }
      }
      if (selectedConversationId) {
        const activeGroup = workspaceGroups.find((group) =>
          group.conversations.some((conversation) => conversation.conversation_id === selectedConversationId)
        );
        if (activeGroup && !next[activeGroup.workspacePath]) {
          next[activeGroup.workspacePath] = true;
          changed = true;
        }
      }
      return changed ? next : current;
    });
  }, [selectedConversationId, workspaceGroups]);

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

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center justify-between px-3 sm:px-4 py-3 border-b">
        <div className="flex items-center gap-3 min-w-0">
          <h2 className="font-semibold text-sm text-zinc-100">Create workspace</h2>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setWorkspacePickerOpen(true)}
            disabled={hasActiveRun}
            className="h-8 w-8 p-0"
            title="Create workspace"
          >
            <Plus className="h-4 w-4" />
          </Button>
        </div>
        <div className="flex items-center gap-1">
          {isSelectMode && (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                if (selectedIds.size === conversations.length) {
                  setSelectedIds(new Set());
                } else {
                  setSelectedIds(new Set(conversations.map((conversation) => conversation.conversation_id)));
                }
              }}
              title={selectedIds.size === conversations.length ? 'Deselect all' : 'Select all'}
              className="h-9 sm:h-8"
            >
              {selectedIds.size === conversations.length ? 'None' : 'All'}
            </Button>
          )}
          <Button
            size="sm"
            variant={isSelectMode ? 'secondary' : 'ghost'}
            onClick={toggleSelectMode}
            title={isSelectMode ? 'Cancel selection' : 'Select conversations'}
            className="h-9 w-9 sm:h-8 sm:w-8"
          >
            {isSelectMode ? <X className="h-4 w-4" /> : <CheckSquare className="h-4 w-4" />}
          </Button>
        </div>
      </div>

      {isSelectMode && selectedIds.size > 0 && (
        <div className="px-3 sm:px-4 py-2 bg-zinc-800 border-b flex items-center justify-between">
          <span className="text-sm text-zinc-300">{selectedIds.size} selected</span>
          <Button
            size="sm"
            variant="destructive"
            onClick={() => setBulkDeleteModalOpen(true)}
            className="h-9 sm:h-8"
          >
            <Trash2 className="h-4 w-4" />
            Delete
          </Button>
        </div>
      )}

      <div className="flex-1 overflow-y-auto p-3 sm:p-4 space-y-4">
        {isLoading && conversations.length === 0 ? (
          <div className="text-sm text-muted-foreground">Loading conversations...</div>
        ) : workspaceGroups.length === 0 ? (
          <div className="text-sm text-muted-foreground">No workspaces yet.</div>
        ) : (
          <>
            {workspaceGroups.map((group) => (
              <WorkspaceSection
                key={group.workspacePath}
                group={group}
                isOpen={workspaceSectionsOpen[group.workspacePath] ?? true}
                onToggle={() => setWorkspaceSectionsOpen((current) => ({
                  ...current,
                  [group.workspacePath]: !(current[group.workspacePath] ?? true),
                }))}
                onNewConversation={() => startWorkspaceDraft(group.workspacePath)}
              >
                {group.conversations.length === 0 ? (
                  <button
                    onClick={() => startWorkspaceDraft(group.workspacePath)}
                    className="w-full border border-dashed border-zinc-800 px-3 py-3 text-left text-xs text-zinc-500 hover:border-zinc-700 hover:text-zinc-300"
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
