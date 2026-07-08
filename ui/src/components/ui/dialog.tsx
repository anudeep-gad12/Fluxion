import * as React from "react";
import { createPortal } from "react-dom";
import { cn } from "@/lib/utils";
import { useMountTransition } from "@/hooks/useMountTransition";
import { Button } from "./button";

interface DialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    children: React.ReactNode;
    className?: string;
}

const FOCUSABLE_SELECTOR =
    'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function Dialog({ open, onOpenChange, children, className }: DialogProps) {
    const surfaceRef = React.useRef<HTMLDivElement>(null);
    const restoreFocusRef = React.useRef<HTMLElement | null>(null);
    const { mounted, closing } = useMountTransition(open);

    // Escape closes; Tab cycles focus inside the surface.
    React.useEffect(() => {
        if (!open) return;
        const handleKeyDown = (event: KeyboardEvent) => {
            if (event.key === "Escape") {
                event.stopPropagation();
                onOpenChange(false);
                return;
            }
            if (event.key !== "Tab") return;
            const surface = surfaceRef.current;
            if (!surface) return;
            const focusable = Array.from(
                surface.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)
            ).filter((el) => el.offsetParent !== null);
            if (focusable.length === 0) {
                event.preventDefault();
                return;
            }
            const first = focusable[0];
            const last = focusable[focusable.length - 1];
            const active = document.activeElement as HTMLElement | null;
            if (event.shiftKey && (active === first || !surface.contains(active))) {
                event.preventDefault();
                last.focus();
            } else if (!event.shiftKey && (active === last || !surface.contains(active))) {
                event.preventDefault();
                first.focus();
            }
        };
        document.addEventListener("keydown", handleKeyDown);
        return () => document.removeEventListener("keydown", handleKeyDown);
    }, [open, onOpenChange]);

    // Move focus into the dialog on open; restore it on close.
    React.useEffect(() => {
        if (!open) return;
        restoreFocusRef.current = document.activeElement as HTMLElement | null;
        const surface = surfaceRef.current;
        const firstFocusable = surface?.querySelector<HTMLElement>(FOCUSABLE_SELECTOR);
        (firstFocusable ?? surface)?.focus?.();
        return () => {
            restoreFocusRef.current?.focus?.();
            restoreFocusRef.current = null;
        };
    }, [open]);

    if (!mounted) return null;
    if (typeof document === "undefined") return null;

    // Portal to <body> so the fixed overlay escapes the desktop-shell-main
    // stacking context (view-transition-name traps fixed descendants), letting
    // --z-dialog win over the sibling sidebar/terminal panels.
    return createPortal(
        <div
            className="fixed inset-0 z-[var(--z-dialog)] flex items-center justify-center"
            role="dialog"
            aria-modal="true"
            data-state={closing ? "closing" : "open"}
        >
            {/* Backdrop */}
            <div
                className={cn(
                    "fixed inset-0 bg-black/72 backdrop-blur-[2px] transition-opacity duration-[140ms]",
                    closing ? "opacity-0" : "opacity-100",
                )}
                onClick={() => onOpenChange(false)}
            />
            {/* Content - relative z-10 to sit above backdrop */}
            <div
                ref={surfaceRef}
                tabIndex={-1}
                className={cn(
                    "ui-dialog-surface relative z-10 mx-4 w-full max-w-md overflow-hidden rounded-xl border border-[var(--desktop-border-strong)] bg-transparent shadow-[var(--shadow-dialog)] outline-none [--pop-offset:8px]",
                    closing ? "ui-pop-out" : "ui-pop-in",
                    className,
                )}
            >
                {children}
            </div>
        </div>,
        document.body,
    );
}

export function DialogHeader({
    children,
    className,
}: {
    children: React.ReactNode;
    className?: string;
}) {
    return (
        <div className={cn("px-6 pt-6 pb-4", className)}>
            {children}
        </div>
    );
}

export function DialogTitle({
    children,
    className,
}: {
    children: React.ReactNode;
    className?: string;
}) {
    return (
        <h2 className={cn("text-base font-bold tracking-[-0.02em] text-[var(--desktop-text-primary)]", className)}>
            {children}
        </h2>
    );
}

export function DialogDescription({
    children,
    className,
}: {
    children: React.ReactNode;
    className?: string;
}) {
    return (
        <p className={cn("mt-1.5 text-sm leading-6 text-[var(--desktop-text-tertiary)]", className)}>
            {children}
        </p>
    );
}

export function DialogContent({
    children,
    className,
}: {
    children: React.ReactNode;
    className?: string;
}) {
    return (
        <div className={cn("px-6 pb-4", className)}>
            {children}
        </div>
    );
}

export function DialogFooter({
    children,
    className,
}: {
    children: React.ReactNode;
    className?: string;
}) {
    return (
        <div className={cn("px-6 pb-6 flex justify-end gap-2", className)}>
            {children}
        </div>
    );
}

interface ConfirmDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    title: string;
    description: string;
    confirmLabel?: string;
    cancelLabel?: string;
    onConfirm: () => void | Promise<void>;
    variant?: "default" | "destructive";
}

export function ConfirmDialog({
    open,
    onOpenChange,
    title,
    description,
    confirmLabel = "Confirm",
    cancelLabel = "Cancel",
    onConfirm,
    variant = "default",
}: ConfirmDialogProps) {
    const [isLoading, setIsLoading] = React.useState(false);

    const handleConfirm = async () => {
        setIsLoading(true);
        try {
            await onConfirm();
        } finally {
            setIsLoading(false);
            onOpenChange(false);
        }
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogHeader>
                <DialogTitle>{title}</DialogTitle>
                <DialogDescription>{description}</DialogDescription>
            </DialogHeader>
            <DialogFooter>
                <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={isLoading}>
                    {cancelLabel}
                </Button>
                <Button
                    variant={variant === "destructive" ? "destructive" : "default"}
                    onClick={handleConfirm}
                    disabled={isLoading}
                >
                    {isLoading ? "Deleting..." : confirmLabel}
                </Button>
            </DialogFooter>
        </Dialog>
    );
}
