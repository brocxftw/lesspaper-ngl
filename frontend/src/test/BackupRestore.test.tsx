import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { BackupRestorePage } from "@/features/settings/BackupRestorePage";
import { SetupPage } from "@/features/auth/SetupPage";

const mutateAsync = vi.fn();

const backupSettings = {
  enabled: false,
  schedule_type: "daily",
  backup_time: "02:00",
  weekday: 0,
  interval_hours: 24,
  repository_subdir: "",
  retention_count: 7,
  verify_after_backup: true,
  last_success_at: null,
  next_run_at: null,
  repository: {
    configured: true,
    exists: true,
    readable: true,
    writable: true,
    path: "/backups",
    free_bytes: 1000,
    message: "ok",
  },
};

let mockBackups: Array<Record<string, unknown>> = [];
let mockRepoWritable = true;
let mockBootstrapState = "uninitialised";
let mockBootstrapBackups: Array<Record<string, unknown>> = [];

vi.mock("@/components/ui/DropdownMenu", () => ({
  DropdownMenu: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuTrigger: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  DropdownMenuContent: ({ children }: { children: React.ReactNode }) => <div role="menu">{children}</div>,
  DropdownMenuItem: ({
    children,
    onSelect,
    disabled,
  }: {
    children: React.ReactNode;
    onSelect?: (event: Event) => void;
    disabled?: boolean;
  }) => (
    <button
      type="button"
      role="menuitem"
      disabled={disabled}
      onClick={() => onSelect?.(new Event("select"))}
    >
      {children}
    </button>
  ),
}));

vi.mock("@/lib/api/hooks", () => ({
  useBackupSettings: () => ({
    data: { ...backupSettings, repository: { ...backupSettings.repository, writable: mockRepoWritable, message: mockRepoWritable ? "ok" : "not writable" } },
    isLoading: false,
    error: null,
  }),
  useBackups: () => ({ data: mockBackups }),
  useBackupRestoreStatus: () => ({ data: { active: false, stage: "idle", filename: null, error: null, started_at: null, completed_at: null } }),
  useUpdateBackupSettings: () => ({ mutateAsync, isPending: false }),
  useCreateBackup: () => ({ mutateAsync, isPending: false }),
  useVerifyBackup: () => ({ mutateAsync }),
  useDeleteBackup: () => ({ mutateAsync }),
  useInspectBackup: () => ({ mutateAsync }),
  useRestoreBackup: () => ({ mutateAsync }),
  useBootstrapStatus: () => ({ data: { instance_state: mockBootstrapState, ready: mockBootstrapState === "ready" }, isLoading: false }),
  useBootstrapBackups: () => ({ data: mockBootstrapBackups }),
  useBootstrapSetup: () => ({ mutateAsync, isPending: false }),
  useBootstrapInspect: () => ({ mutateAsync }),
  useBootstrapRestore: () => ({ mutateAsync }),
}));

describe("Backup & Restore settings", () => {
  beforeEach(() => {
    mockBackups = [];
    mockRepoWritable = true;
    mutateAsync.mockReset();
    mutateAsync.mockResolvedValue(undefined);
  });

  it("renders settings and back up now", () => {
    render(<MemoryRouter><BackupRestorePage /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "Backup & Restore" })).toBeInTheDocument();
    expect(screen.getByText("Enable automatic backups")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Back up now" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Back up now" }));
    expect(mutateAsync).toHaveBeenCalled();
  });

  it("enables automatic backups", () => {
    render(<MemoryRouter><BackupRestorePage /></MemoryRouter>);
    fireEvent.click(screen.getByText("Enable automatic backups"));
    expect(mutateAsync).toHaveBeenCalled();
  });

  it("shows running progress", () => {
    mockBackups = [{
      id: "b1",
      filename: "folium-20260817T000000Z-00000000-0000-0000-0000-000000000001.folium",
      relative_key: "x.folium",
      created_at: "2026-08-17T00:00:00Z",
      size_bytes: 12,
      folium_version: "0.1.0",
      status: "running",
      verification_status: "unverified",
      error_message: null,
      progress_stage: "Dumping database",
    }];
    render(<MemoryRouter><BackupRestorePage /></MemoryRouter>);
    expect(screen.getByText(/Dumping database/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Back up now" })).toBeDisabled();
  });

  it("shows empty history and repository unavailable", () => {
    mockRepoWritable = false;
    render(<MemoryRouter><BackupRestorePage /></MemoryRouter>);
    expect(screen.getByText("No backups yet.")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Backup repository is unavailable");
  });

  it("shows history and restore confirmation", () => {
    mockBackups = [{
      id: "b1",
      filename: "folium-20260817T000000Z-00000000-0000-0000-0000-000000000001.folium",
      relative_key: "x.folium",
      created_at: "2026-08-17T00:00:00Z",
      size_bytes: 12,
      folium_version: "0.1.0",
      status: "completed",
      verification_status: "healthy",
      error_message: null,
      progress_stage: null,
    }];
    render(<MemoryRouter><BackupRestorePage /></MemoryRouter>);
    expect(screen.getByRole("button", { name: /Actions for/ })).toBeInTheDocument();
    const restoreItem = screen.getByRole("menuitem", { name: "Restore" });
    fireEvent.click(restoreItem);
    expect(screen.getByText("Restore this backup?")).toBeInTheDocument();
  });
});

describe("First-run setup", () => {
  beforeEach(() => {
    mockBootstrapState = "uninitialised";
    mockBootstrapBackups = [];
    mutateAsync.mockReset();
    mutateAsync.mockResolvedValue(undefined);
  });

  it("offers new install and restore", () => {
    render(<MemoryRouter><SetupPage /></MemoryRouter>);
    expect(screen.getByRole("button", { name: "Set up new lesspaper-ngl" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Restore backup" })).toBeInTheDocument();
  });

  it("explains when no backups are found", () => {
    render(<MemoryRouter><SetupPage /></MemoryRouter>);
    fireEvent.click(screen.getByRole("button", { name: "Restore backup" }));
    expect(screen.getByText(/No backups were found/)).toBeInTheDocument();
  });

  it("lists discovered backups", () => {
    mockBootstrapBackups = [{
      filename: "folium-20260817T000000Z-00000000-0000-0000-0000-000000000001.folium",
      created_at: "2026-08-17T00:00:00Z",
      folium_version: "0.1.0",
      schema_version: "012_backup_restore",
      document_count: 2,
      size_bytes: 40,
      verification_status: "incompatible",
    }];
    render(<MemoryRouter><SetupPage /></MemoryRouter>);
    fireEvent.click(screen.getByRole("button", { name: "Restore backup" }));
    expect(screen.getByText(/incompatible/)).toBeInTheDocument();
  });

  it("shows recovery copy while restoring", () => {
    mockBootstrapState = "restoring";
    render(<MemoryRouter><SetupPage /></MemoryRouter>);
    expect(screen.getByText(/Restore is in progress/)).toBeInTheDocument();
  });
});
