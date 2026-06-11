import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex h-9 items-center justify-center gap-2 whitespace-nowrap rounded-md px-3 text-sm font-semibold transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground shadow-sm shadow-primary/20 hover:bg-primary/90 hover:shadow-md hover:shadow-primary/20",
        outline: "border bg-card/90 hover:border-primary/30 hover:bg-primary/5",
        ghost: "hover:bg-primary/10 hover:text-primary",
        destructive: "bg-destructive text-destructive-foreground shadow-sm shadow-destructive/20 hover:bg-destructive/90"
      }
    },
    defaultVariants: {
      variant: "default"
    }
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return <Comp className={cn(buttonVariants({ variant, className }))} ref={ref} {...props} />;
  }
);
Button.displayName = "Button";

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        "h-9 w-full rounded-md border bg-white/90 px-3 text-sm outline-none transition-all placeholder:text-muted-foreground focus-visible:border-primary focus-visible:bg-white focus-visible:ring-2 focus-visible:ring-ring/20",
        className
      )}
      {...props}
    />
  )
);
Input.displayName = "Input";

type SurfaceProps<T extends React.ElementType> = {
  as?: T;
  className?: string;
} & React.ComponentPropsWithoutRef<T>;

export function Surface<T extends React.ElementType = "div">({ as, className, ...props }: SurfaceProps<T>) {
  const Comp = as ?? "div";
  return <Comp className={cn("rounded-lg border bg-card/95 text-card-foreground shadow-sm shadow-slate-200/70 backdrop-blur", className)} {...props} />;
}

export function Badge({ className, ...props }: React.HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-semibold",
        className
      )}
      {...props}
    />
  );
}
