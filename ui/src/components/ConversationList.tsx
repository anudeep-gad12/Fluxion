// Conversation list - shows chats in the sidebar with multi-select

import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { listConversations, deleteConversation } from '@/api/client';
import { useStore } from '@/hooks/useStore';
import { Button } from '@/components/ui/button';
import { ConfirmDialog } from '@/components/ui/dialog';
import { cn, formatRelativeTime, truncate } from '@/lib/utils';
import { Plus, Trash2, MessageSquare, CheckSquare, Square, X } from 'lucide-react';
import type { Conversation } from '@/types';

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
        'rounded-lg border px-3 py-2 cursor-pointer transition-colors',
        isSelected ? 'border-blue-500 bg-blue-50' : 'hover:bg-slate-50',
        isChecked && 'bg-rose-50 border-rose-300'
      )}
      onClick={isSelectMode ? onToggleCheck : onClick}
    >
      <div className="flex items-start justify-between gap-2">
        {isSelectMode && (
          <div className="pt-0.5">
            {isChecked ? (
              <CheckSquare className="h-4 w-4 text-rose-500" />
            ) : (
              <Square className="h-4 w-4 text-slate-400" />
            )}
          </div>
        )}
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium truncate">
            {conversation.title ? truncate(conversation.title, 36) : 'New conversation'}
          </p>
          <p className="text-xs text-muted-foreground mt-1">
            {formatRelativeTime(conversation.created_at)}
          </p>
        </div>
        {!isSelectMode && (
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={(e) => {
              e.stopPropagation();
              onDelete();
            }}
          >
            <Trash2 className="h-4 w-4 text-slate-500" />
          </Button>
        )}
      </div>
    </div>
  );
}

export function ConversationList() {
  const navigate = useNavigate();
  const conversations = useStore((s) => s.conversations);
  const selectedConversationId = useStore((s) => s.selectedConversationId);
  const setConversations = useStore((s) => s.setConversations);
  const removeConversation = useStore((s) => s.removeConversation);
  const [isLoading, setIsLoading] = useState(false);

  // Delete modal state
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [conversationToDelete, setConversationToDelete] = useState<string | null>(null);

  // Multi-select state
  const [isSelectMode, setIsSelectMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [bulkDeleteModalOpen, setBulkDeleteModalOpen] = useState(false);

  useEffect(() => {
    async function fetchConversations() {
      setIsLoading(true);
      try {
        const data = await listConversations();
        setConversations(data.conversations);
      } catch (error) {
        console.error('Failed to fetch conversations:', error);
      } finally {
        setIsLoading(false);
      }
    }

    fetchConversations();
  }, [setConversations]);

  const handleNewConversation = () => {
    // Just navigate to /conversations to show empty "new conversation" state
    // The actual conversation will be created when user sends first message
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
      // If we deleted the currently selected conversation, navigate away
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
      <div className="flex items-center justify-between px-4 py-3 border-b">
        <div className="flex items-center gap-2">
          <MessageSquare className="h-4 w-4 text-slate-600" />
          <h2 className="font-semibold text-sm">Conversations</h2>
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
                  setSelectedIds(new Set(conversations.map(c => c.conversation_id)));
                }
              }}
              title={selectedIds.size === conversations.length ? "Deselect all" : "Select all"}
            >
              {selectedIds.size === conversations.length ? 'None' : 'All'}
            </Button>
          )}
          <Button
            size="sm"
            variant={isSelectMode ? "secondary" : "ghost"}
            onClick={toggleSelectMode}
            title={isSelectMode ? "Cancel selection" : "Select conversations"}
          >
            {isSelectMode ? <X className="h-4 w-4" /> : <CheckSquare className="h-4 w-4" />}
          </Button>
          <Button size="sm" variant="ghost" onClick={handleNewConversation}>
            <Plus className="h-4 w-4" />
            New
          </Button>
        </div>
      </div>

      {/* Bulk delete bar */}
      {isSelectMode && selectedIds.size > 0 && (
        <div className="px-4 py-2 bg-rose-50 border-b flex items-center justify-between">
          <span className="text-sm text-rose-700">
            {selectedIds.size} selected
          </span>
          <Button
            size="sm"
            variant="destructive"
            onClick={() => setBulkDeleteModalOpen(true)}
          >
            <Trash2 className="h-4 w-4" />
            Delete
          </Button>
        </div>
      )}

      <div className="flex-1 overflow-y-auto p-4 space-y-2">
        {isLoading && conversations.length === 0 ? (
          <div className="text-sm text-muted-foreground">Loading conversations...</div>
        ) : conversations.length === 0 ? (
          <div className="text-sm text-muted-foreground">No conversations yet.</div>
        ) : (
          conversations.map((conversation) => (
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
      </div>

      {/* Single delete modal */}
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

      {/* Bulk delete modal */}
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
