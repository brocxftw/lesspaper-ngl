/** Shared selection helpers for Documents list/grid. */

export function isEditableKeyboardTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable) return true;
  const tag = target.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
  return Boolean(target.closest("[contenteditable='true'], input, textarea, select"));
}

export function toggleIdInSet(
  selected: Set<string>,
  id: string,
  checked: boolean,
): Set<string> {
  const next = new Set(selected);
  if (checked) next.add(id);
  else next.delete(id);
  return next;
}

export function selectRangeIds(
  orderedIds: string[],
  fromIndex: number,
  toIndex: number,
): Set<string> {
  const start = Math.min(fromIndex, toIndex);
  const end = Math.max(fromIndex, toIndex);
  const next = new Set<string>();
  for (let i = start; i <= end; i += 1) {
    const id = orderedIds[i];
    if (id) next.add(id);
  }
  return next;
}

export function selectAllIds(orderedIds: string[]): Set<string> {
  return new Set(orderedIds);
}

export type DocumentsLayoutMode = "list" | "grid";

export const DOCUMENTS_LAYOUT_PREF_KEY = "lesspaper-ngl.documents.layoutMode";
export const DOCUMENTS_LAYOUT_PREF_KEY_LEGACY = "folium.documents.layoutMode";
