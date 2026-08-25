import { useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { LogOut, Menu, X } from "lucide-react";
import { cn, getInitials } from "@/lib/utils";
import { api } from "@/lib/api/client";
import {
  useSession,
  useLogout,
  useInboxCount,
  useTrashCount,
} from "@/lib/api/hooks";
import { AiStatusPill } from "@/components/layout/AiStatusPill";
import { MobileNavbarSearch, NavbarSearch } from "@/components/layout/NavbarSearch";
import { NavbarUpload } from "@/components/layout/NavbarUpload";
import { AskDock } from "@/components/ask/AskDock";
import { OnboardingTourProvider } from "@/features/onboarding/OnboardingTour";
import { BrandMark, BrandWordmark } from "@/components/brand/BrandMark";
import { TooltipProvider } from "@/components/ui/Tooltip";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/DropdownMenu";

interface AppShellProps {
  children: React.ReactNode;
}

const NAV_ITEMS = [
  { to: "/inbox", label: "Inbox", badge: "inbox" as const },
  { to: "/documents", label: "Library" },
  { to: "/trash", label: "Trash", badge: "trash" as const },
  { to: "/settings", label: "Settings" },
];

export function AppShell({ children }: AppShellProps) {
  const navigate = useNavigate();
  const [mobileNavigationOpen, setMobileNavigationOpen] = useState(false);
  const { data: session } = useSession();
  const logout = useLogout();
  const { data: inboxCount = 0 } = useInboxCount();
  const { data: trashCount } = useTrashCount();

  const handleLogout = async () => {
    await logout.mutateAsync();
    navigate("/login");
  };

  return (
    <TooltipProvider delayDuration={400}>
      <OnboardingTourProvider>
      <div className="flex h-screen flex-col overflow-hidden bg-surface-muted">
        <header className="relative z-50 m-3 flex min-h-[72px] w-[calc(100%-24px)] shrink-0 items-stretch rounded-[14px] border border-[rgba(148,163,184,0.10)] bg-navbar pl-4 pr-5 text-navbar-text shadow-[0_8px_20px_rgba(2,6,23,0.18)] max-[360px]:px-3 sm:pl-[19px] sm:pr-6 lg:pl-[26px] lg:pr-8">
          <div className="flex min-w-0 items-center gap-[7px] max-[360px]:gap-1">
            <BrandMark variant="on-dark" size={36} className="max-[360px]:!h-7 max-[360px]:!w-7" />
            <BrandWordmark
              variant="on-dark"
              className="text-[clamp(14px,5.5vw,22px)] leading-none font-bold tracking-[-0.04em] max-[360px]:text-[14px] lg:text-[26px]"
            />
          </div>

          <nav
            className="ml-6 hidden items-stretch gap-6 md:flex lg:ml-10 lg:gap-9"
            aria-label="Primary"
          >
            {NAV_ITEMS.map(({ to, label, badge }) => {
              const badgeCount =
                badge === "inbox"
                  ? inboxCount
                  : badge === "trash"
                    ? (trashCount?.total ?? 0)
                    : 0;
              return (
                <NavLink
                  key={to}
                  to={to}
                  data-tour={label.toLowerCase()}
                  className={({ isActive }) =>
                    cn(
                      "relative flex h-full items-center px-1 text-sm font-semibold text-navbar-muted transition-colors duration-150 ease-out hover:text-navbar-text",
                      isActive &&
                        "text-navbar-text after:absolute after:right-1 after:bottom-0 after:left-1 after:h-[2.5px] after:rounded-full after:bg-navbar-accent after:content-['']",
                    )
                  }
                >
                  <span className="flex items-center gap-2">
                    <span>{label}</span>
                    {badgeCount > 0 && (
                      <span className="flex h-5 min-w-[20px] items-center justify-center rounded-full bg-navbar-accent/20 px-1.5 text-[11px] font-medium text-navbar-accent">
                        {badgeCount > 99 ? "99+" : badgeCount}
                      </span>
                    )}
                  </span>
                </NavLink>
              );
            })}
          </nav>

          <div className="ml-4 hidden min-w-0 flex-1 items-center justify-end gap-3 pl-2 md:flex sm:gap-4 lg:gap-5">
            <NavbarSearch />
            <NavbarUpload />

            <div className="flex max-md:hidden">
              <AiStatusPill />
            </div>

            <span
              className="hidden h-[38px] w-px shrink-0 bg-[rgba(148,163,184,0.18)] md:block"
              aria-hidden="true"
            />

          </div>

          <div className="ml-auto flex items-center self-center md:hidden">
            <MobileNavbarSearch />
            <button
              type="button"
              className="flex h-11 w-11 items-center justify-center rounded-lg text-navbar-text transition-colors hover:bg-[rgba(148,163,184,0.08)]"
              aria-label={mobileNavigationOpen ? "Close navigation menu" : "Open navigation menu"}
              aria-controls="mobile-primary-navigation"
              aria-expanded={mobileNavigationOpen}
              onClick={() => setMobileNavigationOpen((open) => !open)}
            >
              {mobileNavigationOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </button>
          </div>

          {mobileNavigationOpen && (
            <nav
              id="mobile-primary-navigation"
              className="absolute top-[calc(100%+8px)] right-0 left-0 overflow-hidden rounded-[14px] border border-[rgba(148,163,184,0.10)] bg-navbar p-2 shadow-[0_12px_32px_rgba(2,6,23,0.24)] md:hidden"
              aria-label="Mobile primary"
            >
              {NAV_ITEMS.map(({ to, label, badge }) => {
                const badgeCount =
                  badge === "inbox"
                    ? inboxCount
                    : badge === "trash"
                      ? (trashCount?.total ?? 0)
                      : 0;
                return (
                  <NavLink
                    key={to}
                    to={to}
                    onClick={() => setMobileNavigationOpen(false)}
                    className={({ isActive }) =>
                      cn(
                        "flex min-h-11 items-center justify-between rounded-lg px-3 text-sm font-semibold text-navbar-muted transition-colors hover:bg-[rgba(148,163,184,0.08)] hover:text-navbar-text",
                        isActive && "bg-[rgba(148,163,184,0.12)] text-navbar-text",
                      )
                    }
                  >
                    {label}
                    {badgeCount > 0 && (
                      <span className="flex h-5 min-w-[20px] items-center justify-center rounded-full bg-navbar-accent/20 px-1.5 text-[11px] font-medium text-navbar-accent">
                        {badgeCount > 99 ? "99+" : badgeCount}
                      </span>
                    )}
                  </NavLink>
                );
              })}
            </nav>
          )}

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                type="button"
                className="ml-2 flex items-center gap-2.5 self-center rounded-lg px-1 text-left transition-colors duration-150 ease-out hover:bg-[rgba(148,163,184,0.08)] max-[360px]:ml-1 md:ml-4"
                aria-label="Account menu"
              >
                <div className="flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-full border border-navbar-accent/40 bg-[#172033] text-sm font-bold text-navbar-text lg:h-12 lg:w-12">
                  {session?.user?.has_avatar ? (
                    <img
                      src={api.avatarUrl(session.user.id)}
                      alt=""
                      className="h-full w-full object-cover"
                    />
                  ) : session?.user ? (
                    getInitials(session.user.display_name)
                  ) : (
                    "?"
                  )}
                </div>
                <div className="hidden min-w-0 lg:block">
                  <p className="truncate text-sm font-semibold text-navbar-text">
                    {session?.user.display_name ?? "User"}
                  </p>
                  <p className="truncate text-[13px] font-normal text-navbar-muted">
                    {session?.user.is_admin ? "Admin" : "User"}
                  </p>
                </div>
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => void handleLogout()}>
                <LogOut className="h-3.5 w-3.5" />
                Log out
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </header>

        <main className="flex min-h-0 flex-1 flex-col overflow-hidden bg-surface">
          {children}
        </main>
        <AskDock />
      </div>
      </OnboardingTourProvider>
    </TooltipProvider>
  );
}
