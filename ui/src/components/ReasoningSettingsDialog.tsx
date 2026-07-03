/**
 * Reasoning settings dialog (effort / thinking budget per provider family).
 */

import type { ReasoningSettings, ReasoningSettingsResponse } from '@/api/client';
import { DesktopTextOptionGroup } from '@/components/desktop/DesktopTextOptionGroup';
import {
  Dialog,
  DialogHeader,
  DialogTitle,
  DialogContent,
} from '@/components/ui/dialog';
import { cn } from '@/lib/utils';

export function ReasoningSettingsDialog({
  open,
  onOpenChange,
  settingsResponse,
  draft,
  onDraftChange,
  onSave,
  saving,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  settingsResponse: ReasoningSettingsResponse | null;
  draft: ReasoningSettings | null;
  onDraftChange: (next: ReasoningSettings) => void;
  onSave: () => void;
  saving: boolean;
}) {
  const capabilities = settingsResponse?.capabilities;
  const providerFamily = settingsResponse?.provider_family || 'generic';
  const modelName = settingsResponse?.model_name || 'model';
  const isFireworks = providerFamily === 'fireworks';
  const showReasoningEffort = !isFireworks && !!capabilities?.reasoning_effort?.supported;
  const showReasoningMaxTokens =
    providerFamily === 'openrouter' && !!capabilities?.reasoning_max_tokens?.supported;
  const fireworksMode = draft?.fireworks_reasoning_mode ?? 'effort';
  const openRouterMode = draft?.reasoning_max_tokens == null ? 'effort' : 'budget';
  const minFireworksThinkingBudget = 1024;
  const inputClassName = 'desktop-settings-field';

  const effortChoices =
    capabilities?.reasoning_effort?.options?.length
      ? capabilities.reasoning_effort.options
      : ['low', 'medium', 'high'];

  const disabledReason = (supported?: boolean, reason?: string | null) =>
    supported ? undefined : (reason || 'Unsupported by active provider/model');

  const update = <K extends keyof ReasoningSettings>(key: K, value: ReasoningSettings[K]) => {
    if (!draft) return;
    onDraftChange({ ...draft, [key]: value });
  };

  const updateMany = (patch: Partial<ReasoningSettings>) => {
    if (!draft) return;
    onDraftChange({ ...draft, ...patch });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange} className="max-w-3xl">
      <DialogHeader>
        <DialogTitle>Reasoning settings</DialogTitle>
      </DialogHeader>
      <DialogContent className="space-y-4">
        {!draft || !capabilities ? (
          <p className={cn('desktop-settings-hint')}>Loading reasoning settings…</p>
        ) : (
          <div className="space-y-4">
            <section className={cn('desktop-settings-section')}>
              <span className={cn('desktop-settings-label')}>Active model</span>
              <div className={cn('desktop-settings-model-line')}>{modelName}</div>
              <div className={cn('desktop-settings-model-provider')}>
                {providerFamily}
              </div>
            </section>

            <section className={cn('desktop-settings-section')}>
              <div className="grid gap-4 sm:grid-cols-2">
                <label className="space-y-2">
                  <div>
                    <div className={cn('desktop-settings-field-label')}>Max output</div>
                    <div className={cn('desktop-settings-hint !mt-1')}>
                      Leave blank to use the active model max.
                    </div>
                  </div>
                  <input
                    type="number"
                    min={1}
                    placeholder="Auto"
                    value={draft.max_output_tokens ?? ''}
                    onChange={(e) => update('max_output_tokens', e.target.value === '' ? null : Number(e.target.value))}
                    className={inputClassName}
                  />
                </label>
                {showReasoningEffort && !showReasoningMaxTokens && (
                  <div className="space-y-2">
                    <div>
                      <div className={cn('desktop-settings-field-label')}>Thinking effort</div>
                      <div className={cn('desktop-settings-hint !mt-1')}>
                        Provider-managed reasoning depth.
                      </div>
                    </div>
                    {<DesktopTextOptionGroup
                        ariaLabel="Thinking effort"
                        value={draft.reasoning_effort ?? ''}
                        onChange={(value) => update('reasoning_effort', value || null)}
                        options={[
                          { value: '', label: 'Default' },
                          ...effortChoices.map((opt) => ({ value: opt, label: opt })),
                        ]}
                      />}
                  </div>
                )}
              </div>
            </section>

            {isFireworks ? (
              <section className={cn('desktop-settings-section')}>
                <span className={cn('desktop-settings-label')}>Fireworks</span>
                <div className="mt-3 grid gap-4 sm:grid-cols-2">
                  <div className="space-y-2">
                    <div className={cn('desktop-settings-field-label')}>Control mode</div>
                    {<DesktopTextOptionGroup
                        ariaLabel="Fireworks control mode"
                        value={draft.fireworks_reasoning_mode}
                        onChange={(nextMode) => {
                          updateMany({
                            fireworks_reasoning_mode: nextMode,
                            fireworks_thinking_budget_tokens:
                              nextMode === 'thinking'
                                ? Math.max(draft.fireworks_thinking_budget_tokens ?? minFireworksThinkingBudget, minFireworksThinkingBudget)
                                : null,
                          });
                        }}
                        options={[
                          { value: 'effort', label: 'Effort' },
                          { value: 'thinking', label: 'Budget' },
                        ]}
                      />}
                  </div>

                  {fireworksMode === 'effort' ? (
                    <div className="space-y-2">
                      <div className={cn('desktop-settings-field-label')}>Thinking effort</div>
                      {<DesktopTextOptionGroup
                          ariaLabel="Thinking effort"
                          value={draft.reasoning_effort ?? ''}
                          onChange={(value) => update('reasoning_effort', value || null)}
                          options={[
                            { value: '', label: 'Default' },
                            ...effortChoices.map((opt) => ({ value: opt, label: opt })),
                          ]}
                        />}
                    </div>
                  ) : (
                    <label className="space-y-2">
                      <div className={cn('desktop-settings-field-label')}>Max thinking tokens</div>
                      <input
                        type="number"
                        min={1024}
                        value={draft.fireworks_thinking_budget_tokens ?? ''}
                        onChange={(e) => update('fireworks_thinking_budget_tokens', e.target.value === '' ? null : Number(e.target.value))}
                        onBlur={(e) => update('fireworks_thinking_budget_tokens', Math.max(Number(e.target.value) || minFireworksThinkingBudget, minFireworksThinkingBudget))}
                        disabled={!capabilities.fireworks_thinking_budget_tokens.supported}
                        title={disabledReason(capabilities.fireworks_thinking_budget_tokens.supported, capabilities.fireworks_thinking_budget_tokens.reason)}
                        className={inputClassName}
                      />
                    </label>
                  )}
                </div>
                <p className={cn('desktop-settings-hint')}>
                  {fireworksMode === 'effort'
                    ? 'Sends reasoning_effort only.'
                    : 'Sends thinking.budget_tokens only.'}
                </p>
              </section>
            ) : showReasoningMaxTokens ? (
              <section className={cn('desktop-settings-section')}>
                <span className={cn('desktop-settings-label')}>OpenRouter</span>
                <div className="mt-3 grid gap-4 sm:grid-cols-2">
                  <div className="space-y-2">
                    <div className={cn('desktop-settings-field-label')}>Control mode</div>
                    {<DesktopTextOptionGroup
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
                      />}
                  </div>

                  {openRouterMode === 'effort' ? (
                    <div className="space-y-2">
                      <div className={cn('desktop-settings-field-label')}>Thinking effort</div>
                      {<DesktopTextOptionGroup
                          ariaLabel="Thinking effort"
                          value={draft.reasoning_effort ?? ''}
                          onChange={(value) => update('reasoning_effort', value || null)}
                          options={[
                            { value: '', label: 'Default' },
                            ...effortChoices.map((opt) => ({ value: opt, label: opt })),
                          ]}
                        />}
                    </div>
                  ) : (
                    <label className="space-y-2">
                      <div className={cn('desktop-settings-field-label')}>Max thinking tokens</div>
                      <input
                        type="number"
                        min={1}
                        value={draft.reasoning_max_tokens ?? ''}
                        onChange={(e) => update('reasoning_max_tokens', e.target.value === '' ? null : Number(e.target.value))}
                        disabled={!capabilities.reasoning_max_tokens.supported}
                        title={disabledReason(capabilities.reasoning_max_tokens.supported, capabilities.reasoning_max_tokens.reason)}
                        className={inputClassName}
                      />
                    </label>
                  )}
                </div>
              </section>
            ) : (
              <section className={cn(
                'desktop-settings-section desktop-settings-hint'
              )}>
                This provider has no separate max thinking token setting.
              </section>
            )}

            <div className={cn('desktop-settings-actions')}>
              <button
                onClick={() => onOpenChange(false)}
                className={cn('desktop-settings-btn-ghost')}
                type="button"
              >
                Cancel
              </button>
              <button
                onClick={onSave}
                disabled={saving}
                className={cn('desktop-settings-btn-primary')}
                type="button"
              >
                {saving ? 'Saving…' : 'Save'}
              </button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
