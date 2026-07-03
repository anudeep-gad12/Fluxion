/**
 * Claude-Code-style transcript primitives.
 *
 * Line grammar: a marker column (⏺ action / ⎿ result / > user) + body.
 * Markers carry status color; bodies stay neutral.
 */

import { useState } from 'react';
import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

export type MarkerTone =
  | 'default'
  | 'pending'
  | 'running'
  | 'success'
  | 'error'
  | 'system'
  | 'steer';

export function MarkerLine({
  marker = '⏺',
  tone = 'default',
  mono = false,
  className,
  children,
}: {
  marker?: ReactNode;
  tone?: MarkerTone;
  mono?: boolean;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div className={cn('tr-line', className)}>
      <span className="tr-marker" data-tone={tone} aria-hidden>
        {marker}
      </span>
      <div className={cn('tr-body', mono ? 'tr-mono' : 'tr-prose')}>{children}</div>
    </div>
  );
}

/** Indented `⎿` continuation row under a marker line. */
export function ResultBlock({
  className,
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return (
    <div className={cn('tr-result', className)}>
      <span className="tr-result-marker" aria-hidden>
        ⎿
      </span>
      <div className="tr-result-body">{children}</div>
    </div>
  );
}

/** Plain text clamped to `maxLines` newline-lines with an `… +N lines` expander. */
export function ClampedText({
  text,
  maxLines = 3,
  className,
}: {
  text: string;
  maxLines?: number;
  className?: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const trimmed = text.replace(/\s+$/, '');
  const lines = trimmed.split('\n');
  const overflow = lines.length - maxLines;
  const clamped = overflow > 0 && !expanded;
  const visible = clamped ? lines.slice(0, maxLines).join('\n') : trimmed;

  return (
    <div className={cn('min-w-0', className)}>
      <pre className="tr-pre">{visible}</pre>
      {overflow > 0 && (
        <button
          type="button"
          className="tr-more"
          onClick={() => setExpanded((current) => !current)}
        >
          {clamped ? `… +${overflow} lines` : 'collapse'}
        </button>
      )}
    </div>
  );
}
