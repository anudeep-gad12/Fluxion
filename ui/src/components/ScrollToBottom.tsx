/**
 * "↓ New content" pill that appears when user scrolls up during streaming.
 * Clicking scrolls smoothly to the bottom.
 */

import { useState, useEffect, useCallback, type RefObject } from 'react';
import { cn } from '@/lib/utils';

interface ScrollToBottomProps {
  scrollRef: RefObject<HTMLDivElement | null>;
  /** Whether there's active streaming content */
  isStreaming: boolean;
  className?: string;
}

export function ScrollToBottom({ scrollRef, isStreaming, className }: ScrollToBottomProps) {
  const [showPill, setShowPill] = useState(false);

  // Track whether user is near the bottom
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;

    const handleScroll = () => {
      const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 150;
      setShowPill(!isNearBottom && isStreaming);
    };

    el.addEventListener('scroll', handleScroll, { passive: true });
    return () => el.removeEventListener('scroll', handleScroll);
  }, [scrollRef, isStreaming]);

  // Hide when streaming stops
  useEffect(() => {
    if (!isStreaming) setShowPill(false);
  }, [isStreaming]);

  const scrollToBottom = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
    setShowPill(false);
  }, [scrollRef]);

  if (!showPill) return null;

  return (
    <button
      onClick={scrollToBottom}
      className={cn(
        'ui-transition ui-focus-ring fixed z-30 rounded-full border border-cyan-500/28 bg-zinc-950/94 px-3.5 py-2 text-[11px] font-mono text-cyan-100 backdrop-blur-sm',
        'hover:border-cyan-400/40 hover:bg-cyan-500/[0.08] animate-in fade-in slide-in-from-bottom-2 duration-200',
        'shadow-[0_18px_40px_rgba(0,0,0,0.35)]',
        className,
      )}
    >
      ↓ New content
    </button>
  );
}
