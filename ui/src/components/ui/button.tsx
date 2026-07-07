import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "ui-transition ui-pressable ui-focus-ring inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-xl text-sm font-semibold ring-offset-background disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default: "border border-[var(--desktop-text-primary)] bg-[var(--desktop-text-primary)] text-[var(--desktop-bg-0)] hover:opacity-90",
        destructive:
          "border border-[rgb(var(--ui-danger-rgb)/0.24)] bg-[rgb(var(--ui-danger-rgb)/0.1)] text-[var(--desktop-danger-text)] hover:border-[rgb(var(--ui-danger-rgb)/0.34)] hover:bg-[rgb(var(--ui-danger-rgb)/0.16)]",
        outline:
          "border border-[var(--desktop-border-strong)] bg-[var(--desktop-hover)] text-[var(--desktop-text-secondary)] hover:border-[rgb(var(--desktop-accent-rgb)/0.28)] hover:bg-[var(--desktop-accent-hover)] hover:text-[var(--desktop-text-primary)]",
        secondary:
          "border border-[var(--desktop-border-strong)] bg-[var(--desktop-hover)] text-[var(--desktop-text-secondary)] hover:bg-[var(--desktop-hover-strong)]",
        ghost: "text-[var(--desktop-text-secondary)] hover:bg-[var(--desktop-hover)] hover:text-[var(--desktop-text-primary)]",
        desktop:
          "border border-[var(--desktop-border-strong)] bg-[var(--desktop-hover)] font-medium text-[var(--desktop-text-secondary)] hover:bg-[var(--desktop-hover-strong)] hover:text-[var(--desktop-text-primary)]",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-10 px-4 py-2",
        sm: "h-9 rounded-lg px-3",
        lg: "h-11 rounded-xl px-8",
        icon: "h-10 w-10 rounded-lg",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button"
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    )
  }
)
Button.displayName = "Button"

export { Button, buttonVariants }
