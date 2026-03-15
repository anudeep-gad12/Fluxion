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
        'fixed z-30 px-3 py-1.5 bg-zinc-800 border border-zinc-600 text-zinc-300 text-xs font-mono',
        'hover:bg-zinc-700 transition-all animate-in fade-in slide-in-from-bottom-2',
        'shadow-lg',
        className,
      )}
    >
      ↓ New content
    </button>
  );
}
