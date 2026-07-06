import {
  cloneElement,
  isValidElement,
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type ReactElement,
  type ReactNode,
  type Ref,
} from 'react';
import { createPortal } from 'react-dom';

type Side = 'top' | 'bottom' | 'left' | 'right';
type Align = 'start' | 'center' | 'end';

interface TooltipProps {
  content: ReactNode;
  /** Keyboard hint rendered as a kbd chip, e.g. "⌘↵" */
  shortcut?: string;
  side?: Side;
  align?: Align;
  delay?: number;
  disabled?: boolean;
  children: ReactElement;
}

const GUTTER = 8;
const GAP = 7;
const WARM_WINDOW_MS = 500;

// macOS-style warm-up: once one tooltip has shown, neighbours open instantly.
let lastCloseAt = 0;

function assignRef(ref: Ref<HTMLElement> | undefined, node: HTMLElement | null) {
  if (typeof ref === 'function') ref(node);
  else if (ref && typeof ref === 'object') {
    (ref as { current: HTMLElement | null }).current = node;
  }
}

export function Tooltip({
  content,
  shortcut,
  side = 'top',
  align = 'center',
  delay = 300,
  disabled = false,
  children,
}: TooltipProps) {
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState({ left: 0, top: 0, arrowOffset: 0 });
  const triggerRef = useRef<HTMLElement | null>(null);
  const surfaceRef = useRef<HTMLDivElement | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const tooltipId = useId();

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const show = useCallback(() => {
    if (disabled) return;
    clearTimer();
    const warm = Date.now() - lastCloseAt < WARM_WINDOW_MS;
    if (warm) {
      setOpen(true);
    } else {
      timerRef.current = setTimeout(() => setOpen(true), delay);
    }
  }, [clearTimer, delay, disabled]);

  const hide = useCallback(() => {
    clearTimer();
    setOpen((current) => {
      if (current) lastCloseAt = Date.now();
      return false;
    });
  }, [clearTimer]);

  useEffect(() => clearTimer, [clearTimer]);
  useEffect(() => {
    if (disabled) hide();
  }, [disabled, hide]);

  // Position after render so the surface can be measured.
  useLayoutEffect(() => {
    if (!open) return;
    const trigger = triggerRef.current;
    const surface = surfaceRef.current;
    if (!trigger || !surface) return;
    const t = trigger.getBoundingClientRect();
    const s = surface.getBoundingClientRect();

    let left: number;
    let top: number;
    if (side === 'top' || side === 'bottom') {
      left =
        align === 'start' ? t.left : align === 'end' ? t.right - s.width : t.left + t.width / 2 - s.width / 2;
      top = side === 'top' ? t.top - s.height - GAP : t.bottom + GAP;
    } else {
      left = side === 'left' ? t.left - s.width - GAP : t.right + GAP;
      top = t.top + t.height / 2 - s.height / 2;
    }
    left = Math.min(Math.max(GUTTER, left), window.innerWidth - s.width - GUTTER);
    top = Math.min(Math.max(GUTTER, top), window.innerHeight - s.height - GUTTER);

    // Arrow tracks the trigger centre even when the surface is clamped.
    const arrowOffset =
      side === 'top' || side === 'bottom'
        ? Math.min(Math.max(10, t.left + t.width / 2 - left), s.width - 10)
        : Math.min(Math.max(10, t.top + t.height / 2 - top), s.height - 10);

    setPosition({ left, top, arrowOffset });
  }, [align, open, side]);

  useEffect(() => {
    if (!open) return;
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') hide();
    };
    document.addEventListener('keydown', handleEscape);
    window.addEventListener('resize', hide);
    window.addEventListener('scroll', hide, true);
    return () => {
      document.removeEventListener('keydown', handleEscape);
      window.removeEventListener('resize', hide);
      window.removeEventListener('scroll', hide, true);
    };
  }, [hide, open]);

  if (!isValidElement(children)) return children;
  const childProps = children.props as Record<string, unknown>;

  const trigger = cloneElement(children, {
    ref: (node: HTMLElement | null) => {
      triggerRef.current = node;
      assignRef((children as ReactElement & { ref?: Ref<HTMLElement> }).ref, node);
    },
    'aria-describedby': open ? tooltipId : (childProps['aria-describedby'] as string | undefined),
    onMouseEnter: (event: React.MouseEvent) => {
      (childProps.onMouseEnter as ((e: React.MouseEvent) => void) | undefined)?.(event);
      show();
    },
    onMouseLeave: (event: React.MouseEvent) => {
      (childProps.onMouseLeave as ((e: React.MouseEvent) => void) | undefined)?.(event);
      hide();
    },
    onFocus: (event: React.FocusEvent) => {
      (childProps.onFocus as ((e: React.FocusEvent) => void) | undefined)?.(event);
      show();
    },
    onBlur: (event: React.FocusEvent) => {
      (childProps.onBlur as ((e: React.FocusEvent) => void) | undefined)?.(event);
      hide();
    },
    onMouseDown: (event: React.MouseEvent) => {
      (childProps.onMouseDown as ((e: React.MouseEvent) => void) | undefined)?.(event);
      hide();
    },
  } as never);

  return (
    <>
      {trigger}
      {open
        ? createPortal(
            <div
              ref={surfaceRef}
              id={tooltipId}
              role="tooltip"
              className="ui-tooltip"
              data-side={side}
              style={
                {
                  left: position.left,
                  top: position.top,
                  '--tooltip-arrow-offset': `${position.arrowOffset}px`,
                } as React.CSSProperties
              }
            >
              {content}
              {shortcut ? <kbd className="ui-tooltip-kbd">{shortcut}</kbd> : null}
              <span className="ui-tooltip-arrow" aria-hidden />
            </div>,
            document.body,
          )
        : null}
    </>
  );
}
