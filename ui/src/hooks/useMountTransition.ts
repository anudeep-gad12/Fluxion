import { useEffect, useRef, useState } from 'react';

/**
 * Keeps a surface mounted for a short window after `open` flips false, so an
 * exit animation can play before the node unmounts. Pairs with the ui-pop-in /
 * ui-pop-out keyframes: render nothing when `mounted` is false, and apply the
 * closing style when `closing` is true.
 *
 * @param open       Whether the surface should be visible.
 * @param exitMs     How long the exit animation runs before unmount (default 140ms, --duration-fast).
 */
export function useMountTransition(open: boolean, exitMs = 140): {
  mounted: boolean;
  closing: boolean;
} {
  const [mounted, setMounted] = useState(open);
  const [closing, setClosing] = useState(false);
  const timer = useRef<number | null>(null);

  useEffect(() => {
    if (timer.current) {
      window.clearTimeout(timer.current);
      timer.current = null;
    }

    if (open) {
      setMounted(true);
      setClosing(false);
      return;
    }

    if (!mounted) return;

    // Closing: play the exit animation, then unmount.
    setClosing(true);
    timer.current = window.setTimeout(() => {
      setMounted(false);
      setClosing(false);
      timer.current = null;
    }, exitMs);

    return () => {
      if (timer.current) {
        window.clearTimeout(timer.current);
        timer.current = null;
      }
    };
  }, [open, exitMs, mounted]);

  return { mounted, closing };
}
