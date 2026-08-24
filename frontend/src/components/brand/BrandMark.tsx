import { cn } from "@/lib/utils";
import paperLogo from "@brand/paper_logo.svg";

export type BrandSurface = "on-dark" | "on-light";

interface BrandMarkProps {
  /** Kept for call-site compatibility. The mark is always paper_logo.svg. */
  variant?: BrandSurface;
  size?: number;
  className?: string;
  alt?: string;
}

export function BrandMark({ size = 40, className, alt }: BrandMarkProps) {
  return (
    <span
      className={cn("inline-block shrink-0", className)}
      style={{ width: size, height: size }}
    >
      <img
        src={paperLogo}
        alt={alt ?? ""}
        width={size}
        height={size}
        className="block h-full w-full object-contain"
        aria-hidden={alt ? undefined : true}
      />
    </span>
  );
}

interface BrandWordmarkProps {
  variant: BrandSurface;
  className?: string;
}

export function BrandWordmark({ variant, className }: BrandWordmarkProps) {
  const prefixClass =
    variant === "on-dark" ? "text-navbar-text" : "text-text-primary";
  const accentClass =
    variant === "on-dark" ? "text-navbar-accent" : "text-accent";

  return (
    <span className={cn("font-brand whitespace-nowrap font-bold tracking-[-0.02em]", className)}>
      <span aria-hidden="true" className={prefixClass}>
        lesspaper-<span className={accentClass}>ngl</span>
      </span>
      <span className="sr-only">lesspaper-ngl</span>
    </span>
  );
}

interface BrandLockupProps {
  variant: BrandSurface;
  markSize?: number;
  className?: string;
  wordmarkClassName?: string;
}

export function BrandLockup({
  variant,
  markSize = 28,
  className,
  wordmarkClassName,
}: BrandLockupProps) {
  return (
    <span className={cn("inline-flex items-center gap-2", className)}>
      <BrandMark variant={variant} size={markSize} />
      <BrandWordmark variant={variant} className={wordmarkClassName} />
    </span>
  );
}
