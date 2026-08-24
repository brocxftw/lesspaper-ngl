# Design system

lesspaper-ngl does **not** ship a formal design-token package or Storybook. Visual language is encoded in CSS + primitives.

## CSS

- Tailwind v4 via `@tailwindcss/vite`
- Tokens in `frontend/src/index.css` `@theme`: sidebar, surface, text, accent (teal), danger, warning, radii, Inter/system fonts
- Base font size **13px**
- Utility `scrollbar-thin`

There is no dark-mode class strategy beyond the dark **sidebar** colors; the main canvas is light.

## Components

`frontend/src/components/ui/*`: Button, Input, Textarea, Checkbox, Dialog, Sheet, Select, DropdownMenu, Popover, Tabs, Tooltip. Built on **Radix** primitives + `cn()` (`clsx` + `tailwind-merge`). Lucide icons.

This resembles shadcn/ui **style** but there is **no** `components.json` CLI config.

## Patterns

- Dialogs for destructive confirmations and moves
- Sheet/drawer for Ask (workspace) and some inspectors
- 13px sidebar labels; accent for primary actions

Inbox review cards use some hard-coded hex colors (`#14212B`) alongside tokens (**Partial** consistency).
