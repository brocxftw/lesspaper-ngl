import { useRef } from "react";
import { useNavigate } from "react-router-dom";
import { FolderUp, Upload } from "lucide-react";
import { useDocumentUploader } from "@/lib/api/upload";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/DropdownMenu";

const controlClassName =
  "inline-flex h-[41px] items-center gap-2 rounded-[10px] px-4 text-sm font-semibold " +
  "border border-transparent bg-accent text-accent-foreground shadow-[0_2px_6px_rgba(2,6,23,0.12)] " +
  "transition-colors duration-150 ease-out hover:bg-accent-hover disabled:opacity-60";

export function NavbarUpload() {
  const navigate = useNavigate();
  const uploader = useDocumentUploader();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);

  const afterUpload = async (files: FileList) => {
    await uploader.uploadFileList(files);
    navigate("/inbox?view=work");
  };

  return (
    <div className="max-md:hidden">
      <input
        ref={fileInputRef}
        type="file"
        multiple
        className="hidden"
        onChange={(e) => {
          if (e.target.files) void afterUpload(e.target.files);
          e.target.value = "";
        }}
      />
      <input
        ref={folderInputRef}
        type="file"
        className="hidden"
        // @ts-expect-error webkitdirectory is non-standard but widely supported
        webkitdirectory=""
        directory=""
        multiple
        onChange={(e) => {
          if (e.target.files) void afterUpload(e.target.files);
          e.target.value = "";
        }}
      />
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button type="button" data-tour="upload" className={controlClassName} disabled={uploader.busy}>
            <Upload className="h-4 w-4" />
            {uploader.busy ? "Uploading…" : "Upload"}
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onClick={() => fileInputRef.current?.click()}>
            <Upload className="h-3.5 w-3.5" />
            Upload files…
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => folderInputRef.current?.click()}>
            <FolderUp className="h-3.5 w-3.5" />
            Upload folder…
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
