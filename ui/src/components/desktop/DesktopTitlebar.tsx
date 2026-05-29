import type { MouseEvent as ReactMouseEvent, ReactNode } from 'react';

import { startWindowDrag } from '@/lib/windowDrag';
import { cn } from '@/lib/utils';

interface DesktopTitlebarProps {
  children: ReactNode;
  className?: string;
  /** Apply macOS traffic-light left inset (leftmost column only). */
  safeLeft?: boolean;
}

/**
 * Unified desktop titlebar: Tauri drag region + programmatic startDragging fallback.
 * Interactive controls inside must use `desktop-no-drag`.
 */
export function DesktopTitlebar({ children, className, safeLeft = false }: DesktopTitlebarProps) {
  const handleMouseDown = (event: ReactMouseEvent<HTMLElement>) => {
    void startWindowDrag(event);
  };

  return (
    <header
      data-tauri-drag-region
      onMouseDown={handleMouseDown}
      className={cn(
        'relative flex-shrink-0 select-none',
        safeLeft && 'desktop-titlebar-safe-left',
        className
      )}
    >
      {children}
    </header>
  );
}
