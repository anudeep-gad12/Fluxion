import { flushSync } from 'react-dom';

/**
 * Run a DOM-updating callback inside a native View Transition so the change
 * crossfades instead of hard-cutting. Used for conversation-to-conversation
 * swaps (this app uses classic BrowserRouter, so react-router's own
 * `viewTransition` option is a no-op — we drive the API directly).
 *
 * Degrades to a plain synchronous update when the API is unavailable or the
 * user prefers reduced motion. flushSync forces React to commit the update
 * inside the transition callback so the browser can snapshot before/after.
 */
export function withViewTransition(update: () => void): void {
  const prefersReduced =
    typeof window !== 'undefined' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const startViewTransition = (
    document as Document & {
      startViewTransition?: (cb: () => void) => unknown;
    }
  ).startViewTransition;

  if (prefersReduced || typeof startViewTransition !== 'function') {
    update();
    return;
  }

  startViewTransition.call(document, () => {
    flushSync(update);
  });
}
