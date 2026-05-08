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
        'flex items-center gap-1 font-mono text-xs opacity-0 group-hover/msg:opacity-100 transition-opacity',
        className,
      )}
    >
      <button
        onClick={handleCopy}
        className="px-1.5 py-0.5 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-700/80 transition-colors"
        title="Copy response"
      >
        {copied ? '✓ copied' : 'copy'}
      </button>
      {onRetry && (
        <button
          onClick={onRetry}
          disabled={!canRetry}
          className={cn(
            'px-1.5 py-0.5 transition-colors',
            canRetry
              ? 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-700/80'
              : 'text-zinc-600 cursor-not-allowed',
          )}
          title={canRetry ? 'Retry this message' : 'Cannot retry during active run'}
        >
          retry
        </button>
      )}
    </div>
  );
}
