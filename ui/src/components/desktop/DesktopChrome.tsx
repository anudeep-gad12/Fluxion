import { DesktopTitlebar } from '@/components/desktop/DesktopTitlebar';

interface DesktopChromeProps {
  title: string;
  mergeTitlebar?: boolean;
}

export function DesktopChrome({ title, mergeTitlebar = false }: DesktopChromeProps) {
  if (!mergeTitlebar) {
    return (
      <header className="desktop-chrome desktop-chrome-scrim flex h-11 flex-shrink-0 items-center justify-center border-b border-white/[0.05] px-4">
        <p className="min-w-0 truncate text-[13px] text-zinc-500">{title || 'New chat'}</p>
      </header>
    );
  }

  return (
    <DesktopTitlebar
      className="desktop-chrome desktop-chrome-scrim flex h-[var(--titlebar-height)] items-center justify-center border-b border-white/[0.05] px-4"
    >
      <p className="pointer-events-none min-w-0 truncate text-[13px] font-medium text-zinc-400">
        {title || 'New chat'}
      </p>
    </DesktopTitlebar>
  );
}
