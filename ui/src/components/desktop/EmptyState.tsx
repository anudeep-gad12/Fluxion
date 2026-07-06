import { cn } from '@/lib/utils';
import { startWindowDrag } from '@/lib/windowDrag';
import type { ModelStatus } from '@/api/client';
import type { ChatMode } from '@/types';
import type { MouseEvent as ReactMouseEvent } from 'react';

interface EmptyStateProps {
  mode: ChatMode;
  workspacePath: string;
  modelStatus: ModelStatus | null;
  onSuggestionClick?: (text: string) => void;
}

const SUGGESTIONS: Record<ChatMode, string[]> = {
  chat: [
    'Explain this codebase structure',
    'Help me debug a failing test',
    'Summarize the last commit',
  ],
  agent: [
    'Fix the failing CI check',
    'Add a unit test for this module',
    'Refactor this file for clarity',
  ],
};

export function EmptyState({
  mode,
  workspacePath,
  modelStatus,
  onSuggestionClick,
}: EmptyStateProps) {
  const workspaceName = workspacePath.trim()
    ? workspacePath.trim().split('/').filter(Boolean).pop() || workspacePath.trim()
    : null;
  const model = modelStatus?.model_name?.split('/').pop() || modelStatus?.model_name || 'your model';
  const handleMouseDown = (event: ReactMouseEvent<HTMLDivElement>) => {
    void startWindowDrag(event);
  };

  return (
    <div
      data-tauri-drag-region
      onMouseDown={handleMouseDown}
      className="desktop-thread-column desktop-empty-drag-surface flex flex-1 flex-col items-center justify-center px-6 py-12 text-center"
    >
      <h1 className="text-[22px] font-semibold tracking-tight text-[var(--desktop-text-primary)]">
        {mode === 'agent' ? 'What should we build?' : 'How can I help?'}
      </h1>
      <p className="mt-2 max-w-sm text-sm leading-relaxed text-[var(--desktop-text-tertiary)]">
        {mode === 'agent'
          ? workspaceName
            ? `${workspaceName} · ${model}`
            : 'Choose a workspace in the sidebar, then describe a task.'
          : `Powered by ${model}.`}
      </p>

      <div className="mt-10 flex w-full max-w-lg flex-col gap-2">
        {SUGGESTIONS[mode].map((suggestion) => (
          <button
            key={suggestion}
            type="button"
            onClick={() => onSuggestionClick?.(suggestion)}
            className={cn(
              'desktop-no-drag ui-transition rounded-xl border border-[var(--desktop-border-subtle)] bg-[var(--desktop-hover)] px-4 py-3',
              'text-left text-[13px] text-[var(--desktop-text-secondary)] hover:border-[var(--desktop-border-strong)] hover:bg-[var(--desktop-hover)] hover:text-[var(--desktop-text-primary)]'
            )}
          >
            {suggestion}
          </button>
        ))}
      </div>

    </div>
  );
}
