import { useEffect, useRef, useState } from 'react';
import { FolderOpen, SlidersHorizontal } from 'lucide-react';
import { DesktopTextOptionGroup } from '@/components/desktop/DesktopTextOptionGroup';

interface DesktopRunSettingsMenuProps {
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

function folderName(workspacePath: string): string {
  const trimmed = workspacePath.trim();
  if (!trimmed) return 'No folder';
  return trimmed.split('/').filter(Boolean).pop() || trimmed;
}

export function DesktopRunSettingsMenu({
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
}: DesktopRunSettingsMenuProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handlePointerDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handlePointerDown);
    return () => document.removeEventListener('mousedown', handlePointerDown);
  }, [open]);

  const summary = `${permissionPolicy} · ${collaborationMode === 'plan' ? 'plan' : 'build'}`;

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        className="desktop-icon-btn"
        title={`Run settings (${summary})`}
        aria-label="Run settings"
        aria-expanded={open}
      >
        <SlidersHorizontal className="h-3.5 w-3.5" />
      </button>

      {open ? (
        <div className="desktop-settings-popover absolute bottom-full left-0 z-50 mb-2 w-[min(18rem,calc(100vw-2rem))]">
          <p className="desktop-settings-label mb-3">Run settings</p>

          <div className="desktop-settings-section">
            <span className="desktop-settings-label">Workspace</span>
            {isWorkspaceLocked ? (
              <p
                className="desktop-settings-workspace-locked"
                data-empty={hasConversationWorkspace ? 'false' : 'true'}
                title={hasConversationWorkspace ? effectiveWorkspacePath : undefined}
              >
                {hasConversationWorkspace ? folderName(effectiveWorkspacePath) : 'No folder selected'}
              </p>
            ) : (
              <div className="flex gap-1.5">
                <input
                  value={draftWorkspacePath}
                  onChange={(e) => onDraftWorkspacePathChange(e.target.value)}
                  placeholder="/path/to/project"
                  className="desktop-settings-field min-w-0 flex-1"
                />
                <button
                  type="button"
                  onClick={onBrowseWorkspace}
                  className="desktop-icon-btn shrink-0"
                  title="Browse workspace"
                  aria-label="Browse workspace"
                >
                  <FolderOpen className="h-3.5 w-3.5" />
                </button>
              </div>
            )}
          </div>

          <div className="desktop-settings-section">
            <span className="desktop-settings-label">Permissions</span>
            <DesktopTextOptionGroup
              ariaLabel="Permission policy"
              value={permissionPolicy}
              onChange={onPermissionPolicyChange}
              options={[
                { value: 'strict', label: 'Strict' },
                { value: 'relaxed', label: 'Relaxed' },
                { value: 'yolo', label: 'Yolo' },
              ]}
            />
          </div>

          <div className="desktop-settings-section">
            <span className="desktop-settings-label">Collaboration</span>
            <DesktopTextOptionGroup
              ariaLabel="Collaboration mode"
              value={collaborationMode}
              onChange={onCollaborationModeChange}
              options={[
                { value: 'default', label: 'Build' },
                { value: 'plan', label: 'Plan' },
              ]}
            />
          </div>
        </div>
      ) : null}
    </div>
  );
}
