import { Brain, ChevronDown, Terminal } from 'lucide-react';
import type { ModelStatus } from '@/api/client';
import { DesktopTitlebar } from '@/components/desktop/DesktopTitlebar';
import { cn } from '@/lib/utils';

export type ChatMode = 'chat' | 'agent';

interface ConversationToolbarProps {
  conversationTitle: string;
  mode: ChatMode;
  onModeChange: (mode: ChatMode) => void;
  modelStatus: ModelStatus | null;
  onModelClick: () => void;
  onReasoningClick: () => void;
  mergeTitlebar?: boolean;
  onTerminalClick?: () => void;
  terminalOpen?: boolean;
  showTerminal?: boolean;
}

export function ConversationToolbar({
  conversationTitle,
  mode,
  onModeChange,
  modelStatus,
  onModelClick,
  onReasoningClick,
  mergeTitlebar = false,
  onTerminalClick,
  terminalOpen = false,
  showTerminal = false,
}: ConversationToolbarProps) {
  const modelLabel = modelStatus?.model_name?.split('/').pop() || modelStatus?.model_name || 'Model';

  const toolbarBody = (
      <div
        className={cn(
          'desktop-titlebar-content flex h-full w-full items-center gap-3',
          mergeTitlebar ? 'px-4' : 'px-3'
        )}
      >
        <p className="min-w-0 flex-1 truncate text-[13px] text-zinc-400">
          {conversationTitle || 'New chat'}
        </p>

        <div className="desktop-no-drag flex shrink-0 items-center gap-1">
          <div className="desktop-mode-tabs" role="tablist" aria-label="Mode">
            {([
              { value: 'agent' as const, label: 'Agent' },
              { value: 'chat' as const, label: 'Chat' },
            ]).map((option) => (
              <button
                key={option.value}
                type="button"
                role="tab"
                aria-selected={mode === option.value}
                data-active={mode === option.value ? 'true' : 'false'}
                onClick={() => onModeChange(option.value)}
                className="desktop-mode-tab"
              >
                {option.label}
              </button>
            ))}
          </div>

          <span className="mx-1 h-4 w-px bg-white/10" aria-hidden />

          <button
            type="button"
            onClick={onModelClick}
            className="desktop-ghost-control max-w-[11rem]"
            title="Switch model"
          >
            <span className="truncate">{modelLabel}</span>
            <ChevronDown className="h-3.5 w-3.5 shrink-0 opacity-50" />
          </button>

          <button
            type="button"
            onClick={onReasoningClick}
            className="desktop-icon-control"
            title="Reasoning"
            aria-label="Reasoning settings"
          >
            <Brain className="h-4 w-4" />
          </button>

          {showTerminal && onTerminalClick ? (
            <button
              type="button"
              onClick={onTerminalClick}
              data-active={terminalOpen ? 'true' : 'false'}
              className="desktop-icon-control"
              title="Terminal panel"
              aria-label="Terminal panel"
              aria-pressed={terminalOpen}
            >
              <Terminal className="h-4 w-4" />
            </button>
          ) : null}
        </div>
      </div>
  );

  if (mergeTitlebar) {
    return (
      <DesktopTitlebar className="desktop-toolbar flex h-[var(--titlebar-height)] flex-shrink-0 border-b border-white/[0.05]">
        {toolbarBody}
      </DesktopTitlebar>
    );
  }

  return (
    <header className="desktop-toolbar relative flex h-11 flex-shrink-0 border-b border-white/[0.05]">
      {toolbarBody}
    </header>
  );
}
