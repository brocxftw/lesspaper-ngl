import { NavLink, Navigate, Outlet, useLocation } from "react-router-dom";
import { useState, type ReactNode } from "react";
import {
  Archive,
  Info,
  Library,
  ScrollText,
  Server,
  Sparkles,
  User,
  ChevronDown,
  X,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { usePasswordResetRequests, useSession } from "@/lib/api/hooks";
import { ProfileSettings } from "@/components/settings/ProfileSettings";
import { UsersSettings } from "@/components/settings/UsersSettings";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/Popover";

const SETTINGS_NAV: Array<{ to: string; label: string; adminOnly: boolean; icon: LucideIcon }> = [
  { to: "/settings/profile", label: "Profile", adminOnly: false, icon: User },
  { to: "/settings/library", label: "Library", adminOnly: false, icon: Library },
  { to: "/settings/artificial-intelligence", label: "Artificial Intelligence", adminOnly: true, icon: Sparkles },
  { to: "/settings/backup", label: "Backup & Restore", adminOnly: true, icon: Archive },
  { to: "/settings/system", label: "System", adminOnly: true, icon: Server },
  { to: "/settings/logs", label: "Logs", adminOnly: true, icon: ScrollText },
  { to: "/settings/about", label: "About", adminOnly: false, icon: Info },
];

export function SettingsLayout() {
  const { data: session } = useSession();
  const isAdmin = !!session?.user.is_admin;
  const { data: resetRequests = [] } = usePasswordResetRequests(isAdmin);
  const pendingResets = isAdmin ? resetRequests.length : 0;
  const nav = SETTINGS_NAV.filter((item) => !item.adminOnly || isAdmin);
  const location = useLocation();
  const [mobileNavigationOpen, setMobileNavigationOpen] = useState(false);
  const activeSection = nav.find((item) => location.pathname === item.to) ?? nav[0];

  return (
    <div className="flex h-full min-w-0 flex-col md:flex-row">
      <aside className="hidden shrink-0 border-b border-surface-border bg-surface p-3 md:block md:w-56 md:border-b-0 md:border-r md:p-4">
        <h1 className="mb-4 text-base font-semibold text-text-primary">Settings</h1>
        <nav className="flex gap-1 overflow-x-auto md:block md:space-y-0.5" aria-label="Settings sections">
          {nav.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                cn(
                  "flex shrink-0 items-center gap-2 rounded-md px-3 py-2 text-[13px]",
                  isActive
                    ? "bg-accent-muted font-medium text-accent"
                    : "text-text-secondary hover:bg-surface-hover hover:text-text-primary",
                )
              }
            >
              {({ isActive }) => (
                <>
                  <Icon
                    className={cn("h-4 w-4 shrink-0", isActive ? "text-accent" : "text-text-muted")}
                    strokeWidth={1.75}
                    aria-hidden="true"
                  />
                  <span className="min-w-0 flex-1 truncate">{label}</span>
                  {to === "/settings/profile" && pendingResets > 0 && (
                    <span className="rounded bg-accent-muted px-1.5 py-0.5 text-[10px] font-medium text-accent">
                      {pendingResets}
                    </span>
                  )}
                </>
              )}
            </NavLink>
          ))}
        </nav>
      </aside>
      <div className="min-w-0 flex-1 overflow-auto bg-surface-muted p-4 md:p-6 lg:p-8">
        <div className="mb-6 md:hidden">
          <h1 className="mb-3 text-[22px] font-bold leading-7 text-text-primary">Settings</h1>
          <Popover open={mobileNavigationOpen} onOpenChange={setMobileNavigationOpen}>
            {activeSection && (
              <PopoverTrigger asChild>
                <button
                  type="button"
                  className="flex min-h-11 w-full items-center gap-3 rounded-lg border border-surface-border bg-surface px-3 text-left text-sm font-medium text-text-primary shadow-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
                  aria-label={`Choose settings section, currently ${activeSection.label}`}
                >
                  <activeSection.icon className="h-5 w-5 shrink-0 text-text-secondary" strokeWidth={1.75} aria-hidden="true" />
                  <span className="min-w-0 flex-1 truncate">{activeSection.label}</span>
                  <ChevronDown className="h-4 w-4 shrink-0 text-text-muted" aria-hidden="true" />
                </button>
              </PopoverTrigger>
            )}
            <PopoverContent align="start" side="bottom" className="w-[var(--radix-popover-trigger-width)] max-h-[min(70vh,520px)] overflow-y-auto p-2">
              <div className="flex h-11 items-center justify-between px-2">
                <p className="text-sm font-semibold text-text-primary">Settings</p>
                <button type="button" className="-mr-1 flex h-11 w-11 items-center justify-center rounded-md text-text-muted hover:bg-surface-hover hover:text-text-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent" onClick={() => setMobileNavigationOpen(false)} aria-label="Close settings picker">
                  <X className="h-4 w-4" aria-hidden="true" />
                </button>
              </div>
              <nav aria-label="Settings sections">
                {nav.map(({ to, label, icon: Icon }) => {
                  const isActive = location.pathname === to;
                  return (
                    <NavLink
                      key={to}
                      to={to}
                      onClick={() => setMobileNavigationOpen(false)}
                      className={cn(
                        "flex min-h-11 items-center gap-3 rounded-md px-3 py-2.5 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent",
                        isActive
                          ? "bg-accent-muted font-medium text-accent"
                          : "text-text-secondary hover:bg-surface-hover hover:text-text-primary",
                      )}
                    >
                      <Icon className={cn("h-5 w-5 shrink-0", isActive ? "text-accent" : "text-text-muted")} strokeWidth={1.75} aria-hidden="true" />
                      <span className="min-w-0 flex-1">{label}</span>
                      {to === "/settings/profile" && pendingResets > 0 && (
                        <span className="rounded bg-accent-muted px-1.5 py-0.5 text-[10px] font-medium text-accent">{pendingResets}</span>
                      )}
                    </NavLink>
                  );
                })}
              </nav>
            </PopoverContent>
          </Popover>
        </div>
        <Outlet />
      </div>
    </div>
  );
}

export function ProfileSettingsPage() {
  return <ProfileSettings />;
}

export function UsersSettingsPage() {
  return (
    <AdminSettingsGuard>
      <UsersSettings />
    </AdminSettingsGuard>
  );
}

export function AdminSettingsGuard({ children }: { children: ReactNode }) {
  const { data: session } = useSession();
  const location = useLocation();
  if (session && !session.user.is_admin) {
    return (
      <Navigate
        to="/settings/profile"
        replace
        state={{ notice: `Administrator access is required for ${location.pathname}.` }}
      />
    );
  }
  return <>{children}</>;
}
