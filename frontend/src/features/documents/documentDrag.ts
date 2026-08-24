/** Custom MIME types for internal document-ID drag payloads. */
export const LESSPAPER_NGL_DOCUMENT_IDS =
  "application/x-lesspaper-ngl-document-ids";
/** Legacy MIME — still accepted when reading drops during the rebrand transition. */
export const FOLIUM_DOCUMENT_IDS = "application/x-folium-document-ids";

/** Session flag — custom MIME types are often hidden from `types` during dragover. */
let activeDocumentDragIds: string[] | null = null;

export function setDocumentDragData(
  dataTransfer: DataTransfer,
  documentIds: string[],
): void {
  const payload = JSON.stringify(documentIds);
  activeDocumentDragIds = documentIds;
  dataTransfer.setData(LESSPAPER_NGL_DOCUMENT_IDS, payload);
  dataTransfer.setData(FOLIUM_DOCUMENT_IDS, payload);
  dataTransfer.setData("text/plain", payload);
  dataTransfer.effectAllowed = "move";
}

export function clearDocumentDragData(): void {
  activeDocumentDragIds = null;
}

export function dataTransferHasDocuments(
  dataTransfer: DataTransfer | null | undefined,
): boolean {
  if (activeDocumentDragIds && activeDocumentDragIds.length > 0) return true;
  if (!dataTransfer) return false;
  const types = Array.from(dataTransfer.types ?? []);
  return (
    types.includes(LESSPAPER_NGL_DOCUMENT_IDS) ||
    types.includes(FOLIUM_DOCUMENT_IDS)
  );
}

export function getDocumentDragIds(
  dataTransfer: DataTransfer | null | undefined,
): string[] {
  if (activeDocumentDragIds && activeDocumentDragIds.length > 0) {
    return [...activeDocumentDragIds];
  }
  if (!dataTransfer) return [];
  const raw =
    dataTransfer.getData(LESSPAPER_NGL_DOCUMENT_IDS) ||
    dataTransfer.getData(FOLIUM_DOCUMENT_IDS) ||
    dataTransfer.getData("text/plain");
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((id): id is string => typeof id === "string" && id.length > 0);
  } catch {
    return [];
  }
}
