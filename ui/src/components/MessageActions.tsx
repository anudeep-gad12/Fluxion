/**
 * Hover action bar for AI message responses.
 * Shows copy and retry buttons on hover.
 */

import { useState, useCallback } from 'react';
import { cn } from '@/lib/utils';

interface MessageActionsProps {
  /** The text content to copy (markdown/plain text) */
  content: string;
  /** Callback to retry the message (re-send the user's original prompt) */
  onRetry?: () => void;
  /** Whether retry is currently possible */
  canRetry?: boolean;
  /** Additional CSS classes */
  className?: string;
}

export function MessageActions({
  content,
  onRetry,
  canRetry = true,
  className,
}: MessageActionsProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(() => {
    if (!content) return;
    navigator.clipboard.writeText(content).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, [content]);

  return (
    <div
      className={cn(
        'ui-transition flex items-center gap-1.5 font-mono text-[11px] opacity-0 group-hover/msg:opacity-100',
        className,
      )}
    >
      <button
        onClick={handleCopy}
        className="ui-transition ui-focus-ring rounded-md border border-transparent px-2 py-1 text-zinc-300 hover:border-cyan-500/30 hover:bg-cyan-500/[0.08] hover:text-cyan-100"
        title="Copy response"
      >
        {copied ? '✓ copied' : 'copy'}
      </button>
      {onRetry && (
        <button
          onClick={onRetry}
          disabled={!canRetry}
          className={cn(
            'ui-transition ui-focus-ring rounded-md border px-2 py-1',
            canRetry
              ? 'border-transparent text-zinc-300 hover:border-cyan-500/30 hover:bg-cyan-500/[0.08] hover:text-cyan-100'
              : 'border-transparent text-zinc-600 cursor-not-allowed',
          )}
          title={canRetry ? 'Retry this message' : 'Cannot retry during active run'}
        >
          retry
        </button>
      )}
    </div>
  );
}
