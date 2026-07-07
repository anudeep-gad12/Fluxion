/**
 * Unified run-settings modal — one place for Reasoning, Permissions,
 * Collaboration, and Workspace, replacing the old split reasoning dialog +
 * run-settings popover. Reasoning persists via onSave; the run-control toggles
 * (permissions/collaboration/workspace) apply live on change.
 */

import { FolderOpen } from 'lucide-react';
import type { ReasoningSettings, ReasoningSettingsResponse } from '@/api/client';
import { DesktopTextOptionGroup } from '@/components/desktop/DesktopTextOptionGroup';
import { ReasoningEffortSlider } from '@/components/desktop/ReasoningEffortSlider';
import {
  Dialog,
  DialogHeader,
  DialogTitle,
  DialogContent,
} from '@/components/ui/dialog';
import { Tooltip } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import type { ChatMode } from '@/types';

interface RunSettingsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  mode: ChatMode;
  // Run-control settings (agent mode only; apply live)
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
  // Reasoning settings (both modes; persisted via onSave)
  settingsResponse: ReasoningSettingsResponse | null;
  draft: ReasoningSettings | null;
  onDraftChange: (next: ReasoningSettings) => void;
  onSave: () => void;
  saving: boolean;
}

function folderName(workspacePath: string): string {
  const trimmed = workspacePath.trim();
  if (!trimmed) return 'No folder';
  return trimmed.split('/').filter(Boolean).pop() || trimmed;
}

/** The reasoning-effort fields, provider-aware (effort / thinking budget). */
function ReasoningFields({
  settingsResponse,
  draft,
  onDraftChange,
}: {
  settingsResponse: ReasoningSettingsResponse | null;
  draft: ReasoningSettings | null;
  onDraftChange: (next: ReasoningSettings) => void;
}) {
  const capabilities = settingsResponse?.capabilities;
  const providerFamily = settingsResponse?.provider_family || 'generic';
  const isFireworks = providerFamily === 'fireworks';
  const showReasoningEffort = !isFireworks && !!capabilities?.reasoning_effort?.supported;
  const showReasoningMaxTokens =
    providerFamily === 'openrouter' && !!capabilities?.reasoning_max_tokens?.supported;
  const fireworksMode = draft?.fireworks_reasoning_mode ?? 'effort';
  const openRouterMode = draft?.reasoning_max_tokens == null ? 'effort' : 'budget';
  const minFireworksThinkingBudget = 1024;
  const inputClassName = 'desktop-settings-field';

  const effortChoices = capabilities?.reasoning_effort?.options?.length
    ? capabilities.reasoning_effort.options
    : ['low', 'medium', 'high'];

  const disabledReason = (supported?: boolean, reason?: string | null) =>
    supported ? undefined : reason || 'Unsupported by active provider/model';

  const update = <K extends keyof ReasoningSettings>(key: K, value: ReasoningSettings[K]) => {
    if (!draft) return;
    onDraftChange({ ...draft, [key]: value });
  };

  const updateMany = (patch: Partial<ReasoningSettings>) => {
    if (!draft) return;
    onDraftChange({ ...draft, ...patch });
  };

  if (!draft || !capabilities) {
    return <p className="desktop-settings-hint">Loading reasoning settings…</p>;
  }

  const effortGroup = (
    <ReasoningEffortSlider
      ariaLabel="Thinking effort"
      value={draft.reasoning_effort ?? ''}
      onChange={(value) => update('reasoning_effort', value || null)}
      options={[
        { value: '', label: 'Default' },
        ...effortChoices.map((opt) => ({ value: opt, label: opt })),
      ]}
    />
  );

  return (
    <div className="space-y-5">
      {showReasoningEffort && !showReasoningMaxTokens && (
        <div className="space-y-2.5">
          <div className="desktop-settings-field-label">Thinking effort</div>
          {effortGroup}
        </div>
      )}

      {isFireworks ? (
        <div className="space-y-2.5">
          <div className="desktop-settings-field-label">Control mode</div>
          <DesktopTextOptionGroup
            ariaLabel="Fireworks control mode"
            value={draft.fireworks_reasoning_mode}
            onChange={(nextMode) =>
              updateMany({
                fireworks_reasoning_mode: nextMode,
                fireworks_thinking_budget_tokens:
                  nextMode === 'thinking'
                    ? Math.max(
                        draft.fireworks_thinking_budget_tokens ?? minFireworksThinkingBudget,
                        minFireworksThinkingBudget,
                      )
                    : null,
              })
            }
            options={[
              { value: 'effort', label: 'Effort' },
              { value: 'thinking', label: 'Budget' },
            ]}
          />
          {fireworksMode === 'effort' ? (
            <div className="space-y-2.5 pt-1">
              <div className="desktop-settings-field-label">Thinking effort</div>
              {effortGroup}
            </div>
          ) : (
            <label className="block space-y-2 pt-1">
              <div className="desktop-settings-field-label">Max thinking tokens</div>
              <input
                type="number"
                min={1024}
                value={draft.fireworks_thinking_budget_tokens ?? ''}
                onChange={(e) =>
                  update(
                    'fireworks_thinking_budget_tokens',
                    e.target.value === '' ? null : Number(e.target.value),
                  )
                }
                onBlur={(e) =>
                  update(
                    'fireworks_thinking_budget_tokens',
                    Math.max(Number(e.target.value) || minFireworksThinkingBudget, minFireworksThinkingBudget),
                  )
                }
                disabled={!capabilities.fireworks_thinking_budget_tokens.supported}
                title={disabledReason(
                  capabilities.fireworks_thinking_budget_tokens.supported,
                  capabilities.fireworks_thinking_budget_tokens.reason,
                )}
                className={inputClassName}
              />
            </label>
          )}
        </div>
      ) : showReasoningMaxTokens ? (
        <div className="space-y-2.5">
          <div className="desktop-settings-field-label">Control mode</div>
          <DesktopTextOptionGroup
            ariaLabel="OpenRouter control mode"
            value={openRouterMode}
            onChange={(value) => {
              if (value === 'effort') {
                updateMany({ reasoning_max_tokens: null });
              } else {
                updateMany({ reasoning_max_tokens: draft.reasoning_max_tokens ?? 1024 });
              }
            }}
            options={[
              { value: 'effort', label: 'Effort' },
              { value: 'budget', label: 'Budget' },
            ]}
          />
          {openRouterMode === 'effort' ? (
            <div className="space-y-2.5 pt-1">
              <div className="desktop-settings-field-label">Thinking effort</div>
              {effortGroup}
            </div>
          ) : (
            <label className="block space-y-2 pt-1">
              <div className="desktop-settings-field-label">Max thinking tokens</div>
              <input
                type="number"
                min={1}
                value={draft.reasoning_max_tokens ?? ''}
                onChange={(e) =>
                  update('reasoning_max_tokens', e.target.value === '' ? null : Number(e.target.value))
                }
                disabled={!capabilities.reasoning_max_tokens.supported}
                title={disabledReason(
                  capabilities.reasoning_max_tokens.supported,
                  capabilities.reasoning_max_tokens.reason,
                )}
                className={inputClassName}
              />
            </label>
          )}
        </div>
      ) : null}

      <label className="block space-y-2">
        <div className="desktop-settings-field-label">Max output</div>
        <div className="desktop-settings-hint">Leave blank to use the active model max.</div>
        <input
          type="number"
          min={1}
          placeholder="Auto"
          value={draft.max_output_tokens ?? ''}
          onChange={(e) =>
            update('max_output_tokens', e.target.value === '' ? null : Number(e.target.value))
          }
          className={inputClassName}
        />
      </label>
    </div>
  );
}

