import { FolderOpen } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ChatMode } from './ConversationToolbar';

interface AgentComposerOptionsProps {
  mode: ChatMode;
  isWorkspaceLocked: boolean;
  hasConversationWorkspace: boolean;
  effectiveWorkspacePath: string;
  draftWorkspacePath: string;
  onDraftWorkspacePathChange: (value: string) => void;
  onBrowseWorkspace: () => void;
  permissionPolicy: 'strict' | 'relaxed' | 'yolo';
  onPermissionPolicyChange: (value: 'strict' | 'relaxed' | 'yolo') => void;
  collaborationMode: 'default' | 'plan';
  onCollaborationModeChange: (value: 'default' | 'plan') => void;
}

interface AgentContextFooterProps {
  show: boolean;
  composerContextUtilizationPct: number | null;
  composerPromptTokens: number | null;
  composerContextWindow: number | null;
  conversationRawTokens: number;
  formatContextTokens: (value: number) => string;
}

function folderName(workspacePath: string): string {
  const trimmed = workspacePath.trim();
  if (!trimmed) return 'No folder';
  return trimmed.split('/').filter(Boolean).pop() || trimmed;
}

/** Slim toolbar row rendered inside the composer card (Cursor-style). */
export function AgentComposerOptions({
  mode,
  isWorkspaceLocked,
  hasConversationWorkspace,
  effectiveWorkspacePath,
  draftWorkspacePath,
  onDraftWorkspacePathChange,
  onBrowseWorkspace,
  permissionPolicy,
  onPermissionPolicyChange,
  collaborationMode,
  onCollaborationModeChange,
}: AgentComposerOptionsProps) {
  if (mode !== 'agent') {
    return null;
  }

  const displayPath = isWorkspaceLocked ? effectiveWorkspacePath : draftWorkspacePath;

  return (
    <div className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5">
      {isWorkspaceLocked ? (
        <span
          className={cn(
            'desktop-composer-pill max-w-[10rem]',
            !hasConversationWorkspace && 'text-zinc-600'
          )}
          title={hasConversationWorkspace ? effectiveWorkspacePath : undefined}
        >
          {hasConversationWorkspace ? folderName(effectiveWorkspacePath) : 'No folder'}
        </span>
      ) : (
        <>
          <input
            value={draftWorkspacePath}
            onChange={(e) => onDraftWorkspacePathChange(e.target.value)}
            placeholder="Workspace path"
            className="desktop-composer-input min-w-[7rem] max-w-[12rem] flex-1"
          />
          <button
            type="button"
            onClick={onBrowseWorkspace}
            className="desktop-icon-control h-7 w-7"
            title="Browse workspace"
            aria-label="Browse workspace"
          >
            <FolderOpen className="h-3.5 w-3.5" />
          </button>
        </>
      )}

      <select
        value={permissionPolicy}
        onChange={(e) =>
          onPermissionPolicyChange(e.target.value as 'strict' | 'relaxed' | 'yolo')
        }
        className="desktop-composer-select"
        title="Permissions"
        aria-label="Permission policy"
      >
        <option value="strict">Strict</option>
        <option value="relaxed">Relaxed</option>
        <option value="yolo">Yolo</option>
      </select>

      <select
        value={collaborationMode}
        onChange={(e) =>
          onCollaborationModeChange(e.target.value as 'default' | 'plan')
        }
        className="desktop-composer-select"
        title="Collaboration mode"
        aria-label="Collaboration mode"
      >
        <option value="default">Build</option>
        <option value="plan">Plan</option>
      </select>

      {displayPath.trim() ? (
        <span className="hidden truncate text-[11px] text-zinc-600 lg:inline" title={displayPath}>
          {displayPath}
        </span>
      ) : null}
    </div>
  );
}

export function AgentContextFooter({
  show,
  composerContextUtilizationPct,
  composerPromptTokens,
  composerContextWindow,
  conversationRawTokens,
  formatContextTokens,
}: AgentContextFooterProps) {
  if (!show) {
    return null;
  }

  return (
    <div className="flex flex-wrap items-center gap-2 text-[11px] tabular-nums text-zinc-500">
      <span>
        {composerContextUtilizationPct !== null
          ? `${Math.round(composerContextUtilizationPct)}% ctx`
          : '— ctx'}
      </span>
      <span className="text-zinc-700">·</span>
      <span>
        {typeof composerPromptTokens === 'number' && composerContextWindow
          ? `${formatContextTokens(composerPromptTokens)} / ${formatContextTokens(composerContextWindow)}`
          : '— tok'}
      </span>
      {conversationRawTokens > 0 ? (
        <>
          <span className="text-zinc-700">·</span>
          <span>{formatContextTokens(conversationRawTokens)} raw</span>
        </>
      ) : null}
    </div>
  );
}
