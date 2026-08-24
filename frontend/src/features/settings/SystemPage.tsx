import { useState } from "react";
import {
  useDiagnostics,
  useStorageMetrics,
  useSystemSummary,
} from "@/lib/api/hooks";
import { Button } from "@/components/ui/Button";
import { formatBytes } from "@/lib/utils";
import {
  SettingsCard,
  SettingsContent,
  SettingsDisclosure,
  SettingsEmptyState,
  SettingsPageHeader,
  SettingsSection,
  SettingsStatusBadge,
} from "@/features/settings/components";

function serviceTone(value: string): "success" | "warning" | "danger" | "neutral" {
  const normalised = value.toLowerCase();
  if (normalised === "healthy" || normalised === "ok" || normalised === "configured") return "success";
  if (normalised === "degraded" || normalised === "warning") return "warning";
  if (normalised === "unavailable" || normalised === "error" || normalised === "failed") return "danger";
  return "neutral";
}

function StorageDonut({
  used,
  total,
  free,
}: {
  used: number | null;
  total: number | null;
  free: number | null;
}) {
  const ratio = used != null && total ? Math.min(1, used / total) : 0;
  const circumference = 2 * Math.PI * 44;
  return (
    <div className="flex flex-wrap items-center gap-5">
      <svg viewBox="0 0 120 120" className="h-36 w-36" role="img" aria-labelledby="disk-title disk-desc">
        <title id="disk-title">Document library filesystem capacity</title>
        <desc id="disk-desc">
          {used == null || total == null ? "Capacity unavailable" : `${formatBytes(used)} used of ${formatBytes(total)}`}
        </desc>
        <circle cx="60" cy="60" r="44" fill="none" stroke="var(--color-surface-border)" strokeWidth="12" />
        <circle
          cx="60"
          cy="60"
          r="44"
          fill="none"
          stroke="var(--color-accent)"
          strokeWidth="12"
          strokeDasharray={`${ratio * circumference} ${circumference}`}
          transform="rotate(-90 60 60)"
        />
        <text x="60" y="57" textAnchor="middle" className="fill-text-primary text-[12px] font-semibold">
          {free == null ? "—" : formatBytes(free)}
        </text>
        <text x="60" y="73" textAnchor="middle" className="fill-text-muted text-[8px]">free</text>
      </svg>
      <div className="text-sm text-text-secondary">
        <p><strong className="text-text-primary">{used == null ? "Unavailable" : formatBytes(used)}</strong> used</p>
        <p>{total == null ? "Unavailable" : formatBytes(total)} total</p>
        <p>{free == null ? "Unavailable" : formatBytes(free)} free</p>
      </div>
    </div>
  );
}