export function RunSettingsDialog({
  open,
  onOpenChange,
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
  settingsResponse,
  draft,
  onDraftChange,
  onSave,
  saving,
}: RunSettingsDialogProps) {
  const isAgent = mode === 'agent';
  const modelName = settingsResponse?.model_name || 'model';
  const providerFamily = settingsResponse?.provider_family || 'generic';

  return (
    <Dialog open={open} onOpenChange={onOpenChange} className="max-w-lg">
      <DialogHeader>
        <DialogTitle>Run settings</DialogTitle>
      </DialogHeader>
      <DialogContent className="pt-1">
        {isAgent ? (
          <>
            <section className="desktop-settings-section">
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
            </section>

            <section className="desktop-settings-section">
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
            </section>

            <section className="desktop-settings-section">
              <span className="desktop-settings-label">Workspace</span>
              {isWorkspaceLocked ? (
                <p
                  className="desktop-settings-workspace-locked"
                  data-empty={hasConversationWorkspace ? 'false' : 'true'}
                  title={hasConversationWorkspace ? effectiveWorkspacePath : undefined}
                >
                  {hasConversationWorkspace
                    ? folderName(effectiveWorkspacePath)
                    : 'No folder selected'}
                </p>
              ) : (
                <div className="flex gap-1.5">
                  <input
                    value={draftWorkspacePath}
                    onChange={(e) => onDraftWorkspacePathChange(e.target.value)}
                    placeholder="/path/to/project"
                    className="desktop-settings-field min-w-0 flex-1"
                  />
                  <Tooltip content="Browse workspace">
                    <button
                      type="button"
                      onClick={onBrowseWorkspace}
                      className="desktop-icon-btn shrink-0"
                      aria-label="Browse workspace"
                    >
                      <FolderOpen className="h-3.5 w-3.5" />
                    </button>
                  </Tooltip>
                </div>
              )}
            </section>
          </>
        ) : null}

        <section className="desktop-settings-section">
          <span className="desktop-settings-label">Reasoning</span>
          <div className="desktop-settings-model-line">{modelName}</div>
          <div className="desktop-settings-model-provider mb-3">{providerFamily}</div>
          <ReasoningFields
            settingsResponse={settingsResponse}
            draft={draft}
            onDraftChange={onDraftChange}
          />
        </section>

        <div className={cn('desktop-settings-actions')}>
          <button
            onClick={() => onOpenChange(false)}
            className="desktop-settings-btn-ghost"
            type="button"
          >
            Cancel
          </button>
          <button
            onClick={onSave}
            disabled={saving}
            className="desktop-settings-btn-primary"
            type="button"
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
