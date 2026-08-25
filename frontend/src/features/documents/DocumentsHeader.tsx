import { DocumentViewTabs } from "./DocumentViewTabs";
import type { LibraryView } from "./useDocumentsLibraryState";

interface DocumentsHeaderProps {
  view: LibraryView;
  onViewChange: (view: LibraryView) => void;
}

export function DocumentsHeader({ view, onViewChange }: DocumentsHeaderProps) {
  return (
    <div className="hidden border-b border-surface-border bg-surface px-6 py-3 md:block">
      <DocumentViewTabs view={view} onChange={onViewChange} />
    </div>
  );
}
