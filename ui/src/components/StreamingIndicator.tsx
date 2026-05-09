/**
 * Streaming state indicators.
 * - ShimmerSkeleton: shown while waiting for first token
 * - ThinkingTimer: shown during thinking phase with elapsed time
 */

import { useState, useEffect, useRef } from 'react';
import { cn } from '@/lib/utils';

type AccentTone = 'cyan' | 'sky' | 'amber' | 'emerald';

const ACCENT_STYLES: Record<AccentTone, {
  dot: string;
  text: string;
  chip: string;
  line: string;
}> = {
  cyan: {
    dot: 'bg-cyan-400',
    text: 'text-cyan-200',
    chip: 'border-cyan-500/18 bg-cyan-500/[0.08] text-cyan-100',
    line: 'from-cyan-500/0 via-cyan-400/35 to-cyan-500/0',
  },
  sky: {
    dot: 'bg-sky-400',
    text: 'text-sky-200',
    chip: 'border-sky-500/18 bg-sky-500/[0.08] text-sky-100',
    line: 'from-sky-500/0 via-sky-400/35 to-sky-500/0',
  },
  amber: {
    dot: 'bg-amber-400',
    text: 'text-amber-200',
    chip: 'border-amber-500/18 bg-amber-500/[0.08] text-amber-100',
    line: 'from-amber-500/0 via-amber-400/35 to-amber-500/0',
  },
  emerald: {
    dot: 'bg-emerald-400',
    text: 'text-emerald-200',
    chip: 'border-emerald-500/18 bg-emerald-500/[0.08] text-emerald-100',
    line: 'from-emerald-500/0 via-emerald-400/35 to-emerald-500/0',
  },
};

interface ShimmerSkeletonProps {
  label?: string;
  summary?: string;
  startedAt?: string;
  accent?: AccentTone;
}

/** Shimmer loading skeleton shown before first token arrives */
export function ShimmerSkeleton({
  label = 'thinking',
  summary = 'Working through the run and waiting for the first visible output.',
  startedAt,
  accent = 'cyan',
}: ShimmerSkeletonProps) {
  const [elapsed, setElapsed] = useState(0);
  const startRef = useRef<number | null>(startedAt ? new Date(startedAt).getTime() : null);

  useEffect(() => {
    startRef.current = startedAt ? new Date(startedAt).getTime() : Date.now();
    setElapsed(Math.max(0, Math.floor((Date.now() - startRef.current) / 1000)));
  }, [startedAt]);

  useEffect(() => {
    const interval = window.setInterval(() => {
      if (!startRef.current) {
        startRef.current = Date.now();
      }
      setElapsed(Math.max(0, Math.floor((Date.now() - startRef.current) / 1000)));
    }, 1000);
    return () => window.clearInterval(interval);
  }, []);

  const accentStyles = ACCENT_STYLES[accent];

  return (
    <div className="overflow-hidden rounded-[1rem] border border-zinc-800/90 bg-zinc-950/70">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-900/90 px-4 py-3 font-mono text-[11px]">
        <div className="flex min-w-0 items-center gap-2">
          <span className={cn('inline-flex h-2 w-2 rounded-full animate-pulse', accentStyles.dot)} />
          <span className={cn('uppercase tracking-[0.18em]', accentStyles.text)}>{label}</span>
          <span className="text-zinc-700">/</span>
          <span className="truncate text-zinc-400">live run</span>
        </div>
        <div className={cn('rounded-full border px-2.5 py-1 tabular-nums', accentStyles.chip)}>
          {elapsed}s
        </div>
      </div>

      <div className="space-y-4 px-4 py-4">
        <div className="space-y-2">
          <p className="text-[14px] leading-7 text-zinc-100">{summary}</p>
          <div className={cn('h-px w-full bg-gradient-to-r', accentStyles.line)} />
        </div>

        <div className="space-y-2">
          <div className="h-2.5 w-[78%] rounded-full bg-zinc-900 shimmer" />
          <div className="h-2.5 w-[62%] rounded-full bg-zinc-900 shimmer" />
          <div className="h-2.5 w-[70%] rounded-full bg-zinc-900 shimmer" />
        </div>

        <div className="flex flex-wrap gap-2 font-mono text-[10px] uppercase tracking-[0.16em] text-zinc-500">
          <span className="rounded-full border border-zinc-800/90 bg-zinc-950 px-2 py-1">waiting for first token</span>
          <span className="rounded-full border border-zinc-800/90 bg-zinc-950 px-2 py-1">stream pending</span>
        </div>
      </div>
    </div>
  );
}

/** Thinking timer with elapsed seconds */
export function ThinkingTimer({ label }: { label?: string }) {
  const [elapsed, setElapsed] = useState(0);
  const startRef = useRef(Date.now());

  useEffect(() => {
    startRef.current = Date.now();
    const interval = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startRef.current) / 1000));
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="flex items-center gap-2 py-1 text-[11px] font-mono text-zinc-300">
      <span className="inline-block h-1.5 w-1.5 rounded-full bg-zinc-300 animate-pulse" />
      <span>{label || 'Thinking'}</span>
      <span className="tabular-nums text-zinc-500">{elapsed}s</span>
    </div>
  );
}
