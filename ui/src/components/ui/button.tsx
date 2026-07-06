import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "ui-transition ui-focus-ring inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-xl text-sm font-semibold ring-offset-background disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default: "border border-zinc-100 bg-zinc-100 text-zinc-950 hover:bg-white",
        destructive:
          "border border-red-400/24 bg-red-500/12 text-red-100 hover:border-red-300/36 hover:bg-red-500/18",
        outline:
          "border border-[var(--desktop-border-strong)] bg-[var(--desktop-hover)] text-zinc-200 hover:border-cyan-300/28 hover:bg-[var(--desktop-accent-hover)] hover:text-cyan-50",
        secondary:
          "border border-[var(--desktop-border-strong)] bg-[var(--desktop-hover)] text-zinc-200 hover:border-white/16 hover:bg-[var(--desktop-hover-strong)]",
        ghost: "text-[var(--desktop-text-secondary)] hover:bg-[var(--desktop-hover)] hover:text-cyan-50",
        desktop:
          "border border-[var(--desktop-border-strong)] bg-[var(--desktop-hover)] font-medium text-zinc-200 hover:border-white/[0.12] hover:bg-[var(--desktop-hover-strong)] hover:text-[var(--desktop-text-primary)]",
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
