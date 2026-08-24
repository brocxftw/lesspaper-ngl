import { NavLink, useNavigate } from "react-router-dom";
import { LogOut } from "lucide-react";
import { cn, getInitials } from "@/lib/utils";
import { api } from "@/lib/api/client";
import {
  useSession,
  useLogout,
  useInboxCount,
  useTrashCount,
} from "@/lib/api/hooks";
import { AiStatusPill } from "@/components/layout/AiStatusPill";
import { NavbarSearch } from "@/components/layout/NavbarSearch";
import { NavbarUpload } from "@/components/layout/NavbarUpload";
import { AskDock } from "@/components/ask/AskDock";
import lesspaperNglLogo from "@/assets/brand/lesspaper-ngl_logo.svg";
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
      <div className="flex h-screen flex-col overflow-hidden bg-surface-muted">
        <header className="relative z-50 m-3 flex min-h-[79px] w-[calc(100%-24px)] shrink-0 flex-nowrap items-stretch overflow-x-auto rounded-[14px] border border-[rgba(148,163,184,0.10)] bg-navbar px-8 text-navbar-text shadow-[0_10px_30px_rgba(2,6,23,0.24),0_2px_8px_rgba(2,6,23,0.20)]">
          <div className="flex items-center">
            <img
              src={lesspaperNglLogo}
              alt=""
              width={40}
              height={40}
              className="mr-3 h-10 w-10 shrink-0 object-contain"
              aria-hidden="true"
            />
            <div className="flex min-w-0 flex-col gap-1">
              <span className="shrink-0 text-[30px] leading-none font-bold tracking-[-0.02em] text-[#F8FAFC]">
                lesspaper-ngl
              </span>
              <span className="self-start rounded px-1.5 py-px text-[10px] font-medium leading-4 text-[#CBD5E1] border border-[rgba(148,163,184,0.05)] bg-[rgba(148,163,184,0.12)] shadow-[0_1px_3px_rgba(0,0,0,0.16),inset_0_1px_0_rgba(255,255,255,0.03)]">
                Beta
              </span>
            </div>
          </div>

          <div className="ml-5 flex min-w-0 flex-1 items-center justify-start">
            <NavbarSearch />
          </div>

          <nav
            className="ml-12 flex items-stretch gap-[38px]"
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
                  className={({ isActive }) =>
                    cn(
                      "relative flex h-full items-center px-1 text-sm font-semibold text-[#E2E8F0] transition-colors duration-150 ease-out hover:text-white",
                      isActive &&
                        "text-white after:absolute after:bottom-0 after:left-1/2 after:h-[3px] after:w-16 after:-translate-x-1/2 after:rounded-t-[3px] after:bg-[#2DD4BF] after:shadow-[0_-1px_6px_rgba(45,212,191,0.20)] after:content-['']",
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

          <div className="ml-auto flex items-center gap-[22px] pl-6">
            <NavbarUpload />

            <div className="flex max-md:hidden">
              <AiStatusPill />
            </div>

            <span
              className="block h-[38px] w-px shrink-0 bg-[rgba(148,163,184,0.18)] max-md:hidden"
              aria-hidden="true"
            />

            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button
                  type="button"
                  className="flex items-center gap-2.5 rounded-lg px-1 text-left transition-colors duration-150 ease-out hover:bg-[rgba(148,163,184,0.08)]"
                  aria-label="Account menu"
                >
                  <div className="flex h-12 w-12 shrink-0 items-center justify-center overflow-hidden rounded-full border border-[rgba(20,184,166,0.45)] bg-[#172033] text-sm font-bold text-[#F8FAFC]">
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
                  <div className="min-w-0 max-lg:hidden">
                    <p className="truncate text-sm font-semibold text-[#F8FAFC]">
                      {session?.user.display_name ?? "User"}
                    </p>
                    <p className="truncate text-[13px] font-normal text-[#94A3B8]">
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
          </div>
        </header>

        <main className="flex min-h-0 flex-1 flex-col overflow-hidden bg-surface">
          {children}
        </main>
        <AskDock />
      </div>
    </TooltipProvider>
  );
}
