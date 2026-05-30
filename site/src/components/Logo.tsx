interface LogoProps {
  size?: number;
  showWordmark?: boolean;
  className?: string;
}

/** Fluxion macOS app icon + optional wordmark. */
export function Logo({ size = 28, showWordmark = true, className = '' }: LogoProps) {
  return (
    <span className={`logoLockup ${className}`.trim()} style={{ display: 'inline-flex', alignItems: 'center', gap: showWordmark ? 10 : 0 }}>
      <img
        src="/logo-128.png"
        alt=""
        width={size}
        height={size}
        aria-hidden
        style={{ borderRadius: '22%', display: 'block' }}
      />
      {showWordmark ? <span>Fluxion</span> : null}
    </span>
  );
}
