# Folium UI/UX Audit

> **Note:** Folium has been renamed to lesspaper-ngl. This 2026-08-10 audit retains historical Folium UI phrasing and is marked stale in `docs/README.md`.

**Document type:** Current-product reverse engineering (not a redesign)  
**Audience:** Product design (Google Stitch), UX architecture, frontend planning  
**Vocabulary:** Terms follow [`ubiquitous-language.md`](../../ubiquitous-language.md)  
**Evidence date:** 2026-08-10  
**Codebase:** Folium frontend (`frontend/src`) + API hooks (`frontend/src/lib/api`)

---

## 1. Executive overview

Folium is a **self-hosted, AI-optional document management** product. Organisation and evidence come first; AI enhances filing and Ask Folium, it is not infrastructure.

### Product mental model

```text
Ingest → Inbox (review / Process) → Library (browse / evidence search)
                                      ↓
                              Document viewer + Inspector
                                      ↓
                         Ask Folium (scoped, single-turn, citations)
```

| Pillar | User-facing meaning | Primary surfaces |
|--------|---------------------|------------------|
| **Ingestion** | Upload or consume → preflight (text/OCR + optional AI suggestions) → human **Process** | Inbox, upload dropzones |
| **Library** | Browse and organise non-trashed documents (folders, tags, views) | Documents workspace |
| **Retrieval** | Find evidence (keyword / semantic / hybrid) without chat | Documents header search, Search workspace |
| **Ask Folium** | Single-turn Q&A over a frozen scope with validated citations | AI drawer, Ask route |
| **Ops / admin** | Jobs, trash, AI providers/policy, system, logs, users | Jobs, Trash, Settings |

### What Folium is not (confirmed absent)

- No YouTube / URL extraction UI
- No multi-turn chat or streaming Ask
- No Shared with me / Activity feed
- No Starred / favourites (planned only)
- Guest routes have no branded public 404 (unknown guest URLs redirect toward login)

### Architecture summary (UX-relevant)

| Concern | Implementation |
|---------|----------------|
| Routing | React Router (`App.tsx`) |
| Auth | Cookie session + CSRF; `AuthGuard` / `GuestGuard` |
| Shell | `AppShell` sidebar + main |
| Data | TanStack Query hooks in `lib/api/hooks.ts` |
| Library URL state | Query params on `/documents` (`useDocumentsLibraryState`) |
| Primary library | Documents workspace (explorer + results + viewer modal + AI drawer) |
| Standalone parity routes | `/search`, `/ask` |

Source:
- `frontend/src/App.tsx`
- `frontend/src/components/layout/AppShell.tsx`
- `ubiquitous-language.md`

---

## 2. Application / page inventory

```text
Folium
├── Auth (guest, no AppShell)
│   ├── Login                         /login
│   ├── Register                      /register
│   ├── Forgot password               /forgot-password
│   └── Reset password                /reset-password
│
├── AppShell (authenticated)
│   ├── Documents workspace           /documents          [persistent place]
│   │   ├── Explorer sidebar          (in-page)
│   │   ├── Browse results            list | grid
│   │   ├── Evidence search results   when q non-empty
│   │   ├── Document viewer modal     ?doc=               [temporary]
│   │   ├── AI drawer (Ask Folium)    sheet               [temporary]
│   │   └── Move to folder dialog                         [temporary]
│   ├── Inbox                         /inbox              [persistent place]
│   │   ├── Preview dialog                                [temporary]
│   │   ├── Move / remove dialogs                         [temporary]
│   │   └── Suggestion chips                              [inline]
│   ├── Search workspace              /search             [persistent place]
│   ├── Ask workspace                 /ask                [persistent place]
│   │   └── AI drawer                                     [temporary]
│   ├── Jobs                          /jobs               [persistent place]
│   ├── Trash                         /trash              [persistent place]
│   ├── Settings                      /settings/*         [persistent place]
│   │   ├── Profile                   /settings/profile
│   │   ├── Users (admin)             /settings/profile/users
│   │   ├── Artificial Intelligence   /settings/artificial-intelligence
│   │   │   └── tabs: usage | models | providers | policy | advanced
│   │   ├── System (admin)            /settings/system
│   │   ├── Logs (admin)              /settings/logs
│   │   └── About                     /settings/about
│   └── Not found                     * (auth)
│
└── Legacy redirects
    ├── /documents/folder/:folderId[/:documentId] → query params
    ├── /documents/:documentId → ?doc=
    └── settings aliases → new settings paths
```

### Route table

| Route | Surface | Parent layout | Persistence | Entry points |
|-------|---------|---------------|-------------|--------------|
| `/login` | Login | GuestGuard | Page | Direct, AuthGuard redirect |
| `/register` | Register | GuestGuard | Page | Login link, invite URL |
| `/forgot-password` | Forgot password | GuestGuard | Page | Login link |
| `/reset-password` | Reset password | GuestGuard | Page | Admin-approved token link |
| `/` | Redirect | AuthGuard | — | → `/documents` |
| `/documents` | Documents workspace | AppShell | Persistent | Nav, default landing |
| `/documents?...` | Same + URL state | AppShell | Persistent | Folder/tag/search deep links |
| `/inbox` | Inbox | AppShell | Persistent | Nav, explorer Inbox link, badge |
| `/search` | Search | AppShell | Persistent | Nav |
| `/ask` | Ask launcher | AppShell | Persistent | Nav, Search “Ask about results” |
| `/jobs` | Jobs | AppShell | Persistent | Nav |
| `/trash` | Trash | AppShell | Persistent | Nav, badge |
| `/settings` | → profile | SettingsLayout | Persistent | Shell settings icon |
| `/settings/profile` | Profile | SettingsLayout | Persistent | Settings nav |
| `/settings/profile/users` | Users | SettingsLayout | Persistent | Profile link (admin) |
| `/settings/artificial-intelligence` | AI settings | SettingsLayout | Persistent | Settings nav (admin) |
| `/settings/system` | System | SettingsLayout | Persistent | Settings nav (admin) |
| `/settings/logs` | Logs | SettingsLayout | Persistent | Settings nav (admin) |
| `/settings/about` | About | SettingsLayout | Persistent | Settings nav |
| `*` (auth) | Not found | AppShell | Page | Unknown paths |

Source: `frontend/src/App.tsx`

---

## 3. Navigation architecture

### Application map (places vs actions vs overlays)

```text
App
│
├── [Place] Inbox
│   ├── [Action] Upload files/folder
│   ├── [Action] Assign folder / tags / type
│   ├── [Action] Accept/reject AI suggestions
│   ├── [Action] Process
│   ├── [Action] Remove from queue / Retry preflight
│   └── [Overlay] Preview dialog
│
├── [Place] Documents workspace
│   ├── [Place-slice] Quick Access: All | Recently added | Unprocessed
│   ├── [Place-slice] Folder / Tag filters
│   ├── [Workflow] Browse ↔ Evidence search (q)
│   ├── [Action] Upload, Move, Tag, Trash, Ask
│   ├── [Overlay] Document viewer + Inspector
│   └── [Overlay] AI drawer
│
├── [Place] Search workspace
│   ├── [Action] Evidence search + filters
│   └── [Nav] Open hit → Documents viewer; Ask → /ask
│
├── [Place] Ask workspace
│   └── [Overlay] AI drawer (opens immediately)
│
├── [Place] Jobs
│   └── [Action] Cancel job
│
├── [Place] Trash
│   └── [Action] Restore / Purge / Empty trash
│
└── [Place] Settings
    ├── Profile / Users / AI / System / Logs / About
    └── [Overlay] Provider, assignment, user confirm dialogs; log Sheet
```

### Primary navigation (AppShell)

Persistent left sidebar:

| Item | Route | Badge |
|------|-------|-------|
| Inbox | `/inbox` | Inbox count (`useInboxCount`) |
| Documents | `/documents` | — |
| Search | `/search` | — |
| Ask | `/ask` | — |
| Jobs | `/jobs` | — |
| Trash | `/trash` | Trash total (`useTrashCount`) |

Footer: avatar / display name / Admin|User, Settings, Log out, app version (`useHealth`).

**Collapse:** Persisted `folium.sidebarOpen`. Collapsed = icon rail + tooltips; badges become accent dots.

