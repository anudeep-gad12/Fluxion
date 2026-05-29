import { cn } from '@/lib/utils';
import { isLocalDesktopApp } from '@/lib/platform';
import type { ModelStatus } from '@/api/client';
import type { ChatMode } from './ConversationToolbar';

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
  const desktop = isLocalDesktopApp();
  const workspaceName = workspacePath.trim()
    ? workspacePath.trim().split('/').filter(Boolean).pop() || workspacePath.trim()
    : null;
  const model = modelStatus?.model_name?.split('/').pop() || modelStatus?.model_name || 'your model';

  return (
    <div className="desktop-thread-column flex flex-1 flex-col items-center justify-center px-6 py-12 text-center">
      <h1 className="text-[22px] font-semibold tracking-tight text-zinc-50">
        {mode === 'agent' ? 'What should we build?' : 'How can I help?'}
      </h1>
      <p className="mt-2 max-w-sm text-[14px] leading-relaxed text-zinc-500">
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
              'ui-transition rounded-xl border border-white/[0.06] bg-white/[0.02] px-4 py-3',
              'text-left text-[13px] text-zinc-300 hover:border-white/10 hover:bg-white/[0.04] hover:text-zinc-100'
            )}
          >
            {suggestion}
          </button>
        ))}
      </div>

      {!desktop && (
        <p className="mt-10 text-[12px] text-zinc-600">
          <kbd className="rounded border border-white/10 bg-white/[0.03] px-1.5 py-0.5 font-sans text-zinc-500">
            ⌘
          </kbd>
          <span className="mx-1">+</span>
          <kbd className="rounded border border-white/10 bg-white/[0.03] px-1.5 py-0.5 font-sans text-zinc-500">
            Enter
          </kbd>
          <span className="ml-2">to send</span>
        </p>
      )}
    </div>
  );
}
