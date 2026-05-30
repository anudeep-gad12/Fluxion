import { cn } from '@/lib/utils';

/** macOS app icon raster (from assets/macos/Fluxion.svg via sync_brand_assets). */
const APP_ICON_SRC = '/apple-touch-icon.png';

interface AppBrandIconProps {
  className?: string;
}

export function AppBrandIcon({ className }: AppBrandIconProps) {
  return (
    <img
      src={APP_ICON_SRC}
      alt=""
      className={cn('pointer-events-none shrink-0 rounded-[22%]', className)}
      width={28}
      height={28}
      aria-hidden
    />
  );
}
