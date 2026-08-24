import { useMemo, useState } from "react";
import { MoreHorizontal } from "lucide-react";
import {
  useBackupRestoreStatus,
  useBackupSettings,
  useBackups,
  useCreateBackup,
  useDeleteBackup,
  useInspectBackup,
  useRestoreBackup,
  useUpdateBackupSettings,
  useVerifyBackup,
} from "@/lib/api/hooks";
import type { BackupRecord, BackupSettingsUpdate } from "@/lib/api/types";
import { ApiError } from "@/lib/api/client";
import { Button } from "@/components/ui/Button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/Dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/DropdownMenu";
import { Input } from "@/components/ui/Input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/Select";
import { Switch } from "@/components/ui/Switch";
import { formatBytes, formatDateTime } from "@/lib/utils";
import {
  SettingsCard,
  SettingsContent,
  SettingsDisclosure,
  SettingsEmptyState,
  SettingsInfoBanner,
  SettingsPageHeader,
  SettingsRow,
  SettingsSection,
  SettingsStatusBadge,
} from "@/features/settings/components";

const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

function statusLabel(value: string) {
  return value.replaceAll("_", " ");
}

export function BackupRestorePage() {
  const settings = useBackupSettings();
  const backups = useBackups({
    refetchInterval: 5000,
  });
  const restoreStatus = useBackupRestoreStatus(true);
  const update = useUpdateBackupSettings();
  const createBackup = useCreateBackup();
  const verify = useVerifyBackup();
  const inspect = useInspectBackup();
  const restore = useRestoreBackup();
  const remove = useDeleteBackup();
  const [confirm, setConfirm] = useState<{ type: "delete" | "restore"; record: BackupRecord } | null>(null);
  const [inspectText, setInspectText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const data = settings.data;
  const running = (backups.data || []).some((item) => item.status === "queued" || item.status === "running")
    || restoreStatus.data?.active;
  const repoUnavailable = data ? !data.repository.writable : false;
  const fieldsDisabled = !data?.enabled || update.isPending;

  const apply = async (patch: BackupSettingsUpdate) => {
    setError(null);
    try {
      await update.mutateAsync(patch);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save backup settings");
    }
  };

  const lastSuccessful = useMemo(
    () => (backups.data || []).find((item) => item.status === "completed"),
    [backups.data],
  );

  if (settings.isLoading) {
    return (
      <SettingsContent>
        <SettingsEmptyState>Loading backup settings…</SettingsEmptyState>
      </SettingsContent>
    );
  }
  if (settings.error || !data) {
    return (
      <SettingsContent>
        <p role="alert" className="text-danger">Backup settings are unavailable.</p>
      </SettingsContent>
    );
  }

  return (
    <SettingsContent>
      <SettingsPageHeader
        title="Backup & Restore"
        description="Protect your library with automatic backups and restore points."
        actions={
          <Button
            onClick={() =>
              void Promise.resolve(createBackup.mutateAsync()).catch((err) =>
                setError(err instanceof ApiError ? err.message : "Backup failed"),
              )
            }
            disabled={createBackup.isPending || !!running || repoUnavailable}
          >
            {createBackup.isPending ? "Queuing…" : "Back up now"}
          </Button>
        }
      />

      {error && <p role="alert" className="text-sm text-danger">{error}</p>}
      {restoreStatus.data?.active && (
        <SettingsInfoBanner>
          Restore in progress: {restoreStatus.data.stage}
        </SettingsInfoBanner>
      )}
      {restoreStatus.data?.error && (
        <p role="alert" className="text-sm text-danger">Restore failed: {restoreStatus.data.error}</p>
      )}

      <SettingsSection title="Automatic backups" description="Schedule versioned copies of your library.">
        <SettingsCard>
          <label className="flex cursor-pointer items-center justify-between gap-4">
            <span className="text-sm font-semibold text-text-primary">Enable automatic backups</span>
            <Switch
              checked={data.enabled}
              onCheckedChange={(checked) => void apply({ enabled: checked })}
              disabled={update.isPending || !!running}
              aria-label="Enable automatic backups"
            />
          </label>
          <div className={`mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-3 ${!data.enabled ? "opacity-50" : ""}`}>
            <div>
              <label className="text-xs text-text-muted">Schedule</label>
              <Select
                value={data.schedule_type}
                onValueChange={(value) => void apply({ schedule_type: value as BackupSettingsUpdate["schedule_type"] })}
                disabled={fieldsDisabled}
              >
                <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="daily">Daily</SelectItem>
                  <SelectItem value="weekly">Weekly</SelectItem>
                  <SelectItem value="interval_hours">Every N hours</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {data.schedule_type !== "interval_hours" && (
              <div>
                <label className="text-xs text-text-muted">Time (UTC)</label>
                <Input
                  className="mt-1"
                  type="time"
                  value={data.backup_time}
                  onChange={(event) => void apply({ backup_time: event.target.value })}
                  disabled={fieldsDisabled}
                />
              </div>
            )}
            {data.schedule_type === "weekly" && (
              <div>
                <label className="text-xs text-text-muted">Weekday</label>
                <Select
                  value={String(data.weekday ?? 0)}
                  onValueChange={(value) => void apply({ weekday: Number(value) })}
                  disabled={fieldsDisabled}
                >
                  <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {WEEKDAYS.map((label, index) => (
                      <SelectItem key={label} value={String(index)}>{label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
            {data.schedule_type === "interval_hours" && (
              <div>
                <label className="text-xs text-text-muted">Interval hours</label>
                <Input
                  className="mt-1"
                  type="number"
                  min={1}
                  value={data.interval_hours ?? 24}
                  onChange={(event) => void apply({ interval_hours: Number(event.target.value) })}
                  disabled={fieldsDisabled}
                />
              </div>
            )}
            <div>
              <label className="text-xs text-text-muted">Backups to keep</label>
              <Input
                className="mt-1"
                type="number"
                min={1}
                max={365}
                value={data.retention_count}
                onChange={(event) => void apply({ retention_count: Number(event.target.value) })}
                disabled={update.isPending}
              />
            </div>
          </div>
          <label className="mt-4 flex items-center gap-2 text-sm">
            <Switch
              checked={data.verify_after_backup}
              onCheckedChange={(checked) => void apply({ verify_after_backup: checked })}
              disabled={update.isPending}
              aria-label="Verify after creation"
            />
            Verify after creation
          </label>
          <SettingsDisclosure title="Advanced settings" className="mt-5">
            <div>
              <label className="text-xs text-text-muted">Repository subdirectory</label>
              <Input
                className="mt-1"
                value={data.repository_subdir}
                placeholder="optional, inside /backups"
                onBlur={(event) => void apply({ repository_subdir: event.target.value })}
                disabled={update.isPending}
              />
            </div>
          </SettingsDisclosure>
        </SettingsCard>
      </SettingsSection>

      <SettingsSection title="Backup status">
        <SettingsCard>
          <div className="grid gap-1 sm:grid-cols-2">
            <SettingsRow title="Last successful backup" description={formatDateTime(data.last_success_at)} />
            <SettingsRow title="Next scheduled backup" description={formatDateTime(data.next_run_at)} />
            <SettingsRow
              title="Last status"
              description={lastSuccessful ? statusLabel(lastSuccessful.status) : "—"}
            />
            <SettingsRow
              title="Repository"
              description={data.repository.writable ? "Writable" : data.repository.message}
              action={
                <SettingsStatusBadge tone={data.repository.writable ? "success" : "danger"}>
                  {data.repository.writable ? "Healthy" : "Unavailable"}
                </SettingsStatusBadge>
              }
            />
            <SettingsRow
              title="Last backup size"
              description={lastSuccessful?.size_bytes == null ? "—" : formatBytes(lastSuccessful.size_bytes)}
            />
            <SettingsRow
              title="Free space"
              description={data.repository.free_bytes == null ? "Unavailable" : formatBytes(data.repository.free_bytes)}
            />
          </div>
          {repoUnavailable && (
            <p role="alert" className="mt-3 text-sm text-danger">
              Backup repository is unavailable. lesspaper-ngl remains usable; backups will not run until `/backups` is writable.
            </p>
          )}
        </SettingsCard>
      </SettingsSection>

      <SettingsSection title="Backup history" description="Restore replaces the current library with a selected backup.">
        {(backups.data || []).length === 0 ? (
          <SettingsEmptyState bordered>No backups yet.</SettingsEmptyState>
        ) : (
          <ul className="divide-y divide-surface-border rounded-lg border border-surface-border bg-surface">
            {(backups.data || []).map((item) => (
              <li key={item.filename} className="flex items-center justify-between gap-3 px-4 py-3">
                <div className="min-w-0">
                  <p className="font-medium text-text-primary">{formatDateTime(item.created_at)}</p>
                  <p className="text-xs text-text-muted">
                    {item.size_bytes == null ? "—" : formatBytes(item.size_bytes)} · {item.folium_version || "unknown"} · {statusLabel(item.status)} · {statusLabel(item.verification_status)}
                    {item.progress_stage && item.status === "running" ? ` · ${item.progress_stage}` : ""}
                  </p>
                  {item.error_message && <p className="text-xs text-danger">{item.error_message}</p>}
                </div>
                {item.id && (
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button variant="ghost" size="icon" aria-label={`Actions for ${item.filename}`}>
                        <MoreHorizontal className="h-4 w-4" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem
                        disabled={!!running}
                        onSelect={() => void inspect.mutateAsync(item.id!).then((result) => setInspectText(result.messages.join("\n") || "Backup is ready to restore"))}
                      >
                        Inspect
                      </DropdownMenuItem>
                      <DropdownMenuItem disabled={!!running} onSelect={() => void verify.mutateAsync(item.id!)}>
                        Verify
                      </DropdownMenuItem>
                      <DropdownMenuItem disabled={!!running} onSelect={() => setConfirm({ type: "restore", record: item })}>
                        Restore
                      </DropdownMenuItem>
                      <DropdownMenuItem disabled={!!running} onSelect={() => setConfirm({ type: "delete", record: item })}>
                        Delete
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                )}
              </li>
            ))}
          </ul>
        )}
      </SettingsSection>

      <Dialog open={!!confirm} onOpenChange={(open) => !open && setConfirm(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{confirm?.type === "restore" ? "Restore this backup?" : "Delete this backup?"}</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-text-secondary">
            {confirm?.type === "restore"
              ? "This replaces the current lesspaper-ngl library with the selected backup. This cannot be undone from the UI."
              : "The backup file will be removed from the repository."}
          </p>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setConfirm(null)}>Cancel</Button>
            <Button
              variant="danger"
              onClick={() => {
                if (!confirm?.record.id) return;
                const action = confirm.type === "restore" ? restore.mutateAsync(confirm.record.id) : remove.mutateAsync(confirm.record.id);
                void action.catch((err) => setError(err instanceof ApiError ? err.message : "Action failed"));
                setConfirm(null);
              }}
            >
              {confirm?.type === "restore" ? "Restore lesspaper-ngl" : "Delete backup"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={inspectText != null} onOpenChange={(open) => !open && setInspectText(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Backup inspection</DialogTitle></DialogHeader>
          <p className="whitespace-pre-wrap text-sm text-text-secondary">{inspectText}</p>
          <DialogFooter>
            <Button onClick={() => setInspectText(null)}>Close</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </SettingsContent>
  );
}