**Library explorer in AppShell:** Folder tree + Tags shown when sidebar expanded **and** route is **not** `/documents` or `/settings`. Selecting folder/tag navigates to `/documents?folder=` or `?tag=`. On Documents, the **in-page explorer sidebar** owns folders/tags instead.

Source: `frontend/src/components/layout/AppShell.tsx`

### Secondary / contextual navigation

| Mechanism | Where | Behaviour |
|-----------|-------|-----------|
| Documents Quick Access | Explorer | All / Recently added / Unprocessed / link to Inbox |
| Library view tabs | Documents | All / Recently added / Unprocessed |
| Search mode tabs | Documents header, Search | Hybrid / Keyword / Semantic |
| Settings section nav | SettingsLayout | Profile, AI, System, Logs, About (+ admin filter) |
| AI settings tabs | Artificial Intelligence | `?tab=` usage\|models\|providers\|policy\|advanced |
| Inbox status tabs | Inbox | All / Ready / Needs review / Failed / Preparing |
| Inspector tabs | Viewer | Overview / Metadata / OCR |
| Breadcrumbs | Documents (folder) | Display-only path string (**not** clickable navigators) |
| Viewer prev/next | Document viewer modal | Walk current result set |
| Citation → viewer | Ask / Search | Opens `/documents?doc=&viewerPage=` |

### Back / dismissal behaviour

| Surface | Dismiss / back |
|---------|----------------|
| Document viewer modal | Close clears `doc` query param; library remains |
| AI drawer | Sheet close; scope/question local state reset on reopen with new initialScope |
| Inbox preview | Dialog close |
| Auth success | Replace navigate to `/documents` or `/login` |
| Legacy document URLs | One-way redirect to query-param Documents URL |

---

## 4. Detailed page specifications

---

## Login

### Purpose

Authenticate an existing user into a session. Users arrive via direct URL, logout, or AuthGuard redirect. AuthGuard stores `location` in router state as `from`, but Login always navigates to `/documents` on success (the `from` value is unused).

### Layout structure

```text
┌────────────────────────────────────┐
│         [Leaf] Folium              │
│         Sign in to continue        │
│  ┌──────────────────────────────┐  │
│  │ Username                     │  │
│  │ Password                     │  │
│  │ [Sign in]                    │  │
│  │ Forgot password · Create…    │  │
│  └──────────────────────────────┘  │
└────────────────────────────────────┘
```

Centered card on muted surface; no AppShell.

### Visual elements

| Element | Type | Location | Content | User action | Result |
|---------|------|----------|---------|-------------|--------|
| Brand leaf + Folium | Brand | Top | Product name | None | Identity |
| Username | Input | Form | Username | Type | Validates non-empty |
| Password | Input | Form | Password | Type | Validates non-empty |
| Sign in | Button | Form | Sign in / Signing in… | Click/submit | `POST /api/auth/login` |
| Notice banner | Text | Form top | e.g. after password change | None | Informational |
| Field/root errors | Text | Form | Validation / API message | None | Blocks or explains failure |
| Forgot password | Link | Footer | Forgot password | Click | → `/forgot-password` |
| Create account | Link | Footer | Create account | Click | → `/register` (if registration allowed) |

### Information displayed

- Product brand (primary)
- Optional success notice from navigation state
- Validation and API errors
- Registration availability (hides create link when closed; default shows while status loading)

### Interactions

```text
User submits credentials
→ Button shows “Signing in…”
→ POST /api/auth/login
→ On success: navigate replace to /documents
→ On failure: root error “Invalid username or password” or ApiError.message
```

### Page states

| State | Visual |
|-------|--------|
| Initial | Empty form |
| Validation error | Field messages |
| Pending | Disabled/busy button label |
| Backend error | Root error |
| Registration closed | Create account link hidden |
| Post-reset notice | Notice text above form |

### Modals / dialogs / drawers

None.

Source: `frontend/src/features/auth/LoginPage.tsx`, `AuthGuard.tsx`

---

## Register

### Purpose

Create an account when open registration is enabled, or via invite token (`?invite=`).

### Layout structure

Same guest card layout as Login.

### Visual elements

| Element | Type | Location | Content | User action | Result |
|---------|------|----------|---------|-------------|--------|
| Username | Input | Form | 3–32 alnum/_ | Type | Zod validation |
| Display name | Input | Form | Optional | Type | Defaults to username if empty |
| Password | Input | Form | ≥8 chars | Type | Validation |
| Create account | Button | Form | Submit | Click | `POST /api/auth/register` |
| Invite banner | Banner | Form | Signing up with an invite | None | Indicates invite mode |
| Closed registration | Message | Card | Registration closed | Link to login | Blocks form |

### Interactions

```text
User submits valid form
→ POST /api/auth/register (invite_token if present)
→ Success → /documents
```

### Page states

Initial · validation error · pending · API error · invite mode · registration closed.

Source: `frontend/src/features/auth/RegisterPage.tsx`

---

## Forgot password

### Purpose

Request an admin-approved password reset (no email delivery). User is told an admin must approve and share a one-time link out-of-band.

### Visual elements

| Element | Type | Action | Result |
|---------|------|--------|--------|
| Username | Input | Type | Required |
| Request reset | Button | Submit | `POST /api/auth/forgot-password` |
| Success message | Text | — | Stored as success-typed root message; button disabled |
| Back to login | Link | Click | → `/login` |

Source: `frontend/src/features/auth/ForgotPasswordPage.tsx`

---

## Reset password

### Purpose

Set a new password using `?token=` from an approved reset request.

### Visual elements

| Element | Type | Action | Result |
|---------|------|--------|--------|
| Token validation | Loading/invalid UI | Auto | `GET /api/auth/reset-password/validate` |
| New password | Input | Type | ≥8 |
| Confirm password | Input | Type | Must match |
| Set password | Button | Submit | `POST /api/auth/reset-password` → `/login` with notice |
| Invalid token | Message + links | — | Forgot password / Login |

Source: `frontend/src/features/auth/ResetPasswordPage.tsx`

---

## Documents workspace

### Purpose

Primary library surface: browse, filter, evidence-search, organise (folders/tags), upload into context folder, open viewer, and Ask Folium. Default authenticated landing page.

**Arrival:** Nav “Documents”, `/`, AppShell folder/tag picks, Search hit open, citation links, legacy URL redirects.

### Layout structure

```text
┌ AppShell sidebar ─┬──────────────────────────────────────────────┐
│ (nav only; no     │ DocumentsHeader (title, search, mode, Ask,   │
│  library explorer │ Upload)                                      │
│  on this route)   ├──────────────────────────────────────────────┤
│                   │ UploadStatusBar (when uploading / summary)   │
│                   ├──────────┬───────────────────────────────────┤
│                   │ Explorer │ Breadcrumbs (if folder)           │
│                   │ Quick    │ View tabs                         │
│                   │ Access   │ RecentDocuments (conditional)     │
│                   │ Folders  │ Bulk toolbar OR Results toolbar   │
│                   │ Tags     │ Table | Grid | Evidence results   │
│                   │ (md+)    │                                   │
└───────────────────┴──────────┴───────────────────────────────────┘
+ DocumentViewerModal (when ?doc=)
+ AIChatDrawer (when open)
```

Whole main area wrapped in `UploadDropzone` (drag files/folders). Explorer hidden below `md`.

### Visual elements

