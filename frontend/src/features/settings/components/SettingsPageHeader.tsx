import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function SettingsPageHeader({
  title,
  description,
  actions,
  className,
}: {
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <header className={cn("flex flex-wrap items-start justify-between gap-3", className)}>
      <div className="min-w-0">
        <h1 className="hidden text-[22px] font-bold leading-7 text-text-primary md:block">{title}</h1>
        {description && (
          <p className="mt-0.5 max-w-2xl text-[13px] leading-5 text-text-secondary">{description}</p>
        )}
      </div>
      {actions ? <div className="hidden shrink-0 flex-wrap items-center gap-2 md:flex">{actions}</div> : null}
    </header>
  );
}
