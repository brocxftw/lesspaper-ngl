import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function SettingsSection({
  title,
  description,
  index,
  badge,
  actions,
  children,
  id,
  className,
}: {
  title: string;
  description?: string;
  index?: number;
  badge?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
  id?: string;
  className?: string;
}) {
  const heading = index != null ? `${index}. ${title}` : title;
  return (
    <section id={id} className={cn("space-y-3", className)} aria-labelledby={id ? `${id}-heading` : undefined}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2
              id={id ? `${id}-heading` : undefined}
              className="text-[15px] font-bold leading-[22px] text-text-primary"
            >
              <span className="md:hidden">{title}</span>
              <span className="hidden md:inline">{heading}</span>
            </h2>
            {badge}
          </div>
          {description && (
            <p className="mt-0.5 text-[13px] leading-5 text-text-secondary">{description}</p>
          )}
        </div>
        {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
      </div>
      {children}
    </section>
  );
}
