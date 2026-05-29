import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "ui-transition ui-focus-ring inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-[0.95rem] text-sm font-semibold ring-offset-background disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default: "border border-zinc-100 bg-zinc-100 text-zinc-950 shadow-[0_18px_50px_rgba(255,255,255,0.10)] hover:-translate-y-0.5 hover:bg-white",
        destructive:
          "border border-red-400/24 bg-red-500/12 text-red-100 shadow-[0_14px_32px_rgba(255,120,120,0.08)] hover:border-red-300/36 hover:bg-red-500/18",
        outline:
          "border border-white/10 bg-white/[0.035] text-zinc-200 hover:border-cyan-300/28 hover:bg-cyan-300/[0.07] hover:text-cyan-50",
        secondary:
          "border border-white/10 bg-white/[0.045] text-zinc-200 hover:border-white/16 hover:bg-white/[0.075]",
        ghost: "text-zinc-400 hover:bg-white/[0.055] hover:text-cyan-50",
        desktop:
          "border border-white/[0.08] bg-white/[0.04] font-medium text-zinc-200 shadow-none hover:border-white/12 hover:bg-white/[0.07] hover:text-zinc-50 data-[app=desktop]:hover:translate-y-0",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-10 px-4 py-2",
        sm: "h-9 rounded-[0.85rem] px-3",
        lg: "h-11 rounded-[1rem] px-8",
        icon: "h-10 w-10 rounded-[0.9rem]",
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