export function SystemPage() {
  const { data, isLoading, error } = useSystemSummary();
  const { data: storage } = useStorageMetrics();
  const diagnostics = useDiagnostics();
  const [copyMessage, setCopyMessage] = useState<string | null>(null);
  const copyDiagnostics = async () => {
    const result = await diagnostics.mutateAsync();
    await navigator.clipboard.writeText(result.text);
    setCopyMessage("Diagnostics copied");
  };

  if (isLoading) {
    return (
      <SettingsContent>
        <SettingsEmptyState>Loading system status…</SettingsEmptyState>
      </SettingsContent>
    );
  }
  if (error || !data) {
    return (
      <SettingsContent>
        <p role="alert" className="text-danger">System status is unavailable.</p>
      </SettingsContent>
    );
  }

  return (
    <SettingsContent>
      <SettingsPageHeader
        title="System"
        description="View lesspaper-ngl's health, runtime and storage status."
        actions={
          <div className="text-right">
            <Button variant="outline" onClick={() => void copyDiagnostics()} disabled={diagnostics.isPending}>
              Copy diagnostics
            </Button>
            {copyMessage && <p aria-live="polite" className="mt-1 text-xs text-text-secondary">{copyMessage}</p>}
          </div>
        }
      />

      <SettingsSection id="application" title="Application health">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {[
            ["lesspaper-ngl version", data.version],
            ["Database", data.database_status],
            ["Storage", data.storage_status],
            ["Worker", data.worker_status],
            ["Jobs", `${data.queued_jobs} queued · ${data.running_jobs} running`],
            ["Documents", `${data.document_count.toLocaleString()} · ${data.indexed_document_count.toLocaleString()} indexed`],
          ].map(([label, value]) => (
            <SettingsCard key={label} padding="sm">
              <p className="text-xs text-text-muted">{label}</p>
              <div className="mt-1 flex items-center justify-between gap-2">
                <p className="font-semibold text-text-primary">{value}</p>
                {label !== "lesspaper-ngl version" && label !== "Jobs" && label !== "Documents" && (
                  <SettingsStatusBadge tone={serviceTone(String(value))}>{String(value)}</SettingsStatusBadge>
                )}
              </div>
            </SettingsCard>
          ))}
        </div>
      </SettingsSection>

      <SettingsSection id="runtime" title="Runtime" description={data.deployment_mode}>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {Object.entries(data.services).map(([service, status]) => (
            <SettingsCard key={service} padding="sm">
              <div className="flex items-center justify-between gap-2">
                <span className="font-semibold capitalize text-text-primary">{service}</span>
                <SettingsStatusBadge tone={serviceTone(status)}>{status}</SettingsStatusBadge>
              </div>
            </SettingsCard>
          ))}
        </div>
      </SettingsSection>

      <SettingsSection id="storage" title="Storage">
        <SettingsCard>
          <div className="grid gap-8 lg:grid-cols-2">
            <StorageDonut
              used={storage?.disk_used_bytes ?? null}
              total={storage?.disk_total_bytes ?? null}
              free={storage?.disk_free_bytes ?? null}
            />
            <dl className="space-y-3 text-sm">
              <div>
                <dt className="text-xs text-text-muted">lesspaper-ngl-owned files</dt>
                <dd className="font-medium">{storage?.folium_bytes == null ? "Unavailable" : formatBytes(storage.folium_bytes)}</dd>
              </div>
              <div>
                <dt className="text-xs text-text-muted">Database</dt>
                <dd className="font-medium">{storage?.database_bytes == null ? "Unavailable" : formatBytes(storage.database_bytes)}</dd>
              </div>
            </dl>
          </div>
          <ul className="mt-5 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            {Object.entries(storage?.categories || {}).map(([category, bytes]) => (
              <li key={category} className="rounded-md bg-surface-muted p-3 text-sm capitalize">
                {category.replaceAll("_", " ")}
                <strong className="block">{bytes == null ? "Unavailable" : formatBytes(bytes)}</strong>
              </li>
            ))}
          </ul>
        </SettingsCard>
      </SettingsSection>

      <SettingsDisclosure title="Advanced diagnostics">
        <dl className="grid gap-x-8 gap-y-3 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-xs text-text-muted">Schema revision</dt>
            <dd className="font-mono text-xs">{data.schema_revision}</dd>
          </div>
          <div>
            <dt className="text-xs text-text-muted">Process uptime</dt>
            <dd>{Math.floor(data.process_uptime_seconds / 60)} minutes</dd>
          </div>
          {Object.entries(data.runtime).map(([label, value]) => (
            <div key={label}>
              <dt className="text-xs capitalize text-text-muted">{label.replaceAll("_", " ")}</dt>
              <dd className="mt-1">{value ?? "Unavailable"}</dd>
            </div>
          ))}
          <div>
            <dt className="text-xs text-text-muted">Configured source</dt>
            <dd>{storage?.configured_source || "Unavailable"}</dd>
          </div>
          <div>
            <dt className="text-xs text-text-muted">Container mount</dt>
            <dd className="font-mono text-xs">{storage?.container_path || "Unavailable"}</dd>
          </div>
        </dl>
        {Object.keys(storage?.database_categories || {}).length > 0 && (
          <div className="mt-4">
            <h3 className="mb-2 text-sm font-medium">Database relations</h3>
            <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
              {Object.entries(storage?.database_categories || {}).map(([category, bytes]) => (
                <li key={category} className="rounded-md bg-surface-muted p-3 text-sm">
                  {category.replaceAll("_", " ")}
                  <strong className="block">{bytes == null ? "Unavailable" : formatBytes(bytes)}</strong>
                </li>
              ))}
            </ul>
          </div>
        )}
      </SettingsDisclosure>
    </SettingsContent>
  );
}
