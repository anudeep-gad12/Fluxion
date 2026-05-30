import { AppBrandIcon } from '@/components/AppBrandIcon';
import { cn } from '@/lib/utils';

interface DesktopSidebarBrandProps {
  collapsed: boolean;
}

/** Fluxion mark + wordmark; wordmark fades out when the sidebar is collapsed. */
export function DesktopSidebarBrand({ collapsed }: DesktopSidebarBrandProps) {
  return (
    <div
      className={cn(
        'desktop-sidebar-brand flex items-center',
        collapsed ? 'justify-center' : 'min-w-0 flex-1 gap-2.5'
      )}
    >
      <AppBrandIcon className="desktop-sidebar-brand-logo h-7 w-7" />
      <span
        className={cn(
          'desktop-sidebar-brand-name pointer-events-none truncate text-[15px] font-semibold tracking-tight text-zinc-50',
          collapsed && 'desktop-sidebar-brand-name-collapsed'
        )}
      >
        Fluxion
      </span>
    </div>
  );
}
