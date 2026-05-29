import type { MouseEvent as ReactMouseEvent } from 'react';

import { isLocalDesktopApp } from '@/lib/platform';

/** Elements that must not initiate a window drag. */
const DRAG_BLOCK_SELECTOR =
  '.desktop-no-drag, button, a, input, textarea, select, [role="button"], [contenteditable="true"]';

/**
 * Start native window drag (Tauri). Call from titlebar `onMouseDown`.
 * No-op in the browser; safe when not running inside the desktop shell.
 */
export async function startWindowDrag(event: ReactMouseEvent): Promise<void> {
  if (event.button !== 0) {
    return;
  }
  if (!isLocalDesktopApp()) {
    return;
  }
  const target = event.target as HTMLElement | null;
  if (target?.closest(DRAG_BLOCK_SELECTOR)) {
    return;
  }

  try {
    const { getCurrentWindow } = await import('@tauri-apps/api/window');
    await getCurrentWindow().startDragging();
  } catch {
    // Not in Tauri or capability missing — data-tauri-drag-region may still work.
  }
}
