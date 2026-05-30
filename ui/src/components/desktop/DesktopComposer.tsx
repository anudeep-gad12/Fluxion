import type { Ref, KeyboardEvent, ChangeEvent, ClipboardEvent, ReactNode } from 'react';
import { ArrowUp, Folder, Square } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ChatMode } from '@/components/desktop/ConversationToolbar';

interface DesktopComposerProps {
  mode: ChatMode;
  onModeChange: (mode: ChatMode) => void;
  workspaceLabel?: string | null;
  workspaceTitle?: string;
  textareaRef: Ref<HTMLTextAreaElement>;
  message: string;
  placeholder: string;
  disabled: boolean;
  atLimit: boolean;
  isSubmitting: boolean;
  isGenerating: boolean;
  canSteerActiveRun: boolean;
  hasActiveRun: boolean;
  stoppingRunId: string | null;
  onChange: (event: ChangeEvent<HTMLTextAreaElement>) => void;
  onPaste: (event: ClipboardEvent<HTMLTextAreaElement>) => void;
  onKeyDown: (event: KeyboardEvent<HTMLTextAreaElement>) => void;
  onSelect: () => void;
  onClick: () => void;
  onSubmit: () => void;
  onStop: () => void;
  mentionPicker: ReactNode;
  attachmentsRow?: ReactNode;
  controlsRow: ReactNode;
}

/** Unified prompt surface — one shell, not a boxed textarea + footer strip. */
export function DesktopComposer({
  mode,
  onModeChange,
  workspaceLabel,
  workspaceTitle,
  textareaRef,
  message,
  placeholder,
  disabled,
  atLimit,
  isSubmitting,
  isGenerating,
  canSteerActiveRun,
  hasActiveRun,
  stoppingRunId,
  onChange,
  onPaste,
  onKeyDown,
  onSelect,
  onClick,
  onSubmit,
  onStop,
  mentionPicker,
  attachmentsRow,
  controlsRow,
}: DesktopComposerProps) {
  const sendDisabled =
    !message.trim() || isSubmitting || atLimit || (hasActiveRun && !canSteerActiveRun);

  const sendLabel = isSubmitting
    ? 'Sending…'
    : atLimit
      ? 'Limit'
      : canSteerActiveRun
        ? 'Steer'
        : 'Send';

  const modeOptions = [
    { value: 'agent' as const, label: 'Agent' },
    { value: 'chat' as const, label: 'Chat' },
  ];

  const modeTabs = (
    <div className="desktop-mode-switch shrink-0" role="tablist" aria-label="Mode">
      {modeOptions.map((option, index) => (
        <span key={option.value} className="inline-flex items-center">
          {index > 0 ? (
            <span className="desktop-mode-switch-sep" aria-hidden>
              ·
            </span>
          ) : null}
          <button
            type="button"
            role="tab"
            aria-selected={mode === option.value}
            data-active={mode === option.value ? 'true' : 'false'}
            onClick={() => onModeChange(option.value)}
            className="desktop-mode-switch-option"
          >
            {option.label}
          </button>
        </span>
      ))}
    </div>
  );

  return (
    <div className="desktop-prompt-shell">
      {mode === 'agent' && workspaceLabel ? (
        <div className="desktop-prompt-header">
          <span
            className="desktop-prompt-workspace flex min-w-0 items-center gap-1 truncate"
            title={workspaceTitle}
          >
            <Folder className="h-3 w-3 shrink-0 opacity-50" aria-hidden />
            <span className={cn('truncate', workspaceLabel === 'No folder' ? '' : 'desktop-prompt-workspace-name')}>{workspaceLabel}</span>
          </span>
        </div>
      ) : null}

      {attachmentsRow}

      <div className="desktop-prompt-input-wrap relative">
        <textarea
          ref={textareaRef}
          placeholder={placeholder}
          value={message}
          onChange={onChange}
          onPaste={onPaste}
          onKeyDown={onKeyDown}
          onSelect={onSelect}
          onClick={onClick}
          rows={2}
          className="desktop-prompt-input"
          disabled={disabled}
        />

        {mentionPicker}
      </div>

      <div className="desktop-prompt-footer">
        <div className="min-w-0 flex-1">{controlsRow}</div>

        <div className="desktop-prompt-footer-actions shrink-0">
          {modeTabs}

          {isGenerating ? (
            <button
              type="button"
              onClick={onStop}
              disabled={!!stoppingRunId}
              className="desktop-send-btn desktop-send-btn-stop"
              title="Stop"
              aria-label="Stop run"
            >
              <Square className="h-3 w-3 fill-current" />
            </button>
          ) : (
            <button
              type="button"
              onClick={onSubmit}
              disabled={sendDisabled}
              className={cn(
                'desktop-send-btn',
                sendDisabled && 'desktop-send-btn-disabled',
                canSteerActiveRun && !sendDisabled && 'desktop-send-btn-steer'
              )}
              title={sendLabel}
              aria-label={sendLabel}
            >
              <ArrowUp className="h-4 w-4" strokeWidth={2.5} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
