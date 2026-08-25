import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useBootstrapStatus, useSession } from "@/lib/api/hooks";
import { AppShell } from "@/components/layout/AppShell";

function LoadingScreen() {
  return (
    <div className="flex h-screen items-center justify-center bg-surface-muted text-text-muted text-sm">
      Loading…
    </div>
  );
}

export function AuthGuard() {
  const { data: session, isLoading } = useSession();
  const { data: bootstrap } = useBootstrapStatus();
  const location = useLocation();

  if (isLoading) return <LoadingScreen />;

  if (!session) {
    if (bootstrap && !bootstrap.ready) {
      return <Navigate to="/setup" replace />;
    }
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return <Outlet />;
}

export function AppShellGuard() {
  return <AppShell><Outlet /></AppShell>;
}

export function GuestGuard() {
  const { data: session, isLoading } = useSession();
  const { data: bootstrap } = useBootstrapStatus();
  const location = useLocation();

  if (isLoading) return <LoadingScreen />;

  if (session) {
    return <Navigate to="/inbox" replace />;
  }

  if (bootstrap && !bootstrap.ready && location.pathname !== "/setup") {
    return <Navigate to="/setup" replace />;
  }

  return <Outlet />;
}
