import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { BrandLockup } from "@/components/brand/BrandMark";
import {
  useBootstrapBackups,
  useBootstrapInspect,
  useBootstrapRestore,
  useBootstrapSetup,
  useBootstrapStatus,
} from "@/lib/api/hooks";
import { ApiError } from "@/lib/api/client";
import { Button } from "@/components/ui/Button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/Dialog";
import { formatBytes, formatDateTime } from "@/lib/utils";

export function SetupPage() {
  const navigate = useNavigate();
  const status = useBootstrapStatus();
  const backups = useBootstrapBackups(status.data?.instance_state === "uninitialised");
  const setup = useBootstrapSetup();
  const inspect = useBootstrapInspect();
  const restore = useBootstrapRestore();
  const [mode, setMode] = useState<"choose" | "restore">("choose");
  const [selected, setSelected] = useState<string | null>(null);
  const [inspectText, setInspectText] = useState<string | null>(null);
  const [confirmRestore, setConfirmRestore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const uninitialised = status.data?.instance_state === "uninitialised";
  const restoring = status.data?.instance_state === "restoring" || status.data?.instance_state === "initialising";

  if (status.isLoading) {
    return <p className="flex min-h-screen items-center justify-center text-text-muted">Loading setup…</p>;
  }

  if (status.data?.ready) {
    navigate("/login", { replace: true, state: { notice: "lesspaper-ngl is ready. Sign in to continue." } });
  }

  const onNewInstall = async () => {
    setError(null);
    try {
      await setup.mutateAsync();
      navigate("/login", { replace: true, state: { notice: "lesspaper-ngl is ready. Sign in with the bootstrap admin account." } });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not complete setup");
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface-muted p-4">
      <div className="w-full max-w-lg rounded-lg border border-surface-border bg-surface p-6 shadow-sm">
        <div className="mb-6 text-center">
          <div className="mb-2">
            <BrandLockup
              variant="on-light"
              markSize={28}
              wordmarkClassName="text-2xl font-semibold"
            />
          </div>
          <p className="text-sm text-text-secondary">Set up a new library or restore from a backup in /backups.</p>
        </div>
        {error && <p role="alert" className="mb-3 text-sm text-danger">{error}</p>}
        {restoring && <p className="mb-3 text-sm text-accent">Restore is in progress. This page will continue when lesspaper-ngl is ready.</p>}
        {mode === "choose" && (
          <div className="space-y-3">
            <Button className="w-full" onClick={() => void onNewInstall()} disabled={setup.isPending || !uninitialised}>
              {setup.isPending ? "Setting up…" : "Set up new lesspaper-ngl"}
            </Button>
            <Button className="w-full" variant="secondary" onClick={() => setMode("restore")} disabled={!uninitialised}>
              Restore backup
            </Button>
          </div>
        )}
        {mode === "restore" && (
          <div className="space-y-4">
            {(backups.data || []).length === 0 ? (
              <p className="text-sm text-text-secondary">
                No backups were found in /backups. Copy a `.folium` bundle onto the backup mount, then refresh. Browser upload is not available in this version.
              </p>
            ) : (
              <ul className="space-y-2">
                {(backups.data || []).map((item) => (
                  <li key={item.filename}>
                    <button
                      type="button"
                      className={`w-full rounded-md border p-3 text-left text-sm ${selected === item.filename ? "border-accent bg-accent-muted" : "border-surface-border"}`}
                      onClick={() => setSelected(item.filename)}
                    >
                      <strong className="block">{formatDateTime(item.created_at)}</strong>
                      <span className="text-xs text-text-muted">
                        {item.folium_version} · schema {item.schema_version} · {item.document_count ?? 0} documents · {item.size_bytes == null ? "—" : formatBytes(item.size_bytes)} · {item.verification_status}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <div className="flex gap-2">
              <Button variant="ghost" onClick={() => setMode("choose")}>Back</Button>
              <Button
                variant="secondary"
                disabled={!selected}
                onClick={() => {
                  if (!selected) return;
                  void inspect.mutateAsync(selected).then((result) => {
                    setInspectText([result.compatible ? "Compatible" : "Incompatible", ...result.messages].join("\n"));
                  }).catch((err) => setError(err instanceof ApiError ? err.message : "Inspect failed"));
                }}
              >
                Inspect
              </Button>
              <Button disabled={!selected} onClick={() => setConfirmRestore(true)}>Restore lesspaper-ngl</Button>
            </div>
          </div>
        )}
      </div>

      <Dialog open={inspectText != null} onOpenChange={(open) => !open && setInspectText(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Backup inspection</DialogTitle></DialogHeader>
          <p className="whitespace-pre-wrap text-sm text-text-secondary">{inspectText}</p>
          <DialogFooter><Button onClick={() => setInspectText(null)}>Close</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={confirmRestore} onOpenChange={setConfirmRestore}>
        <DialogContent>
          <DialogHeader><DialogTitle>Restore lesspaper-ngl from this backup?</DialogTitle></DialogHeader>
          <p className="text-sm text-text-secondary">This initialises lesspaper-ngl from the selected backup. Existing empty database state will be replaced.</p>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setConfirmRestore(false)}>Cancel</Button>
            <Button
              variant="danger"
              onClick={() => {
                if (!selected) return;
                void restore.mutateAsync(selected).catch((err) => setError(err instanceof ApiError ? err.message : "Restore failed"));
                setConfirmRestore(false);
              }}
            >
              Restore lesspaper-ngl
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
