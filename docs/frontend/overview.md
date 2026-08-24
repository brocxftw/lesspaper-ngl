# Frontend overview

The UI is a **React 19** SPA built with **Vite 7**, routed with **React Router 7**. Server state uses **TanStack Query**. Styling is **Tailwind CSS 4** with a small set of theme tokens in `index.css`. Domain screens live under `frontend/src/features/*` and `frontend/src/components/*`.

The SPA never talks to PostgreSQL or the worker. It calls the FastAPI HTTP API (same origin in Compose; Vite proxy in development).

---

## Routing

See [app-shell.md](app-shell.md). Authenticated shell wraps Inbox, Documents, Search, Ask, Jobs, Trash, Settings. Guest routes are login/register/password reset.

---

## Application state

- **Server state:** React Query hooks in `lib/api/hooks.ts` (documents, search, jobs, AI, session, …). Default `staleTime` 30s, `retry: 1`.
- **URL state:** Documents library view/folder/query live in query parameters (`useDocumentsLibraryState`).
- **Local React state:** viewer open, selection, drawer open, Inbox review session.
- **localStorage:** sidebar, layout mode, recents collapsed.

There is no Redux/Zustand store.

---

## API interaction

`lib/api/client.ts`: `fetch` + JSON/FormData, `credentials: "include"`, CSRF header on mutations. Types in `lib/api/types.ts` mirror API schemas (manually maintained).

---

## Component architecture

```text
App
 └─ Route → Page (features/*)
      └─ AppShell (most authenticated pages)
           └─ Workspace / domain components
                └─ ui/* primitives (Button, Dialog, Sheet, …)
```

Documents is the densest workspace (explorer + results + modal viewer + inspector + AI drawer). Inbox is a separate review queue. Search and Ask routes exist for parity with Documents-integrated search/Ask.

---

## Design system

See [design-system.md](design-system.md). Primitives follow Radix + Tailwind patterns; there is no published lesspaper-ngl design-token package.
