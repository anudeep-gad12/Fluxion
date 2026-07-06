import * as React from "react";
import { cn } from "@/lib/utils";
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

    if (!open) return null;

    return (
        <div
            className="fixed inset-0 z-[var(--z-dialog)] flex items-center justify-center"
            role="dialog"
            aria-modal="true"
        >
            {/* Backdrop */}
            <div
                className="fixed inset-0 bg-black/72 backdrop-blur-[2px]"
                onClick={() => onOpenChange(false)}
            />
            {/* Content - relative z-10 to sit above backdrop */}
            <div
                ref={surfaceRef}
                tabIndex={-1}
                className={cn(
                    "ui-dialog-surface relative z-10 mx-4 w-full max-w-md overflow-hidden rounded-xl border border-[var(--desktop-border-strong)] bg-transparent shadow-[var(--shadow-dialog)] outline-none animate-in fade-in zoom-in-95 duration-200",
                    className,
                )}
            >
                {children}
            </div>
        </div>
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