| Element | Type | Location | Content | User action | Result |
|---------|------|----------|---------|-------------|--------|
| Title / subtitle | Heading | Header | Folder name or “Documents” + context subtitle | None | Orient |
| Search library | Input | Header | Query | Type (300ms debounce) / submit | Sets `q` → evidence search when non-empty |
| Hybrid / Keyword / Semantic | Tabs | Header | Search mode | Click | Sets `smode`; Semantic disabled if `semantic_available === false` |
| Semantic unavailable note | Text | Header | Coverage warning | None | Explains disabled semantic |
| Ask Folium | Button | Header | Ask Folium | Click | Opens AI drawer with smart default scope |
| Upload | Dropdown | Header | Upload files… / Upload folder… | Click | File picker → `POST /api/documents/upload` with current `folder_id` |
| Drop overlay | Overlay | Page | Drop files or folders | Drop | Upload entries |
| Upload status | Bar | Below header | Progress / created / duplicates / failed | Dismiss | Clears summary |
| Quick Access: All documents | Nav item | Explorer | All | Click | `view=all`, clear folder |
| Recently added | Nav item | Explorer | Recent | Click | `view=recent` |
| Unprocessed | Nav item | Explorer | Unprocessed | Click | `view=unprocessed` |
| Inbox link | Link | Explorer | Inbox | Click | → `/inbox` |
| Folder tree | Tree | Explorer | Logical folders | Select / drop docs / context create·rename·trash | Navigate or bulk move / folder APIs |
| Tag list | List | Explorer | Tags | Toggle | `tag` query filters |
| Breadcrumbs | Text | Main | Folder path | None | Display only |
| View tabs | Tabs | Main | All / Recently added / Unprocessed | Click | Patch `view` |
| Recent cards | Card strip | Main | Newest docs (≤5) | Click | Open viewer |
| Filter chips | Chips | Results toolbar | Search/Tag/Folder | Clear | Removes filter |
| Range text | Text | Results toolbar | Page range | None | Orientation |
| List / Grid toggle | Toggle | Results toolbar | Layout | Click | Persists `folium.documents.layoutMode` |
| Sort | Select | Results toolbar | Sort fields | Change | Patch sort/order |
| Document row | Row | Table | Title, folder, tags, pages·size, readiness, added | Click open; checkbox select; drag | Viewer / selection / move |
| Document card | Card | Grid | Thumbnail/title/meta/readiness | Same | Same |
| Select-all | Checkbox | Table header | — | Click | Select page set |
| Bulk: Move / Tag / Ask / Trash / Clear | Buttons | Bulk toolbar | Actions | Click | Bulk API or drawer |
| Evidence hit cards | Cards | Evidence mode | Title, readiness, snippet, matches | Open / expand / Ask | Viewer or Ask |
| Pagination | Controls | Results | Page | Change | Patch `page` |
| Empty / loading / updating | Status | Main | Messages | None | Communicate state |
| Retrieval readiness badge | Badge | Row/card/viewer | Stage label | None | Communicates readiness |

### Information displayed

**Primary:** Document title, result list/grid, search query/mode, current folder/view.

**Secondary:** Folder leaf name, tags (max 2 in row), page count, file size, added date, retrieval readiness.

**Contextual / hidden until open:** Full metadata, OCR page text, AI summary, ingestion history, pending suggestions (inspector).

**Evidence mode extras:** Document total, match total, effective mode, semantic coverage warnings, nested search matches (kind, page, snippet).

### Interactions (selected)

```text
User types non-empty query in Documents header
→ After debounce, URL q set
→ Browse list query disabled; POST /api/search runs
→ EvidenceSearchResults replace table/grid
→ Bulk/results toolbars for browse hidden

User clicks a document row (no modifiers)
→ openDocument → ?doc=id
→ DocumentViewerModal opens; GET /api/documents/:id
→ Inspector loads; content/download as needed

User Shift/Ctrl-clicks or uses checkboxes
→ Selection model updates; bulk toolbar appears
→ Move → MoveToFolderDialog → POST /api/documents/bulk {action:move}
→ Tag → tag picker → bulk tag
→ Trash → bulk trash
→ Ask → AI drawer scope=documents

User drops documents onto a folder
→ bulk move to that folder_id

User clicks Ask Folium in header
→ Scope priority: active evidence search → selection → open doc → folder_tree → library
→ AI drawer opens
```

### Page states

| State | Visual change |
|-------|---------------|
| Initial / populated browse | Table or grid of library docs |
| Empty | View-specific empty copy + drop hint |
| Loading | “Loading documents…” |
| Refreshing | “Updating…” while fetching |
| Evidence search active | Evidence cards; subtitle “Evidence search…” |
| No evidence matches | “No evidence matches this search” |
| Searching | “Searching…” |
| Semantic unavailable | Mode tab disabled + note/banner |
| Selection active | Bulk toolbar replaces results toolbar |
| Upload busy | Upload controls disabled; status bar progress |
| Viewer open | Near-fullscreen modal over library |
| Ask not ready (doc) | Badge + Ask disabled in viewer |
| List/query error | **Unverified / weak:** pages do not render dedicated `isError` UI for list/search |

### Modals / dialogs / drawers

#### Document viewer modal

| Field | Detail |
|-------|--------|
| Trigger | Open document (`?doc=`) |
| Title | Document title + readiness badge |
| Purpose | Preview original + inspect/edit filing metadata + OCR |
| Layout | Header (Ask, prev/next, close) · left DocumentViewer · right Inspector (md+) |
| Primary actions | Navigate pages, zoom, download/print/open original; Ask if ask-ready; edit title/notes |
| Secondary | Re-embed, suggest tags & folder, retry OCR/preflight, accept/reject suggestions |
| Dismissal | Close clears `doc`; Esc/overlay per Dialog |

#### Move to folder dialog

| Field | Detail |
|-------|--------|
| Trigger | Bulk Move |
| Purpose | Choose destination logical folder |
| Primary | Confirm → bulk move |
| Secondary | Cancel |

#### Folder create / rename / delete dialogs

| Field | Detail |
|-------|--------|
| Trigger | FolderTree actions |
| APIs | `POST/PATCH /api/folders`, `POST /api/folders/:id/trash` |
| Delete | Soft-trash folder |

#### AI drawer

