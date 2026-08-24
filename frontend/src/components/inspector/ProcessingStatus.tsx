import { Check, Circle, X } from "lucide-react";
import { cn, formatDateTime } from "@/lib/utils";
import type { Document } from "@/lib/api/types";
import {
  getEmbeddingProgress,
  getRetrievalReadiness,
} from "@/features/documents/retrievalReadiness";

interface ProcessingStatusProps {
  document: Document;
}

function StatusItem({
  label,
  done,
  date,
  error,
  detail,
}: {
  label: string;
  done: boolean;
  date?: string | null;
  error?: string | null;
  detail?: string | null;
}) {
  return (
    <div className="flex items-start gap-2 py-1">
      {error ? (
        <X className="h-3.5 w-3.5 shrink-0 text-danger mt-0.5" />
      ) : done ? (
        <Check className="h-3.5 w-3.5 shrink-0 text-emerald-600 mt-0.5" />
      ) : (
        <Circle className="h-3.5 w-3.5 shrink-0 text-text-muted mt-0.5" />
      )}
      <div className="min-w-0">
        <p className={cn("text-[13px]", done ? "text-text-primary" : "text-text-secondary")}>
          {label}
        </p>
        {detail && !error && (
          <p className="text-[11px] text-text-muted">{detail}</p>
        )}
        {date && done && (
          <p className="text-[11px] text-text-muted">{formatDateTime(date)}</p>
        )}
        {error && <p className="text-[11px] text-danger">{error}</p>}
      </div>
    </div>
  );
}

export function ProcessingStatus({ document }: ProcessingStatusProps) {
  const readiness = getRetrievalReadiness(document);
  const progress = getEmbeddingProgress(document);
  const embeddingDone = document.has_embeddings && (document.chunks_failed ?? 0) === 0;
  const embeddingPartial =
    readiness === "partial" || ((document.chunks_failed ?? 0) > 0 && document.has_embeddings);
  const embeddingInProgress = readiness === "embedding";

  let embeddingLabel = "Embeddings generated";
  let embeddingDetail: string | null = null;
  if (embeddingInProgress && progress.total > 0) {
    embeddingLabel = `Embedding ${progress.embedded.toLocaleString()} / ${progress.total.toLocaleString()}`;
    embeddingDetail =
      progress.percent != null ? `${progress.percent}% complete` : "Embedding in progress…";
  } else if (embeddingPartial && progress.total > 0) {
    embeddingLabel = `Embeddings partial (${progress.failed} failed)`;
    embeddingDetail = `${progress.embedded.toLocaleString()} of ${progress.total.toLocaleString()} embedded`;
  } else if (document.document_indexed && !document.has_embeddings && progress.total > 0) {
    embeddingLabel = "Embeddings pending";
    embeddingDetail = `${progress.total.toLocaleString()} chunks indexed`;
  }

  return (
    <div className="space-y-0.5">
      <h4 className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-2">
        Processing
      </h4>
      <StatusItem label="OCR completed" done={document.ocr_completed} />
      <StatusItem label="Text extracted" done={document.text_extracted} />
      <StatusItem
        label="Document indexed"
        done={document.document_indexed}
        date={document.indexed_at}
        detail={
          document.document_indexed && progress.total > 0
            ? `${progress.total.toLocaleString()} chunks`
            : null
        }
      />
      {(document.has_embeddings ||
        embeddingInProgress ||
        embeddingPartial ||
        (document.document_indexed && (document.chunks_total ?? 0) > 0)) && (
        <StatusItem
          label={embeddingLabel}
          done={embeddingDone || embeddingPartial}
          date={document.embedding_finished_at}
          detail={embeddingDetail}
          error={document.embedding_error}
        />
      )}
      {document.processing_error && (
        <StatusItem
          label="Processing error"
          done={false}
          error={document.processing_error}
        />
      )}
      {(document.processing_status === "processing" || embeddingInProgress) && (
        <p className="text-[11px] text-warning mt-1">Processing in progress…</p>
      )}
    </div>
  );
}
