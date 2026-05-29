import type { Ref, KeyboardEvent, ChangeEvent, ClipboardEvent, ReactNode } from 'react';
import { ArrowUp, Square } from 'lucide-react';
import { cn } from '@/lib/utils';

interface ComposerProps {
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
  messageLength: number;
  maxLength: number;
  onChange: (event: ChangeEvent<HTMLTextAreaElement>) => void;
  onPaste: (event: ClipboardEvent<HTMLTextAreaElement>) => void;
  onKeyDown: (event: KeyboardEvent<HTMLTextAreaElement>) => void;
  onSelect: () => void;
  onClick: () => void;
  onSubmit: () => void;
  onStop: () => void;
  mentionPicker: ReactNode;
  attachmentsRow?: ReactNode;
  agentOptionsRow?: ReactNode;
  contextStatsRow?: ReactNode;
}

export function Composer({
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
  messageLength,
  maxLength,
  onChange,
  onPaste,
  onKeyDown,
  onSelect,
  onClick,
  onSubmit,
  onStop,
  mentionPicker,
  attachmentsRow,
  agentOptionsRow,
  contextStatsRow,
}: ComposerProps) {
  const sendDisabled =
    !message.trim() || isSubmitting || atLimit || (hasActiveRun && !canSteerActiveRun);

  const sendLabel = isSubmitting
    ? 'Sending…'
    : atLimit
      ? 'Limit'
      : canSteerActiveRun
        ? 'Steer'
        : 'Send';

  return (
    <div className="desktop-composer-dock desktop-thread-column w-full px-4 pb-5 pt-2">
      {attachmentsRow}

      <div className="desktop-composer-card fluxion-composer relative overflow-visible">
        <textarea
          ref={textareaRef}
          placeholder={placeholder}
          value={message}
          onChange={onChange}
          onPaste={onPaste}
          onKeyDown={onKeyDown}
          onSelect={onSelect}
          onClick={onClick}
          rows={1}
          className="desktop-composer-input-field block w-full resize-none bg-transparent px-4 pb-2 pt-3.5 text-[15px] leading-relaxed text-zinc-100 outline-none placeholder:text-zinc-500"
          disabled={disabled}
        />

        {mentionPicker}

        <div className="flex items-center gap-2 border-t border-white/[0.06] px-2 py-2">
          {agentOptionsRow ?? <div className="min-w-0 flex-1" />}

          <div className="flex shrink-0 items-center gap-1.5">
            {isGenerating ? (
              <button
                type="button"
                onClick={onStop}
                disabled={!!stoppingRunId}
                className="desktop-send-button desktop-send-button-stop"
                title="Stop"
                aria-label="Stop run"
              >
                <Square className="h-3.5 w-3.5 fill-current" />
              </button>
            ) : (
              <button
                type="button"
                onClick={onSubmit}
                disabled={sendDisabled}
                className={cn(
                  'desktop-send-button',
                  sendDisabled && 'desktop-send-button-disabled',
                  canSteerActiveRun && !sendDisabled && 'desktop-send-button-steer'
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

      <div className="mt-2 flex items-center justify-between gap-3 px-1">
        <span className="text-[11px] text-zinc-600">⌘↵ send</span>
        <div className="flex items-center gap-3">
          {contextStatsRow}
          <span
            className={cn(
              'text-[11px] tabular-nums text-zinc-600',
              messageLength > maxLength * 0.9 && 'text-zinc-400'
            )}
          >
            {messageLength.toLocaleString()} / {maxLength.toLocaleString()}
          </span>
        </div>
      </div>
    </div>
  );
}
