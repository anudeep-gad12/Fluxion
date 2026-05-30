import { cn } from '@/lib/utils';
import appIconUrl from '@/assets/app-icon.png';

interface AppBrandIconProps {
  className?: string;
}

/** macOS app icon raster — bundled by Vite so packaged static serving cannot break the path. */
export function AppBrandIcon({ className }: AppBrandIconProps) {
  return (
    <img
      src={appIconUrl}
      alt=""
      className={cn('pointer-events-none shrink-0 rounded-[22%]', className)}
      width={28}
      height={28}
      aria-hidden
    />
  );
}
