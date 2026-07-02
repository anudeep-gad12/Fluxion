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
import { isLocalDesktopApp } from '@/lib/platform';
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
  const desktop = isLocalDesktopApp();
  const inputClassName = desktop ? 'desktop-settings-field' : 'premium-field';
  const selectClassName = 'premium-field appearance-none';

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
          <p className={cn(desktop ? 'desktop-settings-hint' : 'text-xs text-zinc-500')}>Loading reasoning settings…</p>
        ) : (
          <div className={cn('space-y-4', !desktop && 'font-mono text-xs')}>
            <section className={cn(desktop ? 'desktop-settings-section' : 'premium-panel px-4 py-3.5')}>
              <span className={cn(desktop ? 'desktop-settings-label' : 'premium-section-label')}>Active model</span>
              <div className={cn(desktop ? 'desktop-settings-model-line' : 'mt-2 text-sm text-zinc-100')}>{modelName}</div>
              <div className={cn(desktop ? 'desktop-settings-model-provider' : 'mt-1 text-[11px] uppercase tracking-[0.16em] text-zinc-500')}>
                {providerFamily}
              </div>
            </section>

            <section className={cn(desktop ? 'desktop-settings-section' : 'premium-panel px-4 py-4')}>
              <div className="grid gap-4 sm:grid-cols-2">
                <label className="space-y-2">
                  <div>
                    <div className={cn(desktop ? 'desktop-settings-field-label' : 'text-zinc-300')}>Max output</div>
                    <div className={cn(desktop ? 'desktop-settings-hint !mt-1' : 'mt-1 text-[11px] leading-5 text-zinc-500')}>
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
                      <div className={cn(desktop ? 'desktop-settings-field-label' : 'text-zinc-300')}>Thinking effort</div>
                      <div className={cn(desktop ? 'desktop-settings-hint !mt-1' : 'mt-1 text-[11px] leading-5 text-zinc-500')}>
                        Provider-managed reasoning depth.
                      </div>
                    </div>
                    {desktop ? (
                      <DesktopTextOptionGroup
                        ariaLabel="Thinking effort"
                        value={draft.reasoning_effort ?? ''}
                        onChange={(value) => update('reasoning_effort', value || null)}
                        options={[
                          { value: '', label: 'Default' },
                          ...effortChoices.map((opt) => ({ value: opt, label: opt })),
                        ]}
                      />
                    ) : (
                      <select
                        value={draft.reasoning_effort ?? ''}
                        onChange={(e) => update('reasoning_effort', e.target.value || null)}
                        disabled={!capabilities.reasoning_effort.supported}
                        title={disabledReason(capabilities.reasoning_effort.supported, capabilities.reasoning_effort.reason)}
                        className={selectClassName}
                      >
                        <option value="">default</option>
                        {effortChoices.map((opt) => (
                          <option key={opt} value={opt}>{opt}</option>
                        ))}
                      </select>
                    )}
                  </div>
                )}
              </div>
            </section>

            {isFireworks ? (
              <section className={cn(desktop ? 'desktop-settings-section' : 'premium-panel px-4 py-4')}>
                <span className={cn(desktop ? 'desktop-settings-label' : 'premium-section-label')}>Fireworks</span>
                <div className="mt-3 grid gap-4 sm:grid-cols-2">
                  <div className="space-y-2">
                    <div className={cn(desktop ? 'desktop-settings-field-label' : 'text-zinc-300')}>Control mode</div>
                    {desktop ? (
                      <DesktopTextOptionGroup
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
                      />
                    ) : (
                      <select
                        value={draft.fireworks_reasoning_mode}
                        onChange={(e) => {
                          const nextMode = e.target.value as 'effort' | 'thinking';
                          updateMany({
                            fireworks_reasoning_mode: nextMode,
                            fireworks_thinking_budget_tokens:
                              nextMode === 'thinking'
                                ? Math.max(draft.fireworks_thinking_budget_tokens ?? minFireworksThinkingBudget, minFireworksThinkingBudget)
                                : null,
                          });
                        }}
                        disabled={!capabilities.fireworks_reasoning_mode.supported}
                        title={disabledReason(capabilities.fireworks_reasoning_mode.supported, capabilities.fireworks_reasoning_mode.reason)}
                        className={selectClassName}
                      >
                        <option value="effort">effort-based</option>
                        <option value="thinking">budget-based</option>
                      </select>
                    )}
                  </div>

                  {fireworksMode === 'effort' ? (
                    <div className="space-y-2">
                      <div className={cn(desktop ? 'desktop-settings-field-label' : 'text-zinc-300')}>Thinking effort</div>
                      {desktop ? (
                        <DesktopTextOptionGroup
                          ariaLabel="Thinking effort"
                          value={draft.reasoning_effort ?? ''}
                          onChange={(value) => update('reasoning_effort', value || null)}
                          options={[
                            { value: '', label: 'Default' },
                            ...effortChoices.map((opt) => ({ value: opt, label: opt })),
                          ]}
                        />
                      ) : (
                        <select
                          value={draft.reasoning_effort ?? ''}
                          onChange={(e) => update('reasoning_effort', e.target.value || null)}
                          disabled={!capabilities.reasoning_effort.supported}
                          title={disabledReason(capabilities.reasoning_effort.supported, capabilities.reasoning_effort.reason)}
                          className={selectClassName}
                        >
                          <option value="">default</option>
                          {effortChoices.map((opt) => (
                            <option key={opt} value={opt}>{opt}</option>
                          ))}
                        </select>
                      )}
                    </div>
                  ) : (
                    <label className="space-y-2">
                      <div className={cn(desktop ? 'desktop-settings-field-label' : 'text-zinc-300')}>Max thinking tokens</div>
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
                <p className={cn(desktop ? 'desktop-settings-hint' : 'mt-3 text-[11px] leading-5 text-zinc-500')}>
                  {fireworksMode === 'effort'
                    ? 'Sends reasoning_effort only.'
                    : 'Sends thinking.budget_tokens only.'}
                </p>
              </section>
            ) : showReasoningMaxTokens ? (
              <section className={cn(desktop ? 'desktop-settings-section' : 'premium-panel px-4 py-4')}>
                <span className={cn(desktop ? 'desktop-settings-label' : 'premium-section-label')}>OpenRouter</span>
                <div className="mt-3 grid gap-4 sm:grid-cols-2">
                  <div className="space-y-2">
                    <div className={cn(desktop ? 'desktop-settings-field-label' : 'text-zinc-300')}>Control mode</div>
                    {desktop ? (
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
                    ) : (
                      <select
                        value={openRouterMode}
                        onChange={(e) => {
                          if (e.target.value === 'effort') {
                            updateMany({ reasoning_max_tokens: null });
                          } else {
                            updateMany({ reasoning_max_tokens: draft.reasoning_max_tokens ?? 1024 });
                          }
                        }}
                        className={selectClassName}
                      >
                        <option value="effort">effort-based</option>
                        <option value="budget">budget-based</option>
                      </select>
                    )}
                  </div>

                  {openRouterMode === 'effort' ? (
                    <div className="space-y-2">
                      <div className={cn(desktop ? 'desktop-settings-field-label' : 'text-zinc-300')}>Thinking effort</div>
                      {desktop ? (
                        <DesktopTextOptionGroup
                          ariaLabel="Thinking effort"
                          value={draft.reasoning_effort ?? ''}
                          onChange={(value) => update('reasoning_effort', value || null)}
                          options={[
                            { value: '', label: 'Default' },
                            ...effortChoices.map((opt) => ({ value: opt, label: opt })),
                          ]}
                        />
                      ) : (
                        <select
                          value={draft.reasoning_effort ?? ''}
                          onChange={(e) => update('reasoning_effort', e.target.value || null)}
                          disabled={!capabilities.reasoning_effort.supported}
                          title={disabledReason(capabilities.reasoning_effort.supported, capabilities.reasoning_effort.reason)}
                          className={selectClassName}
                        >
                          <option value="">default</option>
                          {effortChoices.map((opt) => (
                            <option key={opt} value={opt}>{opt}</option>
                          ))}
                        </select>
                      )}
                    </div>
                  ) : (
                    <label className="space-y-2">
                      <div className={cn(desktop ? 'desktop-settings-field-label' : 'text-zinc-300')}>Max thinking tokens</div>
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
                desktop ? 'desktop-settings-section desktop-settings-hint' : 'premium-panel px-4 py-3.5 text-[11px] leading-5 text-zinc-500'
              )}>
                This provider has no separate max thinking token setting.
              </section>
            )}

            <div className={cn(desktop ? 'desktop-settings-actions' : 'flex justify-end gap-2')}>
              <button
                onClick={() => onOpenChange(false)}
                className={cn(desktop ? 'desktop-settings-btn-ghost' : 'premium-subtle-button')}
                type="button"
              >
                Cancel
              </button>
              <button
                onClick={onSave}
                disabled={saving}
                className={cn(desktop ? 'desktop-settings-btn-primary' : 'premium-primary-button')}
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
