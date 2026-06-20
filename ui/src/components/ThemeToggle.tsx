import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { createPortal } from 'react-dom';
import { Check, Monitor, Moon, Sun, type LucideIcon } from 'lucide-react';
import { useTheme, type ThemePreference } from '@/hooks/useTheme';
import { cn } from '@/lib/utils';

const OPTIONS: Array<{ value: ThemePreference; label: string; icon: LucideIcon }> = [
  { value: 'light', label: 'Light', icon: Sun },
  { value: 'dark', label: 'Dark', icon: Moon },
  { value: 'system', label: 'System', icon: Monitor },
];

export function ThemeToggle({
  className,
  menuAlign = 'right',
}: {
  className?: string;
  menuAlign?: 'left' | 'right';
}) {
  const { preference, setPreference } = useTheme();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const optionRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const [menuPosition, setMenuPosition] = useState({ left: 0, top: 0 });
  const activeIndex = OPTIONS.findIndex((option) => option.value === preference);
  const TriggerIcon = OPTIONS[activeIndex]?.icon ?? Monitor;

  useEffect(() => {
    if (!open) return;
    const triggerRect = triggerRef.current?.getBoundingClientRect();
    if (triggerRect) {
      const menuWidth = 148;
      const preferredLeft = menuAlign === 'left' ? triggerRect.left : triggerRect.right - menuWidth;
      setMenuPosition({
        left: Math.min(Math.max(8, preferredLeft), window.innerWidth - menuWidth - 8),
        top: triggerRect.bottom + 6,
      });
    }
    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (!rootRef.current?.contains(target) && !menuRef.current?.contains(target)) setOpen(false);
    };
    const handleEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      setOpen(false);
      triggerRef.current?.focus();
    };
    const handleDismiss = () => setOpen(false);
    document.addEventListener('mousedown', handlePointerDown);
    document.addEventListener('keydown', handleEscape);
    window.addEventListener('resize', handleDismiss);
    window.addEventListener('scroll', handleDismiss, true);
    requestAnimationFrame(() => optionRefs.current[activeIndex]?.focus());
    return () => {
      document.removeEventListener('mousedown', handlePointerDown);
      document.removeEventListener('keydown', handleEscape);
      window.removeEventListener('resize', handleDismiss);
      window.removeEventListener('scroll', handleDismiss, true);
    };
  }, [activeIndex, menuAlign, open]);

  const handleMenuKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const currentIndex = optionRefs.current.findIndex((option) => option === document.activeElement);
    let nextIndex: number | null = null;
    if (event.key === 'ArrowDown') nextIndex = (currentIndex + 1 + OPTIONS.length) % OPTIONS.length;
    if (event.key === 'ArrowUp') nextIndex = (currentIndex - 1 + OPTIONS.length) % OPTIONS.length;
    if (event.key === 'Home') nextIndex = 0;
    if (event.key === 'End') nextIndex = OPTIONS.length - 1;
    if (nextIndex === null) return;
    event.preventDefault();
    optionRefs.current[nextIndex]?.focus();
  };

  return (
    <div ref={rootRef} className={cn('desktop-theme-menu-root desktop-no-drag', className)}>
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen((current) => !current)}
        onKeyDown={(event) => {
          if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return;
          event.preventDefault();
          setOpen(true);
        }}
        className="desktop-theme-toggle"
        aria-label={`Theme: ${OPTIONS[activeIndex]?.label ?? 'System'}`}
        aria-haspopup="menu"
        aria-expanded={open}
        title="Theme"
      >
        <TriggerIcon className="h-4 w-4" aria-hidden />
      </button>
      {open ? createPortal(
        <div
          ref={menuRef}
          className="desktop-theme-menu"
          role="menu"
          aria-label="Theme"
          onKeyDown={handleMenuKeyDown}
          style={menuPosition}
        >
          {OPTIONS.map((option, index) => {
            const Icon = option.icon;
            const selected = option.value === preference;
            return (
              <button
                key={option.value}
                ref={(node) => { optionRefs.current[index] = node; }}
                type="button"
                role="menuitemradio"
                aria-checked={selected}
                tabIndex={selected ? 0 : -1}
                className="desktop-theme-option"
                data-selected={selected ? 'true' : 'false'}
                onClick={() => {
                  setPreference(option.value);
                  setOpen(false);
                  triggerRef.current?.focus();
                }}
              >
                <Icon className="h-4 w-4" aria-hidden />
                <span>{option.label}</span>
                <Check className="desktop-theme-option-check h-3.5 w-3.5" aria-hidden />
              </button>
            );
          })}
        </div>,
        document.body,
      ) : null}
    </div>
  );
}
