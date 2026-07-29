import { Button as ButtonPrimitive } from "@base-ui/react/button"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "group/button inline-flex shrink-0 items-center justify-center gap-2 rounded-[10px] border border-transparent bg-clip-padding font-sans font-semibold whitespace-nowrap transition-[filter,background-color,border-color] duration-[var(--duration-quick)] ease-[var(--ease-standard)] outline-none select-none focus-visible:ring-2 focus-visible:ring-[var(--color-teal)] focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-40 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        primary:
          "bg-[var(--color-amber)] text-[var(--color-ink)] hover:brightness-95",
        secondary:
          "border-[rgba(27,42,65,0.18)] bg-white text-[var(--color-ink)] hover:bg-[#f4f2ee]",
        ghost:
          "text-[var(--color-teal)] hover:bg-[rgba(47,110,99,0.1)]",
        confirm: "bg-[var(--color-teal)] text-white hover:brightness-95",
        danger: "bg-[var(--color-coral)] text-white hover:brightness-95",
        quiet: "bg-[#f4f2ee] font-medium text-[var(--color-ink)] hover:bg-[#ece9e3]",
      },
      size: {
        sm: "rounded-lg px-3 py-1.5 text-xs",
        default: "px-[18px] py-2.5 text-sm",
        lg: "rounded-[11px] px-6 py-3 text-[15px]",
        icon: "size-10 rounded-[10px]",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "default",
    },
  }
)

function Button({
  className,
  variant = "primary",
  size = "default",
  ...props
}: ButtonPrimitive.Props & VariantProps<typeof buttonVariants>) {
  return (
    <ButtonPrimitive
      data-slot="button"
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }
