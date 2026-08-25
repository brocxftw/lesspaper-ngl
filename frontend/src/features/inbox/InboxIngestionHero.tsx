import { useNavigate } from "react-router-dom";
import { CloudUpload, Lightbulb, Lock } from "lucide-react";
import type { useDocumentUploader } from "@/lib/api/upload";
import type { UploadEntry } from "@/lib/uploadTree";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/Button";
import { UploadDropzone } from "@/components/documents/UploadDropzone";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/Tooltip";

type DocumentUploader = ReturnType<typeof useDocumentUploader>;

const TIPS = [
  "Upload clear, legible documents for best results.",
  "PDFs with selectable text are typically processed faster.",
  "Large batches may remain queued while processing capacity is busy.",
  "Processing progress can be monitored from this workspace.",
];

interface InboxIngestionHeroProps {
  uploader: DocumentUploader;
  onBrowse: () => void;
}

export function InboxIngestionHero({ uploader, onBrowse }: InboxIngestionHeroProps) {
  const navigate = useNavigate();

  const handleEntries = async (entries: UploadEntry[]) => {
    const uploadPromise = uploader.uploadEntries(entries);
    navigate("/inbox?view=work");
    await uploadPromise;
  };

  return (
    <div className="mt-0 md:mt-5">
      <UploadDropzone
        onEntries={(entries) => void handleEntries(entries)}
        disabled={uploader.busy}
      >
        <div
          role="button"
          tabIndex={0}
          onClick={onBrowse}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              onBrowse();
            }
          }}
          className={cn(
            "flex min-h-[160px] cursor-pointer flex-col items-center justify-center rounded-[10px] border border-dashed border-accent bg-white px-5 py-4 text-center shadow-[0_1px_3px_rgba(20,33,43,0.05)] md:min-h-[200px] md:px-6 md:py-8",
            "transition-colors hover:border-accent-hover hover:bg-accent-muted",
            "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent",
          )}
        >
          <div className="flex h-11 w-11 items-center justify-center rounded-full bg-accent-muted md:h-[58px] md:w-[58px]">
            <CloudUpload className="h-6 w-6 text-accent md:h-7 md:w-7" strokeWidth={1.75} />
          </div>
          <h2 className="mt-2.5 text-[16px] font-bold leading-tight text-[#14212B] md:mt-3.5 md:text-[17px]">
            <span className="md:hidden">Upload documents</span>
            <span className="hidden md:inline">Drag & drop documents here</span>
          </h2>
          <p className="mt-1 text-xs text-[#42515D] md:hidden">PDF, DOCX, images and more</p>
          <p className="mt-1 hidden text-xs text-[#42515D] md:block">or click to browse</p>
          <p className="mt-1 hidden text-[11px] text-[#74828D] md:block">
            Supports PDF, DOCX, TXT, CSV, JPG, PNG and more
          </p>
          <Button
            type="button"
            className="mt-3 h-11 rounded-md bg-accent px-[18px] text-accent-foreground hover:bg-accent-hover md:mt-4 md:h-8"
            disabled={uploader.busy}
            onClick={(e) => {
              e.stopPropagation();
              onBrowse();
            }}
          >
            <span className="md:hidden">Choose files</span>
            <span className="hidden md:inline">Browse files</span>
          </Button>
          <Tooltip>
            <TooltipTrigger asChild>
              <p
                className="mt-5 hidden items-center gap-1.5 text-[10px] font-medium text-accent hover:text-accent-hover md:inline-flex"
                onClick={(e) => e.stopPropagation()}
                onKeyDown={(e) => e.stopPropagation()}
              >
                <Lightbulb className="h-3 w-3" strokeWidth={1.75} />
                Upload tips
              </p>
            </TooltipTrigger>
            <TooltipContent side="bottom" className="max-w-[280px] space-y-1.5 p-3">
              <p className="text-[11px] font-semibold text-white">Ingestion tips</p>
              <ul className="space-y-1.5 text-left">
                {TIPS.map((tip) => (
                  <li key={tip} className="flex gap-1.5 text-[11px] leading-snug text-white/85">
                    <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-accent" />
                    <span>{tip}</span>
                  </li>
                ))}
              </ul>
            </TooltipContent>
          </Tooltip>
          <p className="mt-2 hidden items-center gap-1.5 text-[10px] text-[#74828D] md:flex">
            <Lock className="h-3 w-3" strokeWidth={1.75} />
            Your files are processed securely and never shared.
          </p>
        </div>
      </UploadDropzone>
    </div>
  );
}
