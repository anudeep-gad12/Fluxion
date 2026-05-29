import type { Ref, KeyboardEvent, ChangeEvent, ClipboardEvent, ReactNode } from 'react';
import { cn } from '@/lib/utils';
import { DesktopComposer } from '@/components/desktop/DesktopComposer';
import { DesktopAgentStatusBar } from '@/components/desktop/DesktopAgentStatusBar';
import type { ChatMode } from '@/components/desktop/ConversationToolbar';
import type { AgentUIState } from '@/types/agent';

interface DesktopInputDockProps {
  mode: ChatMode;
  onModeChange: (mode: ChatMode) => void;
  workspaceLabel?: string | null;
  workspaceTitle?: string;
  queuedSteers: string[];
  activeAgentRun: { run_id: string; created_at: string } | null;
  activeAgentHudState: AgentUIState | null;
  showAgentHud: boolean;
  onImplementationStarted?: (run: {
    run_id: string;
    stream_token?: string;
    stream_url?: string;
  }) => void;
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
  controlsRow: ReactNode;
  metaRow?: ReactNode;
  limitHint?: ReactNode;
}

export function DesktopInputDock({
  mode,
  onModeChange,
  workspaceLabel,
  workspaceTitle,
  queuedSteers,
  activeAgentRun,
  activeAgentHudState,
  showAgentHud,
  onImplementationStarted,
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
  controlsRow,
  metaRow,
  limitHint,
}: DesktopInputDockProps) {
  const showMeta = Boolean(metaRow || limitHint);

  return (
    <div className="desktop-composer-dock desktop-thread-column w-full flex-shrink-0 px-4 pb-4 pt-2">
      {queuedSteers.length > 0 ? (
        <div className="mb-2 flex flex-wrap gap-1.5">
          {queuedSteers.map((steerMessage, index) => (
            <span
              key={index}
              className="inline-flex items-center gap-1 rounded-md border border-amber-500/20 bg-amber-500/[0.08] px-2 py-1 text-[12px] text-amber-200/90"
            >
              <span className="text-amber-500/60">Queued:</span>{' '}
              {steerMessage.length > 40 ? `${steerMessage.slice(0, 40)}…` : steerMessage}
            </span>
          ))}
        </div>
      ) : null}

      {showAgentHud && activeAgentRun && activeAgentHudState ? (
        <DesktopAgentStatusBar
          runId={activeAgentRun.run_id}
          runCreatedAt={activeAgentRun.created_at}
          agentState={activeAgentHudState}
          onImplementationStarted={onImplementationStarted}
        />
      ) : null}

      <DesktopComposer
        mode={mode}
        onModeChange={onModeChange}
        workspaceLabel={workspaceLabel}
        workspaceTitle={workspaceTitle}
        textareaRef={textareaRef}
        message={message}
        placeholder={placeholder}
        disabled={disabled}
        atLimit={atLimit}
        isSubmitting={isSubmitting}
        isGenerating={isGenerating}
        canSteerActiveRun={canSteerActiveRun}
        hasActiveRun={hasActiveRun}
        stoppingRunId={stoppingRunId}
        onChange={onChange}
        onPaste={onPaste}
        onKeyDown={onKeyDown}
        onSelect={onSelect}
        onClick={onClick}
        onSubmit={onSubmit}
        onStop={onStop}
        mentionPicker={mentionPicker}
        attachmentsRow={attachmentsRow}
        controlsRow={controlsRow}
      />

      {showMeta ? (
        <div className="desktop-prompt-meta">
          <div className="min-w-0 flex-1">{metaRow}</div>
          <div className="flex shrink-0 items-center gap-2">
            {limitHint}
            <span className={cn(messageLength > maxLength * 0.9 && 'text-zinc-500')}>
              {messageLength.toLocaleString()} / {maxLength.toLocaleString()}
            </span>
          </div>
        </div>
      ) : (
        <p className="desktop-prompt-meta justify-end">
          <span className={cn(messageLength > maxLength * 0.9 && 'text-zinc-500')}>
            {messageLength.toLocaleString()} / {maxLength.toLocaleString()}
          </span>
        </p>
      )}
    </div>
  );
}
