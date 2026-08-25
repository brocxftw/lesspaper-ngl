import { useMemo, useState } from "react";
import { AlertCircle, ChevronDown, Clock, FileStack, Inbox, Search } from "lucide-react";
import { Link } from "react-router-dom";
import type { Folder, Tag } from "@/lib/api/types";
import { cn } from "@/lib/utils";
import { FolderTree } from "@/components/folders/FolderTree";
import { SidebarTagList } from "@/components/tags/TagList";
import { Input } from "@/components/ui/Input";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/Sheet";
import type { LibraryView } from "./useDocumentsLibraryState";

interface Props { folders: Folder[]; tags: Tag[]; view: LibraryView; folderId?: string; tagIds: string[]; total: number; onViewChange: (view: LibraryView) => void; onFolderSelect: (id: string | undefined) => void; onTagToggle: (id: string) => void; }
const quick = [{ id: "all" as const, label: "All documents", icon: FileStack }, { id: "recent" as const, label: "Recently added", icon: Clock }, { id: "unprocessed" as const, label: "Unprocessed", icon: AlertCircle }];

export function MobileLibraryExplorer(props: Props) {
  const [open, setOpen] = useState(false); const [tab, setTab] = useState<"browse" | "tags">("browse"); const [query, setQuery] = useState("");
  const folderName = useMemo(() => props.folders.find((folder) => folder.id === props.folderId)?.name, [props.folders, props.folderId]);
  const label = folderName ?? (props.view === "recent" ? "Recently added" : props.view === "unprocessed" ? "Unprocessed" : "All documents");
  const tags = useMemo(() => props.tags.filter((tag) => tag.name.toLowerCase().includes(query.trim().toLowerCase())), [props.tags, query]);
  const chooseView = (view: LibraryView) => { props.onFolderSelect(undefined); props.onViewChange(view); setOpen(false); };
  const chooseFolder = (id: string) => { props.onFolderSelect(id); setOpen(false); };
  const chooseTag = (id: string) => { props.onTagToggle(id); setOpen(false); };
  return <Sheet open={open} onOpenChange={setOpen}>
    <SheetTrigger asChild><button type="button" className="flex h-11 w-full items-center justify-between rounded-[10px] border border-surface-border bg-surface px-3 text-left text-sm font-medium text-text-primary"><span className="truncate">{label}</span><ChevronDown className="h-4 w-4 shrink-0 text-text-muted" /></button></SheetTrigger>
    <p className="mt-1 text-xs text-text-muted">{props.total} {props.total === 1 ? "document" : "documents"}</p>
    <SheetContent side="right" className="!w-[min(92vw,420px)] !max-w-none p-0">
      <SheetHeader className="shrink-0 bg-surface"><SheetTitle>Library explorer</SheetTitle></SheetHeader>
      <div className="shrink-0 border-b border-surface-border bg-surface px-4 pb-3"><div className="grid grid-cols-2 rounded-lg bg-surface-muted p-1" role="tablist">{(["browse", "tags"] as const).map((item) => <button key={item} type="button" role="tab" aria-selected={tab === item} onClick={() => setTab(item)} className={cn("h-9 rounded-md text-sm font-medium capitalize focus-visible:outline focus-visible:outline-2 focus-visible:outline-focus", tab === item ? "bg-white text-text-primary shadow-sm" : "text-text-secondary")}>{item}</button>)}</div></div>
      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4 scrollbar-thin">
        {tab === "browse" ? <><p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-text-muted">Quick access</p><ul className="space-y-1">{quick.map(({ id, label: name, icon: Icon }) => { const selected = props.view === id && !props.folderId && props.tagIds.length === 0; return <li key={id}><button type="button" onClick={() => chooseView(id)} className={cn("flex min-h-11 w-full items-center gap-3 rounded-md px-3 text-left text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-focus", selected ? "bg-accent-muted text-text-primary" : "text-text-secondary hover:bg-surface-hover")}><Icon className={cn("h-4 w-4", selected ? "text-accent" : "text-text-muted")} />{name}</button></li>; })}<li><Link to="/inbox" className="flex min-h-11 items-center gap-3 rounded-md px-3 text-sm text-text-secondary hover:bg-surface-hover focus-visible:outline focus-visible:outline-2 focus-visible:outline-focus"><Inbox className="h-4 w-4 text-text-muted" />Inbox</Link></li></ul><div className="mt-6"><p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-text-muted">Folders</p><div className="[&_.group>button]:min-h-10 [&_.group>button]:w-7 [&_.group>div>button]:min-h-10"><FolderTree folders={props.folders} selectedFolderId={props.folderId} onSelect={chooseFolder} variant="surface" hideHeader /></div></div></> : <><p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-text-muted">Tags</p><div className="relative mb-3"><Search className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-text-muted" /><Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search tags..." className="h-10 pl-9" /></div><div className="[&_li>div>button]:min-h-10"><SidebarTagList tags={tags} selectedTagIds={props.tagIds} onSelect={chooseTag} variant="surface" /></div></>}
      </div>
    </SheetContent>
  </Sheet>;
}
