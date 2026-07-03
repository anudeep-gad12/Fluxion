/**
 * Comet arc ring — the app's running indicator.
 *
 * A conic-gradient arc with a fading tail, spun purely in CSS
 * (see `.tr-comet` in styles/transcript.css). Inactive renders
 * a frozen neutral ring.
 */

export function CometSpinner({ active = true }: { active?: boolean }) {
  return <span className="tr-comet" data-active={active ? 'true' : 'false'} aria-hidden />;
}
