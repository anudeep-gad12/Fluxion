import { DesktopTitlebar } from '@/components/desktop/DesktopTitlebar';

interface DesktopChromeProps {
  title: string;
  mergeTitlebar?: boolean;
}

export function DesktopChrome({ title, mergeTitlebar = false }: DesktopChromeProps) {
  if (!mergeTitlebar) {
    return (
      <header className="desktop-chrome desktop-chrome-scrim flex flex-shrink-0 items-center justify-start border-b border-[var(--desktop-border-subtle)] px-4">
        <p className="desktop-chrome-title">{title || 'New chat'}</p>
      </header>
    );
  }

  return (
    <DesktopTitlebar
      className="desktop-chrome desktop-chrome-scrim flex items-center justify-start border-b border-[var(--desktop-border-subtle)] px-4"
    >
      <p className="desktop-chrome-title pointer-events-none">
        {title || 'New chat'}
      </p>
    </DesktopTitlebar>
  );
}
