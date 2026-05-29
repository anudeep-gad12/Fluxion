import { cn } from '@/lib/utils';

export interface DesktopTextOption<T extends string> {
  value: T;
  label: string;
  disabled?: boolean;
}

interface DesktopTextOptionGroupProps<T extends string> {
  value: T;
  options: DesktopTextOption<T>[];
  onChange: (value: T) => void;
  ariaLabel: string;
  className?: string;
}

/** Inline text options (Agent · Chat style) for settings panels. */
export function DesktopTextOptionGroup<T extends string>({
  value,
  options,
  onChange,
  ariaLabel,
  className,
}: DesktopTextOptionGroupProps<T>) {
  return (
    <div
      className={cn('desktop-mode-switch', className)}
      role="radiogroup"
      aria-label={ariaLabel}
    >
      {options.map((option, index) => (
        <span key={option.value} className="inline-flex items-center">
          {index > 0 ? (
            <span className="desktop-mode-switch-sep" aria-hidden>
              ·
            </span>
          ) : null}
          <button
            type="button"
            role="radio"
            aria-checked={value === option.value}
            data-active={value === option.value ? 'true' : 'false'}
            disabled={option.disabled}
            onClick={() => onChange(option.value)}
            className="desktop-mode-switch-option capitalize"
          >
            {option.label}
          </button>
        </span>
      ))}
    </div>
  );
}
