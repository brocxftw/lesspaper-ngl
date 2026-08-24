import { formatDateTime } from "@/lib/utils";
import { useJobs, useCancelJob } from "@/lib/api/hooks";
import type { Job } from "@/lib/api/types";
import { Button } from "@/components/ui/Button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/Select";
import { useState } from "react";
import { Loader2, CheckCircle, XCircle, Clock, Ban } from "lucide-react";

function StatusIcon({ status }: { status: Job["status"] }) {
  switch (status) {
    case "running":
      return <Loader2 className="h-3.5 w-3.5 animate-spin text-accent" />;
    case "completed":
      return <CheckCircle className="h-3.5 w-3.5 text-emerald-600" />;
    case "failed":
      return <XCircle className="h-3.5 w-3.5 text-danger" />;
    case "cancelled":
      return <Ban className="h-3.5 w-3.5 text-text-muted" />;
    default:
      return <Clock className="h-3.5 w-3.5 text-text-muted" />;
  }
}

function jobTypeLabel(type: string): string {
  return type
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

export function JobList() {
  const [statusFilter, setStatusFilter] = useState<string>("");
  const { data: jobs = [], isLoading, refetch, isFetching } = useJobs(statusFilter || undefined);
  const cancelJob = useCancelJob();

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between border-b border-surface-border bg-surface px-6 py-4">
        <div>
          <h1 className="text-lg font-semibold text-text-primary">Jobs</h1>
          <p className="text-sm text-text-secondary mt-0.5">
            Background processing tasks
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Select value={statusFilter || "all"} onValueChange={(v) => setStatusFilter(v === "all" ? "" : v)}>
            <SelectTrigger className="w-[140px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All statuses</SelectItem>
              <SelectItem value="queued">Queued</SelectItem>
              <SelectItem value="running">Running</SelectItem>
              <SelectItem value="completed">Completed</SelectItem>
              <SelectItem value="failed">Failed</SelectItem>
            </SelectContent>
          </Select>
          <Button variant="secondary" size="sm" onClick={() => refetch()} disabled={isFetching}>
            Refresh
          </Button>
        </div>
      </div>

      <div className="flex-1 overflow-auto">
        {isLoading ? (
          <p className="p-6 text-sm text-text-muted">Loading jobs…</p>
        ) : jobs.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <Clock className="h-10 w-10 text-text-muted/40 mb-3" />
            <p className="text-sm text-text-secondary">No jobs found</p>
          </div>
        ) : (
          <table className="w-full text-[13px]">
            <thead className="sticky top-0 bg-surface-muted border-b border-surface-border">
              <tr className="text-left text-xs font-medium text-text-muted uppercase">
                <th className="px-4 py-2">Status</th>
                <th className="px-4 py-2">Type</th>
                <th className="px-4 py-2">Document</th>
                <th className="px-4 py-2">Created</th>
                <th className="px-4 py-2">Error</th>
                <th className="px-4 py-2 w-20" />
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => (
                <tr
                  key={job.id}
                  className="border-b border-surface-border hover:bg-surface-hover"
                >
                  <td className="px-4 py-2">
                    <span className="flex items-center gap-2 capitalize">
                      <StatusIcon status={job.status} />
                      {job.status}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-text-primary">{jobTypeLabel(job.job_type)}</td>
                  <td className="px-4 py-2 text-text-secondary font-mono text-xs">
                    {job.document_id ? job.document_id.slice(0, 8) + "…" : "—"}
                  </td>
                  <td className="px-4 py-2 text-text-secondary whitespace-nowrap">
                    {formatDateTime(job.created_at)}
                  </td>
                  <td className="px-4 py-2 text-danger text-xs max-w-[200px] truncate">
                    {job.status === "failed" && job.error ? job.error : "—"}
                  </td>
                  <td className="px-4 py-2">
                    {(job.status === "queued" || job.status === "running") && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => cancelJob.mutate(job.id)}
                        disabled={cancelJob.isPending}
                      >
                        Cancel
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
