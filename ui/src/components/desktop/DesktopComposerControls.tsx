import { Brain, ChevronDown, Terminal } from 'lucide-react';
import type { ModelStatus } from '@/api/client';
import { DesktopRunSettingsMenu } from '@/components/desktop/DesktopRunSettingsMenu';
import { Tooltip } from '@/components/ui/tooltip';
import type { ChatMode } from '@/types';

interface DesktopComposerControlsProps {
  mode: ChatMode;
  modelStatus: ModelStatus | null;
  onModelClick: () => void;
  onReasoningClick: () => void;
  showTerminal: boolean;
  terminalOpen: boolean;
  onTerminalClick: () => void;
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

function formatProviderLabel(provider: string | undefined): string | null {
  if (!provider) return null;
  if (provider === 'local') return 'Local';
  return provider.charAt(0).toUpperCase() + provider.slice(1);
}

/** Minimal footer inside the card: model + a few icons (Cursor-style). */
export function DesktopComposerControls({
  mode,
  modelStatus,
  onModelClick,
  onReasoningClick,
  showTerminal,
  terminalOpen,
  onTerminalClick,
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
}: DesktopComposerControlsProps) {
  const modelLabel =
    modelStatus?.model_name?.split('/').pop() || modelStatus?.model_name || 'Model';
  const providerLabel = formatProviderLabel(modelStatus?.provider);

  return (
    <div className="flex min-w-0 items-center gap-0.5">
      <Tooltip
        content={modelStatus?.model_name ? `Model: ${modelStatus.model_name}` : 'Switch model'}
      >
        <button type="button" onClick={onModelClick} className="desktop-model-trigger">
          <span className="desktop-model-trigger-name">{modelLabel}</span>
          {providerLabel ? (
            <span className="desktop-model-trigger-provider">{providerLabel}</span>
          ) : null}
          <ChevronDown className="desktop-model-trigger-chevron" aria-hidden />
        </button>
      </Tooltip>

      {mode === 'agent' ? (
        <DesktopRunSettingsMenu
          isWorkspaceLocked={isWorkspaceLocked}
          hasConversationWorkspace={hasConversationWorkspace}
          effectiveWorkspacePath={effectiveWorkspacePath}
          draftWorkspacePath={draftWorkspacePath}
          onDraftWorkspacePathChange={onDraftWorkspacePathChange}
          onBrowseWorkspace={onBrowseWorkspace}
          permissionPolicy={permissionPolicy}
          onPermissionPolicyChange={onPermissionPolicyChange}
          collaborationMode={collaborationMode}
          onCollaborationModeChange={onCollaborationModeChange}
        />
      ) : null}

      <Tooltip content="Reasoning settings">
        <button
          type="button"
          onClick={onReasoningClick}
          className="desktop-icon-btn shrink-0"
          aria-label="Reasoning settings"
        >
          <Brain className="h-3.5 w-3.5" />
        </button>
      </Tooltip>

      {showTerminal ? (
        <Tooltip content="Terminal panel">
          <button
            type="button"
            onClick={onTerminalClick}
            data-active={terminalOpen ? 'true' : 'false'}
            className="desktop-icon-btn shrink-0"
            aria-label="Terminal panel"
            aria-pressed={terminalOpen}
          >
            <Terminal className="h-3.5 w-3.5" />
          </button>
        </Tooltip>
      ) : null}
    </div>
  );
}
