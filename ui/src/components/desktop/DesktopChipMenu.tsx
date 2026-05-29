import { useEffect, useRef, useState, type ReactNode } from 'react';
import { ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils';

interface DesktopChipMenuOption {
  value: string;
  label: string;
}

interface DesktopChipMenuProps {
  label: string;
  value: string;
  options: DesktopChipMenuOption[];
  onChange: (value: string) => void;
  className?: string;
}

export function DesktopChipMenu({
  label,
  value,
  options,
  onChange,
  className,
}: DesktopChipMenuProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handlePointerDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handlePointerDown);
    return () => document.removeEventListener('mousedown', handlePointerDown);
  }, [open]);

  const active = options.find((option) => option.value === value);

  return (
    <div ref={rootRef} className={cn('relative', className)}>
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        className="desktop-chip max-w-[9rem]"
        title={label}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <span className="truncate">{active?.label ?? value}</span>
        <ChevronDown className="h-3 w-3 shrink-0 opacity-50" />
      </button>
      {open ? (
        <div
          className="absolute bottom-full left-0 z-50 mb-1 min-w-[8rem] overflow-hidden rounded-lg border border-white/10 bg-[#1c1c1f] py-1 shadow-lg"
          role="listbox"
        >
          {options.map((option) => (
            <button
              key={option.value}
              type="button"
              role="option"
              aria-selected={option.value === value}
              onClick={() => {
                onChange(option.value);
                setOpen(false);
              }}
              className={cn(
                'block w-full px-3 py-1.5 text-left text-[11px] text-zinc-300 hover:bg-white/[0.06]',
                option.value === value && 'bg-white/[0.06] text-zinc-100'
              )}
            >
              {option.label}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

interface DesktopChipButtonProps {
  children: ReactNode;
  onClick?: () => void;
  active?: boolean;
  title?: string;
  className?: string;
}

export function DesktopChipButton({
  children,
  onClick,
  active = false,
  title,
  className,
}: DesktopChipButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      data-active={active ? 'true' : 'false'}
      className={cn('desktop-chip', className)}
    >
      {children}
    </button>
  );
}