See [AI drawer (Ask Folium)](#ai-drawer-ask-folium) (shared).

Source:
- `frontend/src/features/documents/DocumentsPage.tsx`
- `useDocumentsLibraryState.ts`
- `DocumentExplorerSidebar.tsx`, `DocumentsHeader.tsx`
- `DocumentBulkToolbar.tsx`, `DocumentViewerModal.tsx`
- `components/documents/*`, `components/inspector/*`, `components/viewer/DocumentViewer.tsx`

---

## Inbox

### Purpose

Queue for newly ingested documents that need review and **Process** before final library indexing. Users upload here, correct filing metadata, accept AI suggestions, then Process.

**Arrival:** Primary nav (with count badge), Documents explorer Inbox link.

### Layout structure

```text
┌ AppShell ─┬─────────────────────────────────────────────┐
│           │ Header: Inbox + AI availability + Upload    │
│           │ UploadStatusBar                             │
│           │ Status tabs OR bulk action bar              │
│           │ Search + Sort                               │
│           │ InboxTable                                  │
│           │ Footer toast (process/remove results)       │
└───────────┴─────────────────────────────────────────────┘
+ Preview dialog, Move dialog, Remove confirm
```

No explorer sidebar; AppShell may show library explorer beside Inbox.

### Visual elements

| Element | Type | Location | Content | User action | Result |
|---------|------|----------|---------|-------------|--------|
| Title / subtitle | Heading | Header | Inbox / awaiting review | None | Orient |
| AI suggestions note | Text | Header | Available · N pending / Unavailable | None | AI state |
| Upload dropdown | Dropdown | Header | Files / folder | Click | Upload (no folder_id; server Inbox default) |
| Status tabs | Tabs | Toolbar | All/Ready/Needs review/Failed/Preparing + counts | Click | Filter `inbox_status` |
| Search | Input | Toolbar | Filter queue | Type | List `q` |
| Sort | Dropdown | Toolbar | Date added / Modified / Title + order | Change | List sort |
| Selection count | Text | Bulk bar | N selected | — | — |
| Assign folder | Button | Bulk | — | Opens Move dialog | Per-id bulk move |
| Add tags | Popover | Bulk | Tag list | Pick | Bulk tag |
| Remove | Button | Bulk | — | Confirm dialog | `POST /api/documents/remove-from-queue` |
| Process N | Button | Bulk/toolbar | Process count | Click | `POST /api/documents/process` |
| Row checkbox | Checkbox | Table | — | Toggle | Selection |
| Filename / meta | Text | Document col | Primary name + secondary meta | Click row | Preview |
| Title suggestion chip | Chip | Document col | Suggested title | Accept/Reject | Suggestion APIs |
| Folder control | Control | Folder col | Pending path or folder | Set/clear | Metadata PATCH |
| Folder suggestion | Chip | Folder col | AI path | Accept/Reject | Suggestion APIs |
| Tags control | Control | Tags col | Tags | Add/create | Metadata / create tag |
| Type control | Select | Type col | Document type | Change | Metadata |
| Status badge | Badge | Status col | preparing/ready/needs_review/failed | None | Queue state |
| Preview | Icon button | Actions | — | Click | Preview dialog |
| Retry | Icon button | Actions (failed) | — | Click | `POST .../retry-preflight` |
| Remove | Icon button | Actions | — | Confirm | Remove from queue |
| Result toast | Banner | Bottom | Processed/skipped/failed | Dismiss | Clears message |

### Information displayed

- Inbox status (queue) — distinct from retrieval readiness
- Filename, title suggestions, pending folder path, tags, type
- AI suggestion availability and pending count
- Process eligibility (implicit via Process count)
- Errors on failed docs (preview / badge context)

### Interactions

```text
User uploads files
→ Sequential POST /api/documents/upload
→ Refetch inbox; docs appear as preparing → ready/needs_review/failed
→ Poll every 3s while preparing/processing

User sets folder path (existing folder or pending path)
→ PATCH metadata; needs_review cleared when target present

User clicks Process
→ Targets = selected processable OR all processable in list
→ POST /api/documents/process
→ Toast with processed/skipped/failed counts
→ Successful docs leave Inbox for library indexing
```

**Processable rule (UI):** not `preparing`/`failed`; and has `pending_folder_path` OR a non-Inbox `folder_path`.

### Page states

| State | Visual |
|-------|--------|
| Loading | “Loading inbox…” |
| Empty | “Inbox is clear” + Upload CTA |
| Populated | Table rows |
| Preparing (live) | Status badge; auto-refresh |
| AI unavailable | Muted header note; manual filing still works |
| AI available | Emerald note + pending count |
| Selection | Bulk bar replaces status tabs row content |
| Process pending | Process button disabled |
| Remove confirmation | Destructive dialog |
| Result | Bottom toast |
| List error | **Unverified / weak:** no dedicated error panel |

### Modals

#### Inbox preview dialog

| Field | Detail |
|-------|--------|
| Trigger | Row click / Preview |
| Content | DocumentViewer + status/error + suggestions + folder/tags/type controls |
| Nav | Prev/next within current filtered list |
| Not included | Full Inspector tabs, Ask Folium |

#### Remove from queue dialog

Destructive confirm; primary Remove; cancel dismisses.

#### Move to folder dialog

Same shared component as Documents.

Source: `frontend/src/features/inbox/*`

---

## Search workspace

### Purpose

Standalone evidence search with richer filters (folder, single tag, readiness). Complements Documents header search. Does not invoke Ask/chat models.

### Layout structure

```text
┌ Header: Search title                                    │
│ [Query] [Folder] [Tag] [Readiness] [Go]                 │
│ Hybrid | Keyword | Semantic                             │
├─────────────────────────────────────────────────────────┤
│ EvidenceSearchResults (totals, warnings, Ask link, hits)│
└─────────────────────────────────────────────────────────┘
```

### Visual elements

| Element | Type | Action | Result |
|---------|------|--------|--------|
| Query | Input | Debounce 300ms / submit | `?q=` → `POST /api/search` when non-empty |
| Folder select | Select | Change | Folder filter, descendants included |
| Tag select | Select | Change | Single tag filter |
| Readiness select | Select | any / indexed / semantic / unprocessed | Maps to `document_indexed` / `has_embeddings` / `unprocessed` |
| Mode tabs | Tabs | Change mode | Semantic disabled if unavailable |
| Hit card | Card | Click | → `/documents?doc=&viewerPage=` |
| Expand matches | Disclosure | Expand | Page/chunk evidence; open at page |
| Ask Folium about these results | Link/button | Click | → `/ask?q=<query>` |

### Information displayed

Query, mode, filters, document/match totals, effective mode, semantic coverage, snippets (sanitized), readiness per hit.

### Page states

Idle (no query) · Searching · Results · No matches · Semantic unavailable · Fetching refresh.

**Note:** Broader `SearchRequest` fields (dates, mime, correspondent, etc.) exist in types but are **not exposed** in this UI.

Source: `frontend/src/features/search/SearchPage.tsx`, `components/search/SearchWorkspace.tsx`, `EvidenceSearchResults.tsx`

---

## Ask workspace

### Purpose

Dedicated route that immediately opens the AI drawer. Encourages using Documents-integrated Ask; provides a deep-link target from Search (`?q=` sets **search scope snapshot**, does **not** prefill the question text).

### Layout structure

```text
┌ Centered empty state: Sparkles, “Ask Folium”,              │
│ short copy preferring Documents, [Open Ask]                │
│ + AIChatDrawer Sheet                                       │
└────────────────────────────────────────────────────────────┘
```

### Visual elements

| Element | Type | Action | Result |
|---------|------|--------|--------|
| Open Ask | Button | Click | Ensures drawer open |
| AI drawer | Sheet | See shared spec | `POST /api/ask` |

### Page states

Drawer auto-open on mount / when `q` changes; citation click hard-assigns to Documents viewer URL.

Source: `frontend/src/features/ask/AskPage.tsx`, `components/ask/AskWorkspace.tsx`

---

## AI drawer (Ask Folium)

Shared temporary surface (Sheet, right). Hosted by Documents (primary), Ask page, and entry points (viewer Ask, bulk Ask, evidence Ask).

### Purpose

Single-turn, scoped Ask Folium with citations. Search retrieves; Ask generates.

### Visual elements

| Element | Type | Action | Result |
|---------|------|--------|--------|
| Scope select | Select | Change kind | library / folder / folder_tree / documents / document / search |
| Folder select | Select | When folder scopes | Sets folder_id |
| Scope summary | Panel | — | Label + readiness estimate from preview docs |
| Question | Textarea | Type | Required to send |
| Send | Button | Click | `POST /api/ask` |
| Thinking… | Status | — | Pending |
| Answer | Text | — | Model answer |
| Insufficient evidence | Warning | — | Canonical low-evidence outcome |
| Provider/model/local | Meta | — | Transparency |
| Citations | List | Click | Open document at page |
| Confirm remote | Button | When 403 + warn policy | Resubmit with `confirm_remote: true` |
| Errors | Text | — | Scope validation or API errors |

### Scope readiness

Shows `askReady/total`, semantic count, unavailable count when `previewDocuments` provided; otherwise explanatory muted copy.

### States

Empty · Thinking · Answer · Insufficient evidence · Remote confirmation required · Error (providers/policy) · Scope validation errors · AI/chat unavailable (error copy points to Settings).

Source: `frontend/src/components/ask/AIChatDrawer.tsx`, `CitationList.tsx`, `scopeReadiness.ts`

> **Note:** `DocumentAskInput` (`POST /api/documents/:id/ask`) exists but is **not mounted** anywhere — orphaned component.

---

## Document viewer + Inspector (detail)

### DocumentViewer

| Control | Result |
|---------|--------|
| Page prev/next | Change page (`viewerPage` synced from modal) |
| Zoom ± | Local zoom |
| Open original / Print / Download | `/api/documents/:id/download` |
| Loading / error / unsupported MIME | Status UI |

### Inspector tabs

**Overview:** Retrieval readiness, processing flags (`ProcessingStatus`), AI summary, Re-embed, Suggest tags & folder, pending `InboxSuggestions`, ingestion history (recent jobs).

**Metadata:** Editable title & notes (blur-save `PATCH .../metadata`); display folder path, tags, type, correspondent, language, pages, dates. Type/correspondent editing here is largely display-only vs Inbox type control.

**OCR:** Page text via `GET .../content`; filter; Retry preflight (inbox) or Retry OCR (library).

Source: `DocumentInspector.tsx`, `ProcessingStatus.tsx`, `AISummary.tsx`, `MetadataPanel.tsx` (also used read-only in Trash)

---

## Jobs

### Purpose

Operational view of background jobs (OCR, indexing, embeddings, etc.).

### Layout

```text
┌ Jobs | Status filter | Refresh ┐
│ Table: Status | Type | Document | Created | Error | Cancel │
└────────────────────────────────┘
```

Auto-refetch ~5s.

### Visual elements

| Element | Action | Result |
|---------|--------|--------|
| Status filter | all/queued/running/completed/failed | Filters list (**cancelled omitted**) |
| Refresh | Click | Refetch |
| Cancel | Queued/running | `POST /api/jobs/:id/cancel` |
| Empty | — | Clock + empty copy |

Source: `frontend/src/features/jobs/JobsPage.tsx`, `components/jobs/JobList.tsx`

---

## Trash

### Purpose

Review soft-deleted folders and loose documents; restore or purge before retention expiry.

### Layout structure

```text
┌ Header: Trash | retention note | Restore | Delete forever | Empty ┐
├────────────┬──────────────────────┬─────────────┤
│ Folders /  │ DocumentViewer       │ Metadata    │
│ Docs list  │ (active loose doc)   │ Panel       │
└────────────┴──────────────────────┴─────────────┘
```

### Visual elements

| Element | Action | Result |
|---------|--------|--------|
| Retention note | — | Shows retention days from `useTrashCount` |
| Folder rows | Select / restore / purge | Folder restore restores nested docs |
| Loose document rows | Select / activate preview | Docs inside trashed folders hidden as “loose” |
| Days left | — | From `purge_after` |
| Restore selected | Click | Restore folders + bulk restore docs |
| Delete forever | `confirm` | Purge folders + `DELETE` docs |
| Empty trash | `confirm` | `POST /api/trash/empty` |

### States

Loading · empty · populated · destructive native confirms · preview of active loose doc.

Source: `frontend/src/features/trash/TrashPage.tsx`

---

## Settings — layout

```text
┌ Settings nav (horizontal mobile / left rail md+) ─┬─ Outlet ┐
│ Profile [pending reset badge]                     │         │
│ Artificial Intelligence (admin)                   │         │
│ System (admin)                                    │         │
│ Logs (admin)                                      │         │
│ About                                             │         │
└───────────────────────────────────────────────────┴─────────┘
```

Non-admin hitting admin routes → redirected to Profile with notice (`AdminSettingsGuard`).

Source: `frontend/src/features/settings/SettingsLayout.tsx`

---

## Settings — Profile

### Purpose

Manage own identity, password, sessions, avatar, usage; admin shortcut to Users.

### Visual elements / interactions

| Control | API | Result |
|---------|-----|--------|
| Avatar upload / remove | POST/DELETE `/api/auth/me/avatar` | Updates avatar |
| Username / display name Save | PATCH `/api/auth/me` | Profile update |
| Change password | POST `/api/auth/me/password` | Success signs out → login notice |
| Sessions list | GET `/api/auth/me/sessions` | UA, last seen, IP |
| Revoke session | DELETE session | Ends that session |
| Sign out others | POST sign-out-others | Keeps current |
| Usage | GET `/api/auth/me/usage` | Storage + AI monthly |
| User administration | Link (admin) | → `/settings/profile/users` |

Source: `frontend/src/components/settings/ProfileSettings.tsx`

---

## Settings — Users (admin)

### Purpose

Admin user lifecycle: password reset approvals, invites, account flags, quotas, set password.

### Sections

1. **Password reset requests** — Approve (copies reset link) / Reject (confirm dialog)
2. **Invite links** — Create (copies `/register?invite=`) / Revoke
3. **Accounts** — Make/remove admin, activate/deactivate, delete, set password, storage quota, AI monthly quota

Self-account protections: cannot delete/deactivate/demote/edit own quotas.

Modal: shared confirm Dialog for privileged actions; set-password dialog (≥8).

Source: `frontend/src/components/settings/UsersSettings.tsx`

---

## Settings — Artificial Intelligence (admin)

Tabs via `?tab=` (default `usage`):

### Usage

Range: today / 7d / 30d / month. KPIs: Requests, Tokens, Processing time, Estimated cost. Charts + provider/workload breakdowns. `GET /api/ai/usage`.

### Models

Assignments for Indexing, Embedding, Chat (vision in Advanced). Change opens AssignmentDialog (provider + model discovery or free text). Embedding change warning. `GET/PATCH /api/ai/assignments`.

### Providers

List providers (Ollama, OpenAI Compatible, OpenAI, OpenRouter, Anthropic, Gemini). Add/Edit dialog (name, kind, base URL, API key show/hide, chat/embedding models, embedding knobs, local checkbox). Test / Enable-Disable / Delete (`window.confirm`).

### Policy

Privacy mode: local only / private hybrid / standard. Remote allow Q&A / embeddings / vision; warn before remote; block remote. Automation: auto-enrichment, auto-tagging. Enforcement note + active embedding info. `GET/PATCH /api/ai/policy`.

### Advanced

AI profiles (Lightweight / Balanced / Quality / Custom token/chunk knobs) + Vision assignment panel. Note in UI: profiles ≠ model selection.

Source: `ArtificialIntelligencePage.tsx`, `AIProvidersSettings.tsx`, `AIPolicySettings.tsx`, `AIProfilesSettings.tsx`

---

## Settings — System (admin)

| Section | Information | API |
|---------|-------------|-----|
| Application | Version, schema, uptime, DB/storage/worker health, doc counts, jobs | `useSystemSummary` |
| Runtime | deployment_mode, service statuses, key/values | same |
| Storage `#storage` | Donut used/free, paths, category bytes | `useStorageMetrics` |
| Copy diagnostics | Clipboard | `GET /api/system/diagnostics` |

Source: `frontend/src/features/settings/SystemPage.tsx`

---

## Settings — Logs (admin)

Filters (URL): search, level, service, range (default 24h), page. Actions: Refresh, Export CSV, Clear (`confirm`), Live poll 5s. Row click → Sheet with structured fields (timestamp, level, service, module, request_id, message, context, stack).

Source: `frontend/src/features/settings/LogsPage.tsx`

---

## Settings — About

Product/version/build (`GET /api/about`), Privacy & Data Handling static copy, link to AI Policy (admin) or “managed by administrator”, optional project links.

Source: `frontend/src/features/settings/AboutPage.tsx`

---

## Not found

Authenticated unknown path: icon, “Page not found”, link to Documents. Inside AppShell.

Source: `frontend/src/features/not-found/NotFoundPage.tsx`

---

## 5. Visual element inventory (cross-cutting)

### Status systems (must not be conflated)

| System | Values (UI) | Where |
|--------|-------------|-------|
| Inbox status | preparing, ready, needs_review, failed | Inbox |
| Processing status | pending, processing, ready, failed, partial | Inspector / pipeline |
| Retrieval readiness | Preparing, Needs review, Ready to process, Indexing, Embedding %, Keyword ready, Semantic ready, Failed, Partial | Library, viewer, search |
| Job status | queued, running, completed, failed, cancelled | Jobs |
| Suggestion status | pending, accepted, rejected | Suggestion chips |

### Shared UI primitives

Button, Input, Textarea, Checkbox, Select, Tabs, Dialog, Sheet, Popover, DropdownMenu, Tooltip — under `components/ui/`.

### Document representation variants

| Variant | Surface | Fields emphasised |
|---------|---------|-------------------|
| DocumentRow | Documents list | Title, folder leaf, tags, pages·size, readiness, date |
| DocumentCard | Documents grid | Thumbnail, title, readiness |
| Recent card | Recent strip | Thumbnail, title |
| Inbox row | Inbox | Filename, filing controls, inbox status |
| Evidence hit | Search / evidence mode | Snippet, matches, readiness |
| Trash row | Trash | Title, purge countdown |

---

## 6. Interaction behaviour (API map)

| User intent | Frontend | API |
|-------------|----------|-----|
| Sign in/out | Login / AppShell | `POST /api/auth/login`, logout |
| Upload | Uploader | `POST /api/documents/upload` |
| List library / inbox / trash | `useDocuments` | `GET /api/documents` |
| Evidence search | `useSearch` | `POST /api/search` |
| Process inbox | `useProcessInboxDocuments` | `POST /api/documents/process` |
| Bulk organise | `useBulkAction` | `POST /api/documents/bulk` |
| Metadata edit | `useUpdateDocumentMetadata` | `PATCH /api/documents/:id/metadata` |
| Suggestions | accept/reject hooks | `/api/ai/suggestions/...` |
| Ask | `useAsk` | `POST /api/ask` |
| Folder CRUD | folder hooks | `/api/folders` |
| Jobs | `useJobs` / cancel | `/api/jobs` |
| Trash ops | restore/purge/empty | document/folder/trash endpoints |
| AI admin | providers/policy/assignments/usage | `/api/ai/*` |
| System/logs | system/logs hooks | `/api/system/*`, `/api/logs` |

CSRF required for state-changing calls (`lib/csrf.ts`, `client.ts`).

---

## 7. UI states (product-wide)

| State | Where handled | Notes |
|-------|---------------|-------|
| Empty | Documents, Inbox, Search, Jobs, Trash, sessions | Distinct copy per surface |
| Loading | Query `isLoading` text | Rare skeletons; mostly text |
| Refreshing | “Updating…” / “refreshing…” / live logs | Polling on Inbox/Jobs/Logs |
| Processing / Preparing | Badges + poll | Inbox & readiness |
| Success toasts/notices | Inbox result bar; auth notices; settings messages | Not a global toast system |
| Validation errors | Auth forms, Ask scope, settings forms | Inline |
| Backend errors | Often inline / button error text | **Gap:** Documents/Inbox list errors weak |
| AI unavailable | Inbox header; Ask errors; semantic disabled | Manual filing still works |
| OCR unavailable / failed | Readiness Failed + Retry | Inspector OCR tab |
| Offline | **Unverified:** no dedicated offline UI | Browser/network errors surface as API failures |
| Permission denied | Admin guard redirect; Ask remote 403 → confirm | |
| Destructive confirmation | Dialogs or `window.confirm` | Inconsistent pattern |
| No search results | Evidence empty copy | |
| Duplicate upload | Upload summary counts | `on_duplicate=skip` for tree/multi |

---

## 8. Modal / dialog / drawer inventory

| Surface | Kind | Trigger | Primary / destructive |
|---------|------|---------|------------------------|
| Document viewer | Dialog (near fullscreen) | Open doc | Close; Ask; inspect |
| AI drawer | Sheet | Ask entry points | Send Ask |
| Move to folder | Dialog | Bulk move / Inbox assign | Confirm move |
| Folder create/rename/delete | Dialog | FolderTree | Save / Trash folder |
| Inbox preview | Dialog | Row/preview | Filing controls |
| Inbox remove | Dialog | Remove | Destructive remove |
| AI provider add/edit | Dialog | Providers | Save |
| AI assignment | Dialog | Models/Advanced | Save assignment |
| Users confirm / set password | Dialog | Admin actions | Confirm / set |
| Log event | Sheet | Logs row | Close |
| Provider delete | `window.confirm` | Delete | Destructive |
| Logs clear | `window.confirm` | Clear | Destructive |
| Trash purge/empty | `window.confirm` | Header actions | Destructive |

---

## 9. Complete user journeys

---

## Journey: Import a document (upload)

### User goal

Get a file into Folium for filing and later retrieval.

### Entry point

Inbox Upload, Documents Upload, or drag-drop on those pages. (Consume watch folder is server-side; **no dedicated Consume UI**.)

### Happy path

```text
1. User chooses Upload files/folder or drops entries
2. System shows UploadStatusBar progress; POST /api/documents/upload sequentially
3. System reports created / duplicates / failed
4. If Inbox upload: document appears in Inbox as preparing → ready/needs_review
5. If Documents upload with folder: document associated with folder_id (inbox behaviour server-defined)
6. User continues to review (Inbox) or browse (Library)
```

### Decision points

```text
                    ┌─ content duplicate → counted as duplicate, skipped
Upload ─────────────┤
                    └─ success → preflight jobs (text/OCR; optional AI suggestions)
```

### Failure / recovery

- Failed upload rows in summary; dismissible
- Failed preflight → can Retry from Inbox
- **Unverified:** exact Documents-upload inbox flag without inspecting backend defaults at runtime

### Completion state

Upload summary shows created count; document visible in Inbox and/or Library depending on path.

---

## Journey: Review and Process Inbox

### User goal

File documents out of Inbox into the library with correct metadata and start final indexing.

### Entry point

`/inbox`

### Happy path

```text
1. User opens Inbox; sees queue with status tabs
2. User opens preview or edits folder/tags/type inline
3. Optional: accept AI suggestion chips (title/folder/tags/type/correspondent)
4. Document becomes processable (filing target present, not preparing/failed)
5. User clicks Process (selected or all processable)
6. System POST /api/documents/process; toast shows counts
7. Documents leave Inbox; indexing/embedding jobs run
8. User finds them under Documents; readiness moves toward Keyword/Semantic ready
```

### Decision points

```text
                    ┌─ AI suggestions available → chips shown; accept/reject
Preflight done ─────┤
                    └─ AI unavailable → manual folder/tags/type only

                    ┌─ processable → included in Process
Review ─────────────┤
                    └─ needs_review / preparing / failed → excluded until fixed/retried
```

### Failure / recovery

- Failed status → Retry preflight
- Process skipped/failed counts in toast
- Remove from queue (not the same as Trash library delete — queue removal API)

### Completion state

Toast with processed count; Inbox row gone; document appears in library folder; Jobs show indexing/embedding.

---

## Journey: Browse and organise library

### User goal

Find documents by folder/tag/view and move/tag/trash them.

### Entry point

`/documents`

### Happy path

```text
1. User selects Quick Access or folder/tag
2. System browses via GET /api/documents (empty q)
3. User selects rows (checkbox/keyboard) or drags to folder
4. Bulk Move/Tag/Trash or drop-move
5. Optional open viewer to edit title/notes
```

### Completion state

Filters reflect organisation; readiness badges show retrieval stage.

---

## Journey: Evidence search

### User goal

Find passages/documents matching a query without generating an answer.

### Entry points

Documents header search; `/search`

### Happy path

```text
1. User enters query; chooses Hybrid/Keyword/Semantic
2. Optional filters (Documents: folder/tags via explorer; Search page: folder/tag/readiness)
3. POST /api/search returns hits + matches + coverage
4. User opens hit → viewer at page; or expands evidence matches
```

### Decision points

```text
                    ┌─ semantic_available → Semantic/Hybrid as requested
Mode ───────────────┤
                    └─ unavailable → Semantic disabled; effective mode may fall back
```

### Completion state

Hits listed with snippets; user can open evidence or hand off to Ask.

---

## Journey: Ask Folium about documents

### User goal

Get a cited answer from a bounded scope.

### Entry points

Documents Ask · viewer Ask · bulk Ask · evidence Ask · `/ask` · Search “Ask about results”

### Happy path

```text
1. User opens AI drawer with an initial scope
2. User confirms/adjusts scope; types question; Send
3. POST /api/ask returns answer + citations
4. User clicks citation → Documents viewer at page
```

### Decision points

```text
Ask ── 403 remote warn ──→ Confirm remote AI and ask (confirm_remote)
    └─ success / insufficient_evidence / error
```

### Failure / recovery

- Scope validation errors (no folder/docs/search)
- Provider/policy errors → Settings guidance
- Insufficient evidence warning on answer
- Ask disabled on viewer until document ask-ready

### Completion state

Answer visible with citations; optional navigation into evidence.

---

## Journey: Configure AI providers and policy

### User goal

Enable optional AI (embeddings, chat, suggestions) under a privacy mode.

### Entry point

Settings → Artificial Intelligence (admin)

### Happy path

```text
1. Admin adds provider, Tests connection
2. Assigns Embedding / Chat (/ Indexing) models
3. Sets privacy mode + allow flags + warn/block remote
4. Enables auto-tagging / auto-enrichment if desired
5. Optionally tunes AI profile (context budgets)
6. Usage tab monitors consumption
```

### Failure / recovery

- Test failure in provider dialog
- Delete blocked if still assigned (confirm copy)
- Users see Inbox “AI filing suggestions unavailable” and Ask errors until fixed

### Completion state

`useAICapabilities` reflects chat/embeddings/auto_tagging; semantic mode enabled when embedding space active.

---

## Journey: Soft-delete and restore

### User goal

Remove documents/folders from the library reversibly, or purge.

### Entry point

Documents bulk Trash; FolderTree delete; `/trash`

### Happy path

```text
1. User trashes docs/folders
2. Items appear in Trash with retention countdown
3. User restores OR deletes forever / empties trash
```

### Completion state

Restored items back in library; purged items gone; nav trash badge updates.

---

## Journey: Password reset (admin-mediated)

```text
1. User submits Forgot password
2. Admin approves in Settings → Users; copies link
3. User opens Reset password with token; sets password
4. Redirect to Login with notice
```

---

## Journey: Troubleshoot processing

```text
1. User sees Failed readiness or Inbox failed
2. Retry preflight/OCR from Inbox or Inspector
3. Or open Jobs to cancel/inspect errors
4. Admin may check System health / Logs
```

---

## 10. Cross-page workflows

| Workflow | Pages involved |
|----------|----------------|
| Ingest → File → Retrieve | Inbox → Process → Documents → Search |
| Search → Ask → Cite → View | Search or Documents evidence → Ask drawer → Documents viewer |
| Upload in context folder | Documents (folder selected) → upload with folder_id → (server inbox/library rules) |
| Admin enables AI → user gets suggestions | Settings AI → Inbox chips / Ask |
| Trash from library → restore | Documents → Trash → Documents |
| Legacy URL → modern Documents | Legacy routes → `/documents?folder&doc` |

```text
Inbox ──Process──► Documents ──Evidence search──► Ask ──citation──► Viewer
   ▲                  │                               │
   └── Upload         └── Bulk trash ──► Trash        └── Settings AI (deps)
```

---

## 11. Reusable UX patterns

| Pattern | Appearances | Variants / consistency |
|---------|-------------|------------------------|
| AppShell nav + badges | All auth pages | Consistent; explorer suppressed on Documents/Settings |
| Page header (title + subtitle + actions) | Documents, Inbox, Search, Jobs, Trash | Similar density; Search taller |
| Upload dropdown + dropzone + status bar | Inbox, Documents | Shared components; folder_id only on Documents |
| Evidence results | Documents (q), Search page | Shared `EvidenceSearchResults` |
| Retrieval readiness badge | Rows, cards, viewer, evidence | Shared helper |
| Status badge (Inbox) | Inbox only | Separate vocabulary from readiness |
| Suggestion chips | Inbox table/preview; Inspector overview | Accept/reject shared |
| Bulk selection toolbar | Documents, Inbox | Different actions (Process vs Trash) |
| MoveToFolderDialog | Documents, Inbox | Shared |
| AI drawer | Documents, Ask | Shared |
| Settings cards / tables | Settings sections | Admin vs user split |
| Native `confirm` vs Dialog | Trash/Logs/Providers vs Users/Inbox | **Inconsistent** |
| Empty state centered copy | Many pages | Text-first, few illustrations |
| Debounced search input | Documents, Search | 300ms both |
| Polling while busy | Inbox 3s, Jobs 5s, Logs live 5s, suggestions 4s | Pattern reused |

Unused / orphaned: `DocumentToolbar.tsx`, `DocumentAskInput.tsx` (not wired).

---

## 12. UX inconsistencies and risks

| Issue | Location | Evidence | User Impact | Severity |
|-------|----------|----------|-------------|----------|
| Inbox **Ready** vs **Keyword ready** / **Semantic ready** | Inbox vs library badges | Different enums; ubiquitous language trap | Users may think Process is unnecessary or that Ready means Ask-ready | High |
| Two search UIs with different filters | Documents header vs `/search` | Search page has readiness filter; Documents uses explorer tags/folder | Unclear which surface to use; feature asymmetry | Medium |
| Ask route does not prefill question from `?q=` | `/ask` | Sets search scope only | User expects question filled from Search handoff | Medium |
| List/query error UI missing | Documents, Inbox | No `isError` rendering in pages | Silent failure / empty confusion | High |
| Destructive confirms inconsistent | Trash/Logs vs Dialogs | `window.confirm` vs `Dialog` | Uneven trust/safety UX | Medium |
| Breadcrumbs non-interactive | Documents | `Breadcrumbs` display-only | Can't climb folder hierarchy via crumbs | Low |
| Metadata edit asymmetry | Inbox type vs Inspector | Type editable in Inbox; Inspector mostly title/notes | Users hunt for where to edit type/correspondent | Medium |
| AppShell folder tree vs Documents explorer | Global vs page | Duplicate folder/tag navigation with different visibility rules | Cognitive split; folders hidden in shell on Documents | Medium |
| Orphan Ask input component | `DocumentAskInput` | Unused | Dead capability / future drift | Low |
| Jobs filter omits cancelled | Jobs | Filter enum incomplete | Harder to audit cancelled work | Low |
| No Consume UI | Product has consume mount | Ops-only / backend poll | Homelab users may not discover drop-folder ingest | Medium |
| No YouTube/extraction | Absent | Grep: no UI | N/A for current product (do not invent) | — |
| Archive flag weak UI exposure | Types/API support archive bulk | Documents bulk toolbar lacks archive | Backend capability under-exposed | Medium |
| Offline not modelled | App-wide | No offline banner | Opaque failures offline | Medium |
| Guest unknown URL → login | Router | No public 404 | Confusing deep links when logged out | Low |
| Semantic coverage warnings dense | Evidence results | Multiple mode/coverage strings | Easy to miss why results feel incomplete | Medium |

---

## 13. Stitch-ready screen specifications

Functional specs only — no colour/typography prescriptions unless functionally meaningful (e.g. destructive).

---

## Stitch Specification — Login

### Goal
Let a returning user establish a session.

### Required regions
Brand header; credential form; auxiliary links; error/notice region.

### Required components
Username field; password field; submit; forgot-password link; conditional register link; error text; optional notice.

### Required information
Product identity; validation/API errors; registration availability.

### Primary action
Sign in.

### Secondary actions
Forgot password; create account.

### Important states
Idle; validating; submitting; error; notice-after-reset; registration closed.

### Connected screens
Register; Forgot password; Documents (success).

---

## Stitch Specification — Register

### Goal
Create an owner account (open or invite).

### Required regions
Brand; form; invite banner; closed-registration message.

### Required components
Username; optional display name; password; submit; login link.

### Required information
Invite state; validation rules feedback.

### Primary action
Create account.

### Secondary actions
Back to login.

### Important states
Open registration; invite; closed; error; submitting.

### Connected screens
Login; Documents.

---

## Stitch Specification — Forgot / Reset password

### Goal
Admin-mediated password recovery.

### Required regions
Request form OR token validation + new password form.

### Required components
Username request; success confirmation; token invalid state; new/confirm password; submit.

### Required information
OOB admin-approval explanation; token validity.

### Primary action
Request reset / Set password.

### Connected screens
Login; (admin) Users approvals.

---

## Stitch Specification — App shell

### Goal
Orient the user across Folium places and account controls.

### Required regions
Collapsible sidebar; primary nav; optional library explorer; account footer; main outlet.

### Required components
Nav items with Inbox/Trash counts; folder tree; tag list; avatar; settings; logout; version.

### Required information
Current route; counts; user display name; admin flag; version.

### Primary action
Navigate to a place.

### Secondary actions
Collapse sidebar; open settings; log out; jump to folder/tag.

### Important states
Expanded/collapsed; explorer visible/hidden; badge overflow 99+.

### Connected screens
All authenticated places.

---

## Stitch Specification — Documents workspace

### Goal
Browse, filter, evidence-search, organise, upload, open, and Ask across the library.

### Required regions
Header (title, search, mode, Ask, upload); upload status; explorer (Quick Access, folders, tags); view tabs; optional recent strip; results toolbar/bulk toolbar; results (list/grid/evidence); overlays (viewer, Ask, move).

### Required components
Search field; mode tabs; readiness badges; filter chips; sort; layout toggle; selection; document rows/cards; pagination; empty/loading states.

### Required information
Titles; folder; tags; size/pages; added date; retrieval readiness; evidence snippets/match totals; semantic availability/coverage.

### Primary action
Find and open a document (browse or evidence search).

### Secondary actions
Upload; Ask Folium; bulk move/tag/trash; folder CRUD; tag filter.

### Important states
Browse empty/populated/loading; evidence active/empty; semantic unavailable; selection; upload progress; folder scoped; unprocessed/recent views.

### Connected screens
Inbox; viewer modal; AI drawer; Search (conceptual parity); Trash (via trash action).

---

## Stitch Specification — Document viewer + Inspector

### Goal
Read the original and manage readiness/metadata/OCR for one document.

### Required regions
Modal chrome; viewer canvas; inspector tabs; header actions.

### Required components
Page/zoom/download controls; readiness badge; Ask (enabled when ask-ready); Overview/Metadata/OCR; processing flags; AI summary; suggestions; job history; retry/reprocess actions.

### Required information
Title; filename; size; pages; folder; tags; type; correspondent; dates; OCR text; readiness description; errors.

### Primary action
Inspect evidence (page through document).

### Secondary actions
Edit title/notes; Ask; retry OCR/preflight; re-embed; request suggestions; prev/next document.

### Important states
Loading preview; unsupported type; ask unavailable; processing; failed; suggestion pending.

### Connected screens
Documents underneath; AI drawer; Jobs (indirect).

---

## Stitch Specification — Inbox

### Goal
Review filing metadata and Process documents into the library.

### Required regions
Header + AI availability; upload status; status tabs / bulk bar; search/sort; table; result toast; preview dialog.

### Required components
Status badges; folder/tags/type controls; suggestion chips; process button; remove/retry; preview viewer.

### Required information
Inbox status; filename; pending folder path; tags; type; suggestion fields; process counts; errors.

### Primary action
Process processable documents.

### Secondary actions
Upload; assign folder/tags; accept/reject suggestions; remove; retry; preview.

### Important states
Empty clear inbox; preparing (live); needs review; ready; failed; AI unavailable; selection; process result.

### Connected screens
Documents (after Process); preview dialog; Move dialog.

---

## Stitch Specification — Search workspace

### Goal
Run filtered evidence search and open or Ask over results.

### Required regions
Query + filters + mode; results list.

### Required components
Query; folder/tag/readiness filters; mode tabs; hit cards; match expansion; Ask handoff.

### Required information
Totals; snippets; readiness; coverage warnings; effective mode.

### Primary action
Search evidence.

### Secondary actions
Open document; Ask about results.

### Important states
No query; loading; empty; semantic unavailable.

### Connected screens
Documents viewer; Ask.

---

## Stitch Specification — Ask Folium (drawer)

### Goal
Answer one question from a bounded scope with citations.

### Required regions
Scope controls; readiness summary; question composer; answer; citations; remote confirm.

### Required components
Scope select; folder select; textarea; send; citation list; warnings.

### Required information
Scope label; ask-ready counts; answer; insufficient_evidence; provider/model/local; citation title/page/quote.

### Primary action
Send question.

### Secondary actions
Change scope; confirm remote; open citation.

### Important states
Empty; thinking; answer; insufficient evidence; remote confirm; errors; missing scope data.

### Connected screens
Documents viewer (citations); Settings AI (recovery).

---

## Stitch Specification — Jobs

### Goal
Monitor and cancel background processing jobs.

### Required regions
Filter bar; job table.

### Required components
Status filter; refresh; cancel; empty state.

### Required information
Status; type; document id; created; error.

### Primary action
Inspect job health.

### Secondary actions
Cancel; refresh.

### Important states
Empty; running; failed; polling.

### Connected screens
Documents/Inbox (indirect via document ids).

---

## Stitch Specification — Trash

### Goal
Restore or permanently delete soft-deleted items before retention elapses.

### Required regions
Header actions; folder/doc list; preview; metadata.

### Required components
Selection; restore; delete forever; empty trash; retention indicator; viewer.

### Required information
Titles; purge countdown; retention days.

### Primary action
Restore or purge selected.

### Secondary actions
Empty trash; preview loose doc.

### Important states
Empty; selected; destructive confirm.

### Connected screens
Documents (after restore).

---

## Stitch Specification — Settings Profile

### Goal
Manage personal account, sessions, avatar, and usage.

### Required regions
Profile form; password; sessions; usage; admin link.

### Required components
Avatar controls; fields; session rows; revoke; usage meters.

### Required information
Identity; session metadata; storage/AI usage vs quotas.

### Primary action
Save profile / manage sessions.

### Secondary actions
Change password; open Users (admin).

### Important states
Loading sessions; success/error messages; signed-out-after-password-change.

### Connected screens
Users; Login.

---

## Stitch Specification — Settings Users (admin)

### Goal
Administer invites, password resets, accounts, and quotas.

### Required regions
Reset requests; invites; accounts table; confirm dialogs.

### Required components
Approve/reject; create/revoke invite; admin/active toggles; quotas; set password.

### Required information
User flags; quota values; pending reset count; invite tokens (copy links).

### Primary action
Resolve access (approve reset / invite / account change).

### Important states
Empty lists; confirm destructive; self-account restrictions.

### Connected screens
Profile; Reset password (external link).

---

## Stitch Specification — Settings Artificial Intelligence

### Goal
Configure optional AI usage, models, providers, privacy policy, and profiles.

### Required regions
Tabbed workspace: usage; models; providers; policy; advanced.

### Required components
KPI/charts; assignment dialog; provider CRUD/test; privacy toggles; profile selectors; vision assignment.

### Required information
Usage metrics; provider health; privacy mode; enforcement note; active embedding identity; automation flags.

### Primary action
Make AI capabilities correctly available under chosen privacy mode.

### Secondary actions
Test provider; view usage; tune profiles.

### Important states
No providers; test fail; remote warn/block; embedding change warning.

### Connected screens
Inbox suggestions; Ask; Search semantic mode.

---

## Stitch Specification — Settings System / Logs / About

### Goal
Operate and understand the deployment.

### Required regions
System summary + storage; logs filters/table/detail sheet; about/privacy copy.

### Required components
Health indicators; storage donut; diagnostics copy; log filters; export/clear/live; about metadata.

### Required information
Version; service health; storage paths/bytes; log events; privacy narrative.

### Primary action
Diagnose system health / inspect logs / read about.

### Important states
Degraded storage; empty logs; live polling; clear confirm.

### Connected screens
AI Policy (from About for admins).

---

## 14. Coverage checklist

- [x] Every frontend route inspected (`App.tsx` auth + guest + settings redirects + legacy)
- [x] Every major page documented
- [x] Every modal/dialog/sheet documented (including `window.confirm` destructives)
- [x] Every major interactive control documented (page specs + API map)
- [x] Empty states documented
- [x] Loading states documented
- [x] Error states documented (including known weak list-error UI)
- [x] AI-unavailable behaviour documented (Inbox, semantic mode, Ask, capabilities)
- [x] Destructive actions documented (trash, purge, remove queue, delete provider, clear logs, user delete)
- [x] Primary user journeys mapped
- [x] Cross-page navigation mapped
- [x] Stitch specifications produced

### Explicit non-coverage / unverified

> **Unverified:** Exact server default for uploads without `folder_id` (Inbox assumption from frontend omission).  
> **Unverified:** Runtime offline behaviour beyond generic API failures.  
> **Confirmed gap:** AuthGuard saves `from` on redirect to login, but `LoginPage` always navigates to `/documents` and ignores it.  
> **Absent by design (do not invent):** YouTube extraction, Shared with me, Activity, Starred, multi-turn Ask.

---

## Appendix A — Source index

| Area | Paths |
|------|-------|
| Routes | `frontend/src/App.tsx` |
| Shell | `frontend/src/components/layout/AppShell.tsx` |
| Documents | `frontend/src/features/documents/*` |
| Inbox | `frontend/src/features/inbox/*` |
| Search | `frontend/src/features/search/*`, `components/search/*` |
| Ask | `frontend/src/features/ask/*`, `components/ask/*` |
| Jobs | `frontend/src/features/jobs/*`, `components/jobs/*` |
| Trash | `frontend/src/features/trash/*` |
| Settings | `frontend/src/features/settings/*`, `components/settings/*` |
| Auth | `frontend/src/features/auth/*` |
| API | `frontend/src/lib/api/{hooks,types,client,upload}.ts` |
| Language | `ubiquitous-language.md` |

---

*End of audit. This document describes the existing Folium product UX as implemented; it does not prescribe a visual redesign.*
