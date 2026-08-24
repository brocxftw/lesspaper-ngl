import { cn } from "@/lib/utils";
import { forwardRef, type ButtonHTMLAttributes } from "react";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "default" | "secondary" | "ghost" | "danger" | "outline";
  size?: "sm" | "md" | "icon";
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "default", size = "md", disabled, ...props }, ref) => {
    return (
      <button
        ref={ref}
        disabled={disabled}
        className={cn(
          "inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition-colors",
          "disabled:pointer-events-none disabled:opacity-50",
          size === "sm" && "h-7 px-2 text-xs",
          size === "md" && "h-8 px-3 text-[13px]",
          size === "icon" && "h-8 w-8 p-0",
          variant === "default" &&
            "bg-accent text-accent-foreground hover:bg-accent-hover",
          variant === "secondary" &&
            "bg-surface-muted text-text-primary border border-surface-border hover:bg-surface-hover",
          variant === "ghost" &&
            "text-text-secondary hover:bg-surface-hover hover:text-text-primary",
          variant === "danger" &&
            "bg-danger text-white hover:bg-red-700",
          variant === "outline" &&
            "border border-surface-border bg-surface text-text-primary hover:bg-surface-hover",
          className,
        )}
        {...props}
      />
    );
  },
);
Button.displayName = "Button";
