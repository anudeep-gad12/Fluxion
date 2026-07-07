import type { CSSProperties } from 'react';

export interface EffortStop {
  value: string;
  label: string;
}

interface ReasoningEffortSliderProps {
  value: string;
  options: EffortStop[];
  onChange: (value: string) => void;
  ariaLabel: string;
}

/**
 * Stepped slider for thinking effort — snaps across the discrete effort stops
 * (Default → Low → Medium → High …). Tick labels are also clickable. Keyboard
 * arrows move between stops (native range behavior).
 */
export function ReasoningEffortSlider({
  value,
  options,
  onChange,
  ariaLabel,
}: ReasoningEffortSliderProps) {
  if (options.length === 0) return null;

  const foundIndex = options.findIndex((option) => option.value === value);
  const activeIndex = foundIndex < 0 ? 0 : foundIndex;
  const lastIndex = Math.max(1, options.length - 1);
  const fill = `${(activeIndex / lastIndex) * 100}%`;

  return (
    <div className="desktop-effort">
      <input
        type="range"
        className="desktop-effort-range ui-focus-ring"
        min={0}
        max={options.length - 1}
        step={1}
        value={activeIndex}
        aria-label={ariaLabel}
        aria-valuetext={options[activeIndex]?.label}
        onChange={(event) => onChange(options[Number(event.target.value)]?.value ?? '')}
        style={{ '--fill': fill } as CSSProperties}
      />
      <div className="desktop-effort-ticks">
        {options.map((option, index) => (
          <button
            key={option.value || 'default'}
            type="button"
            className="desktop-effort-tick"
            data-active={index === activeIndex ? 'true' : 'false'}
            onClick={() => onChange(option.value)}
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  );
}
