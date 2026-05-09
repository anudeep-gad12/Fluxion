/**
 * Streaming state indicators.
 * - ShimmerSkeleton: shown while waiting for first token
 * - ThinkingTimer: shown during thinking phase with elapsed time
 */

import { useState, useEffect, useRef } from 'react';

/** Shimmer loading skeleton shown before first token arrives */
export function ShimmerSkeleton() {
  return (
    <div className="space-y-3 py-2">
      <div className="h-3 w-[82%] rounded-full bg-zinc-800 shimmer" />
      <div className="h-3 w-[58%] rounded-full bg-zinc-800 shimmer" />
      <div className="h-3 w-[76%] rounded-full bg-zinc-800 shimmer" />
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
