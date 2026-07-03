/**
 * Braille running indicator — the classic terminal spinner
 * (⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏) with an accent glow while active.
 * Freezes to a dim solid cell (⠿) when inactive.
 * Honors prefers-reduced-motion by not cycling frames.
 */

import { useEffect, useState } from 'react';

const FRAMES = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'];
const IDLE_GLYPH = '⠿';
const FRAME_MS = 80;

export function BrailleSpinner({ active = true }: { active?: boolean }) {
  const [frame, setFrame] = useState(0);

  useEffect(() => {
    if (!active) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const interval = window.setInterval(() => {
      setFrame((current) => (current + 1) % FRAMES.length);
    }, FRAME_MS);
    return () => window.clearInterval(interval);
  }, [active]);

  return (
    <span className="tr-spinner" data-active={active ? 'true' : 'false'} aria-hidden>
      {active ? FRAMES[frame] : IDLE_GLYPH}
    </span>
  );
}
