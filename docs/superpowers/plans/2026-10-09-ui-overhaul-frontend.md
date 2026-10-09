# UI Overhaul — Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `static/index.html` with a React + TypeScript app (sidebar navigation, Dashboard, Library with filters/sort/selection/batch actions, trash view, model detail) that consumes the API built in the backend plan, keeping the current "blueprint" visual identity.

**Architecture:** A Vite-built React/TS SPA lives in `frontend/`, built to `frontend/dist/`, served by FastAPI (`webapp.py` serves `dist/index.html` at `/` and mounts `dist/assets` at `/assets`). No client-side router — the app has exactly two views (Dashboard, Library) switched by local component state from a persistent sidebar, so `react-router-dom` is not needed. No global state library — `fetch`-backed hooks plus prop drilling from `App.tsx` are enough for two views and a handful of shared lists.

**Tech Stack:** React 18, TypeScript, Vite, Tailwind CSS, Three.js (ported from the existing vanilla STL viewer). No new test tooling (manual browser verification per task, per the approved design — see "Hors périmètre" in the spec).

**Spec:** `docs/superpowers/specs/2026-10-09-ui-overhaul-design.md`
**Depends on:** `docs/superpowers/plans/2026-10-09-ui-overhaul-backend.md` (must be implemented first — every endpoint/response shape used below is defined there)

This plan implements the **Frontend** section of the spec, using the exact
layouts approved with the user during brainstorming (sidebar navigation,
dashboard with recent/lists sections, library with grid/list modes and a
floating batch bar, lists shown as cyan pills distinct from search-only
tags).

## Global Constraints

- Visual identity is preserved: blueprint grid background, `#0F2A44`/`#16385A`/`#1C4468` blues, `#6FC7DA` cyan, `#F2C14E` yellow, `#7FBF8F` green, `#E2725B` red, Oswald/JetBrains Mono/Work Sans fonts (spec: "Identité visuelle").
- Auto-generated tags are never shown on cards/rows — only lists are (cyan pills). Tags stay searchable but visible only in the detail overlay (user feedback during brainstorming).
- No `react-router-dom`, no Redux/Zustand/etc. — two views, switched by local state, fetch-backed hooks. Justify any added dependency beyond React/Vite/Tailwind/Three.js before adding it (user's global convention: no unjustified dependencies).
- No automated frontend test suite for this plan — each task ends with explicit manual browser verification instead of a test run (approved during brainstorming).
- Batch action buttons are visually uniform (same height/padding, only hover color differs) — a user-reported defect in an earlier iteration of this same UI.

## Review Focus

- Selecting models, then changing a filter or the search text — the selection must either survive for still-visible rows or be cleared, but never reference ids that are no longer in view and silently no-op when "batch delete" is pressed.
- Opening the detail overlay for a model, toggling a list chip, closing without clicking "Sauvegarder" — the list membership must NOT be persisted (only the explicit save action calls the API), matching the existing edit-zone pattern where only "Modifier" reveals fields and a distinct "Sauvegarder" commits them.
- A model with `thumbnail_path: null` (STL analysis failed or f3d unavailable) — grid, list, and detail views must all fall back to the dimension-diagram SVG instead of a broken image icon, exactly like the current `static/index.html` does.
- The trash view and the normal library view share the same grid/table components — an action available only in trash ("Restaurer") must not appear in the normal view and vice versa ("Mettre à la corbeille" must not appear in the trash view).
- Creating a list from inside the batch "add to list" picker (not just from the sidebar) — the new list must immediately be usable in that same picker without requiring a page reload.

---

## File Structure

```
frontend/
  index.html
  package.json, tsconfig.json, vite.config.ts
  tailwind.config.js, postcss.config.js
  src/
    main.tsx
    App.tsx
    api.ts            — fetch wrappers for every backend endpoint
    types.ts           — Model, ListSummary, Stats, BatchPayload
    styles/index.css   — Tailwind directives + blueprint theme (cards, pills, sidebar, batch bar, overlay)
    lib/dimSvg.ts       — ported dimension-diagram SVG helper
    hooks/useLists.ts
    hooks/useModels.ts
    hooks/useStats.ts
    components/Sidebar.tsx
    components/StatBar.tsx
    components/ModelCard.tsx
    components/ModelRow.tsx
    components/FilterBar.tsx
    components/BatchActionBar.tsx
    components/ListPicker.tsx
    components/Viewer3D.tsx
    components/ModelDetailOverlay.tsx
    pages/Dashboard.tsx
    pages/Library.tsx
```

- Modify: `webapp.py` (serve `frontend/dist`)
- Delete (Task 8, once the React app fully replaces it): `static/index.html`

---

### Task 1: Scaffold the Vite/React/TS/Tailwind project and wire it to FastAPI

**Files:**
- Create: `frontend/package.json`, `frontend/tsconfig.json`, `frontend/tsconfig.node.json`, `frontend/vite.config.ts`, `frontend/tailwind.config.js`, `frontend/postcss.config.js`, `frontend/index.html`, `frontend/src/main.tsx`, `frontend/src/App.tsx`, `frontend/src/styles/index.css`
- Modify: `webapp.py` (serve `frontend/dist`)
- Modify: `.gitignore` (add `frontend/node_modules`, `frontend/dist`)

**Interfaces:**
- Consumes: nothing.
- Produces: a working `npm run dev` (Vite dev server) and `npm run build` (outputs `frontend/dist/`) pipeline; `webapp.py` serves `frontend/dist/index.html` at `/` when it exists, falling back to the current `static/index.html` otherwise (so the app keeps working mid-migration); the global Tailwind theme classes used by every later task (`.bp-card`, `.bp-pill`, `.bp-chip`, `.bp-sidebar`, `.bp-batchbar`, etc. — all defined in Task 1's `index.css`, consumed by Tasks 3–7).

- [ ] **Step 1: Scaffold the Vite project**

Run:
```bash
cd /home/romain/Documents/Code/3d/library
npm create vite@6.3.1 frontend -- --template react-ts
```

Expected: a `frontend/` directory with the standard Vite React+TS template
(`package.json`, `tsconfig.json`, `vite.config.ts`, `src/main.tsx`,
`src/App.tsx`, `index.html`).

- [ ] **Step 2: Install dependencies (Tailwind + Three.js)**

Run:
```bash
cd /home/romain/Documents/Code/3d/library/frontend
npm install
npm install three@0.160.0
npm install -D @types/three@0.160.0 tailwindcss@3.4.14 postcss@8.4.47 autoprefixer@10.4.20
npx tailwindcss init -p
```

Expected: `frontend/package.json` lists `three` as a dependency and
`tailwindcss`/`postcss`/`autoprefixer` as devDependencies; `tailwind.config.js`
and `postcss.config.js` now exist.

- [ ] **Step 3: Configure Tailwind content paths and theme colors**

Replace `frontend/tailwind.config.js`:

```js
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        "bp-deep": "#0F2A44",
        "bp-panel": "#16385A",
        "bp-panel2": "#1C4468",
        "bp-ink": "#E9EFF3",
        "bp-ink-dim": "#90A9BE",
        "bp-cyan": "#6FC7DA",
        "bp-yellow": "#F2C14E",
        "bp-green": "#7FBF8F",
        "bp-red": "#E2725B",
      },
      fontFamily: {
        display: ["Oswald", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
        sans: ["Work Sans", "sans-serif"],
      },
    },
  },
  plugins: [],
};
```

- [ ] **Step 4: Write the global stylesheet (blueprint theme + shared component classes)**

Create `frontend/src/styles/index.css`:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  body {
    margin: 0;
    font-family: "Work Sans", sans-serif;
    color: #E9EFF3;
    background:
      linear-gradient(rgba(255, 255, 255, 0.07) 1px, transparent 1px) 0 0/32px 32px,
      linear-gradient(90deg, rgba(255, 255, 255, 0.07) 1px, transparent 1px) 0 0/32px 32px,
      #0F2A44;
    min-height: 100vh;
  }
}

@layer components {
  .bp-nav-top {
    @apply flex items-center gap-2 px-2.5 py-2 mb-0.5 text-sm rounded cursor-pointer text-bp-ink;
  }
  .bp-nav-top.active {
    @apply bg-bp-panel text-bp-cyan;
  }
  .bp-nav-item {
    @apply flex justify-between items-center px-2.5 py-2 mb-0.5 text-sm rounded cursor-pointer;
  }
  .bp-nav-item:hover {
    @apply bg-bp-panel;
  }
  .bp-nav-item.active {
    @apply bg-bp-panel text-bp-cyan border-l-2 border-bp-cyan;
  }
  .bp-nav-count {
    @apply font-mono text-xs text-bp-ink-dim;
  }

  .bp-card {
    @apply bg-bp-panel border border-white/10 rounded-sm p-3.5 relative;
  }
  .bp-card.selected {
    @apply border-bp-yellow ring-1 ring-bp-yellow;
  }
  .bp-checkbox {
    @apply absolute top-2.5 left-2.5 w-[18px] h-[18px] border border-bp-ink-dim rounded-sm bg-bp-deep flex items-center justify-center text-[11px] cursor-pointer;
  }
  .bp-card.selected .bp-checkbox {
    @apply bg-bp-yellow text-bp-deep border-bp-yellow;
  }
  .bp-printed-badge {
    @apply absolute top-2.5 right-2.5 font-mono text-[9px] text-bp-green border border-bp-green px-1.5 py-0.5 rounded-sm;
  }
  .bp-thumb {
    @apply h-[100px] bg-bp-deep border border-white/5 my-4 flex items-center justify-center text-[10px] text-bp-ink-dim font-mono overflow-hidden;
  }
  .bp-thumb img {
    @apply w-full h-full object-contain;
  }
  .bp-name {
    @apply font-display text-sm uppercase tracking-wide mb-2;
  }
  .bp-pill {
    @apply font-mono text-[9px] text-bp-cyan border border-bp-cyan bg-bp-cyan/10 px-1.5 py-0.5 rounded-full;
  }
  .bp-meta {
    @apply font-mono text-[10px] text-bp-ink-dim border-t border-dashed border-white/10 pt-2 flex justify-between;
  }

  .bp-chip {
    @apply bg-bp-panel border border-white/10 rounded-full px-3 py-1.5 font-mono text-[11px] cursor-pointer;
  }
  .bp-chip.active {
    @apply border-bp-cyan text-bp-cyan bg-bp-cyan/10;
  }

  .bp-batchbar {
    @apply fixed bottom-5 left-1/2 -translate-x-1/2 bg-bp-panel2 border border-bp-cyan rounded px-4 py-2.5 flex items-center gap-2.5 font-mono text-xs shadow-2xl z-20;
  }
  .bp-batchbar button {
    @apply bg-transparent border border-white/10 text-bp-ink h-8 px-3.5 rounded-sm cursor-pointer font-mono text-[11px] whitespace-nowrap flex items-center gap-1.5;
  }
  .bp-batchbar button:hover {
    @apply border-bp-cyan text-bp-cyan;
  }
  .bp-batchbar button.danger:hover {
    @apply border-bp-red text-bp-red;
  }

  .bp-detail-overlay {
    @apply fixed inset-0 bg-black/70 flex items-center justify-center p-6 z-30;
  }
  .bp-detail {
    @apply bg-bp-panel2 border border-white/10 rounded-sm max-w-[460px] w-full p-6;
  }
  .bp-btn {
    @apply bg-transparent border border-white/10 text-bp-ink font-mono uppercase text-[11px] px-3.5 py-2 rounded-sm cursor-pointer;
  }
  .bp-btn:hover {
    @apply border-bp-cyan text-bp-cyan;
  }
  .bp-btn.primary {
    @apply border-bp-yellow text-bp-yellow;
  }
}
```

- [ ] **Step 5: Wire Vite's PostCSS pipeline and import the stylesheet**

Replace `frontend/postcss.config.js`:

```js
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};
```

Replace `frontend/src/main.tsx`:

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./styles/index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
```

Replace `frontend/src/App.tsx` with a temporary placeholder (fleshed out in
Task 3):

```tsx
export default function App() {
  return <div className="p-8 font-display text-2xl uppercase">3D Library — build OK</div>;
}
```

Replace `frontend/index.html`:

```html
<!doctype html>
<html lang="fr">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>3D Library</title>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link
      href="https://fonts.googleapis.com/css2?family=Oswald:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&family=Work+Sans:wght@400;500&display=swap"
      rel="stylesheet"
    />
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 6: Verify the dev server renders the placeholder**

Run: `cd frontend && npm run dev` then open `http://localhost:5173` in a browser.
Expected: page shows "3D Library — build OK" in the Oswald font, dark blue
background with the grid pattern visible. Stop the dev server (`Ctrl+C`)
once confirmed.

- [ ] **Step 7: Build and wire FastAPI to serve the build output**

Run: `cd frontend && npm run build`
Expected: `frontend/dist/index.html` and `frontend/dist/assets/*.{js,css}` exist.

Modify `webapp.py`: replace the `index()` route and the static mount at the
bottom of the file (`webapp.py:321-328`) with:

```python
FRONTEND_DIST = Path(__file__).parent / "frontend" / "dist"


@app.get("/")
def index():
    frontend_index = FRONTEND_DIST / "index.html"
    if frontend_index.exists():
        return FileResponse(frontend_index)
    return FileResponse(Path(__file__).parent / "static" / "index.html")


if (FRONTEND_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="frontend-assets")

static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")
```

- [ ] **Step 8: Verify FastAPI serves the built React app**

Run:
```bash
cd /home/romain/Documents/Code/3d/library
LIBRARY_DB_PATH=/tmp/ui-plan-check/library.db python3 -m webapp --port 8010 &
sleep 1
curl -s http://127.0.0.1:8010/ | grep -o '<title>.*</title>'
kill %1
```
Expected: `<title>3D Library</title>` — confirms FastAPI is serving the Vite
build, not the old `static/index.html`. (The `LIBRARY_DB_PATH` doesn't need
to exist for this check — only `/` is being hit, not an `/api/*` route.)

- [ ] **Step 9: Ignore build artifacts and commit**

Append to `.gitignore`:
```
frontend/node_modules
frontend/dist
```

```bash
git add frontend/package.json frontend/package-lock.json frontend/tsconfig.json \
  frontend/tsconfig.node.json frontend/vite.config.ts frontend/tailwind.config.js \
  frontend/postcss.config.js frontend/index.html frontend/src/main.tsx frontend/src/App.tsx \
  frontend/src/styles/index.css webapp.py .gitignore
git commit -m "feat(frontend): scaffold React/TS/Vite/Tailwind app served by FastAPI"
```

---

### Task 2: API client, types, and ported dimension-SVG helper

**Files:**
- Create: `frontend/src/types.ts`, `frontend/src/api.ts`, `frontend/src/lib/dimSvg.ts`

**Interfaces:**
- Consumes: the backend plan's endpoints exactly as documented there (`GET/POST/PUT/DELETE /api/models*`, `/api/lists*`, `/api/trash`, `/api/stats`).
- Produces: TypeScript types `Model`, `ListSummary`, `Stats`, `BatchPayload`, `ModelUpdatePayload` (consumed by every component task below); functions in `api.ts` — `getModels(params)`, `getModel(id)`, `updateModel(id, patch)`, `getLists()`, `createList(name)`, `renameList(id, name)`, `deleteList(id)`, `setModelLists(id, listIds)`, `trashModel(id)`, `restoreModel(id)`, `deleteModelPermanently(id)`, `getTrash()`, `batchAction(payload)`, `getStats()`; `dimSvg(sx, sy, sz)` returning the same SVG markup string as the current vanilla implementation.

- [ ] **Step 1: Write the types**

Create `frontend/src/types.ts`:

```ts
export interface ListRef {
  id: number;
  name: string;
}

export interface ListSummary extends ListRef {
  model_count: number;
}

export interface Model {
  id: number;
  name: string;
  original_filename: string | null;
  path: string;
  source_archive: string | null;
  category: string | null;
  tags: string | null;
  size_x: number | null;
  size_y: number | null;
  size_z: number | null;
  volume: number | null;
  is_watertight: 0 | 1 | null;
  material: string | null;
  estimated_weight_g: number | null;
  estimated_print_time_h: number | null;
  thumbnail_path: string | null;
  added_at: string;
  print_count: number;
  deleted_at: string | null;
  printed: 0 | 1;
  lists: ListRef[];
  purge_at?: string; // uniquement sur /api/trash
}

export interface Stats {
  total_models: number;
  total_weight_g: number;
  total_print_time_h: number;
  trash_count: number;
  recent: Model[];
}

export type SortKey =
  | "added_desc"
  | "added_asc"
  | "name_asc"
  | "name_desc"
  | "weight_desc"
  | "weight_asc"
  | "volume_desc"
  | "volume_asc";

export interface ModelListParams {
  q?: string;
  lists?: number[];
  printed?: boolean;
  sort?: SortKey;
}

export type BatchActionKind =
  | "trash"
  | "restore"
  | "delete"
  | "add_list"
  | "remove_list"
  | "set_printed";

export interface BatchPayload {
  ids: number[];
  action: BatchActionKind;
  list_id?: number;
  printed?: boolean;
}

export interface ModelUpdatePayload {
  name?: string;
  category?: string;
  material?: string;
  tags?: string;
  source_archive?: string;
  printed?: boolean;
}
```

- [ ] **Step 2: Write the API client**

Create `frontend/src/api.ts`:

```ts
import type {
  BatchPayload,
  ListSummary,
  Model,
  ModelListParams,
  ModelUpdatePayload,
  Stats,
} from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: init?.body ? { "Content-Type": "application/json" } : undefined,
    ...init,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Erreur ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export function getModels(params: ModelListParams = {}): Promise<Model[]> {
  const qs = new URLSearchParams();
  if (params.q) qs.set("q", params.q);
  if (params.lists?.length) qs.set("lists", params.lists.join(","));
  if (params.printed !== undefined) qs.set("printed", String(params.printed));
  if (params.sort) qs.set("sort", params.sort);
  const suffix = qs.toString() ? `?${qs}` : "";
  return request<Model[]>(`/api/models${suffix}`);
}

export function getModel(id: number): Promise<Model> {
  return request<Model>(`/api/models/${id}`);
}

export function updateModel(id: number, patch: ModelUpdatePayload): Promise<unknown> {
  return request(`/api/models/${id}`, { method: "PUT", body: JSON.stringify(patch) });
}

export function getLists(): Promise<ListSummary[]> {
  return request<ListSummary[]>("/api/lists");
}

export function createList(name: string): Promise<ListSummary> {
  return request<ListSummary>("/api/lists", { method: "POST", body: JSON.stringify({ name }) });
}

export function renameList(id: number, name: string): Promise<unknown> {
  return request(`/api/lists/${id}`, { method: "PUT", body: JSON.stringify({ name }) });
}

export function deleteList(id: number): Promise<unknown> {
  return request(`/api/lists/${id}`, { method: "DELETE" });
}

export function setModelLists(id: number, listIds: number[]): Promise<unknown> {
  return request(`/api/models/${id}/lists`, {
    method: "PUT",
    body: JSON.stringify({ list_ids: listIds }),
  });
}

export function trashModel(id: number): Promise<unknown> {
  return request(`/api/models/${id}/trash`, { method: "POST" });
}

export function restoreModel(id: number): Promise<unknown> {
  return request(`/api/models/${id}/restore`, { method: "POST" });
}

export function deleteModelPermanently(id: number): Promise<unknown> {
  return request(`/api/models/${id}`, { method: "DELETE" });
}

export function getTrash(): Promise<Model[]> {
  return request<Model[]>("/api/trash");
}

export function batchAction(payload: BatchPayload): Promise<{ processed: number[]; skipped: number[] }> {
  return request("/api/models/batch", { method: "POST", body: JSON.stringify(payload) });
}

export function getStats(): Promise<Stats> {
  return request<Stats>("/api/stats");
}

export function openFolder(id: number): Promise<{ folder: string }> {
  return request(`/api/models/${id}/open-folder`, { method: "POST" });
}

export function openOrcaSlicer(id: number): Promise<unknown> {
  return request(`/api/models/${id}/open-orcaslicer`, { method: "POST" });
}
```

- [ ] **Step 3: Port the dimension-diagram SVG helper**

Create `frontend/src/lib/dimSvg.ts` (direct port of `static/index.html`'s
`dimSVG`, used as the thumbnail fallback):

```ts
export function dimSvg(sx: number | null, sy: number | null, sz: number | null): string {
  if (sx == null) {
    return `<svg viewBox="0 0 200 70"><text x="100" y="38" text-anchor="middle" fill="#90A9BE">dimensions non analysées</text></svg>`;
  }
  return `
    <svg viewBox="0 0 200 70">
      <rect x="40" y="15" width="90" height="40" stroke="#E9EFF3" stroke-width="1.4" fill="none"/>
      <line x1="150" y1="15" x2="150" y2="55" stroke="#90A9BE" stroke-width="1"/>
      <line x1="40" y1="60" x2="130" y2="60" stroke="#90A9BE" stroke-width="1"/>
      <text x="85" y="12" font-family="monospace" font-size="9" fill="#6FC7DA" text-anchor="middle">${sx} mm</text>
      <text x="160" y="38" font-family="monospace" font-size="9" fill="#6FC7DA">${sz} mm</text>
      <text x="85" y="70" font-family="monospace" font-size="9" fill="#6FC7DA" text-anchor="middle">${sy} mm</text>
    </svg>`;
}
```

- [ ] **Step 4: Verify with a temporary render**

Temporarily replace the body of `App.tsx`'s returned JSX with
`<div dangerouslySetInnerHTML={{ __html: dimSvg(85, 40, 22) }} />` and
`import { dimSvg } from "./lib/dimSvg";`, run `npm run dev`, confirm a
dimension diagram renders with "85 mm" / "40 mm" / "22 mm" labels. Then
revert `App.tsx` back to the Task 1 placeholder — this was just a smoke test,
not the final `App.tsx` (that's Task 3).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types.ts frontend/src/api.ts frontend/src/lib/dimSvg.ts
git commit -m "feat(frontend): add typed API client and dimension-SVG helper"
```

---

### Task 3: App shell, Sidebar, and Dashboard page

**Files:**
- Create: `frontend/src/hooks/useLists.ts`, `frontend/src/hooks/useStats.ts`, `frontend/src/components/Sidebar.tsx`, `frontend/src/components/StatBar.tsx`, `frontend/src/pages/Dashboard.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `getLists`, `getStats` (Task 2).
- Produces: `useLists()` returning `{ lists, refresh }` (consumed by Sidebar, Library's filter bar, and the list picker in later tasks); `App`'s view-switch state (`view: "dashboard" | "library"`, `libraryListFilter: number | null`) passed down to `Sidebar` and `Dashboard`/`Library` — later tasks (4+) read this exact shape to know which props `Library` receives.

- [ ] **Step 1: Write the `useLists` and `useStats` hooks**

Create `frontend/src/hooks/useLists.ts`:

```ts
import { useCallback, useEffect, useState } from "react";
import { getLists } from "../api";
import type { ListSummary } from "../types";

export function useLists() {
  const [lists, setLists] = useState<ListSummary[]>([]);

  const refresh = useCallback(() => {
    getLists().then(setLists).catch(() => setLists([]));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { lists, refresh };
}
```

Create `frontend/src/hooks/useStats.ts`:

```ts
import { useCallback, useEffect, useState } from "react";
import { getStats } from "../api";
import type { Stats } from "../types";

export function useStats() {
  const [stats, setStats] = useState<Stats | null>(null);

  const refresh = useCallback(() => {
    getStats().then(setStats).catch(() => setStats(null));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { stats, refresh };
}
```

- [ ] **Step 2: Write the Sidebar**

Create `frontend/src/components/Sidebar.tsx`:

```tsx
import type { ListSummary } from "../types";

interface SidebarProps {
  view: "dashboard" | "library";
  trashCount: number;
  lists: ListSummary[];
  activeListId: number | null;
  showingTrash: boolean;
  onSelectDashboard: () => void;
  onSelectLibrary: (listId: number | null) => void;
  onSelectTrash: () => void;
}

export default function Sidebar({
  view,
  trashCount,
  lists,
  activeListId,
  showingTrash,
  onSelectDashboard,
  onSelectLibrary,
  onSelectTrash,
}: SidebarProps) {
  return (
    <div className="w-[220px] border-r border-white/10 p-5 px-4 flex-shrink-0">
      <div className="font-display font-bold uppercase tracking-wide text-lg mb-6">
        3D <span className="text-bp-cyan">Library</span>
      </div>

      <div className={`bp-nav-top ${view === "dashboard" ? "active" : ""}`} onClick={onSelectDashboard}>
        ⌂ Accueil
      </div>
      <div
        className={`bp-nav-top ${view === "library" && !showingTrash ? "active" : ""}`}
        onClick={() => onSelectLibrary(null)}
      >
        ▦ Bibliothèque
      </div>

      <div className="font-mono text-[10px] text-bp-ink-dim uppercase tracking-wide mt-4 mb-2">
        Listes
      </div>
      {lists.map((list) => (
        <div
          key={list.id}
          className={`bp-nav-item ${view === "library" && !showingTrash && activeListId === list.id ? "active" : ""}`}
          onClick={() => onSelectLibrary(list.id)}
        >
          <span>{list.name}</span>
          <span className="bp-nav-count">{list.model_count}</span>
        </div>
      ))}

      <div
        className={`bp-nav-item mt-2 opacity-80 ${showingTrash ? "active" : ""}`}
        onClick={onSelectTrash}
      >
        <span>🗑 Corbeille</span>
        <span className="bp-nav-count">{trashCount}</span>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Write the StatBar**

Create `frontend/src/components/StatBar.tsx`:

```tsx
import type { Stats } from "../types";

export default function StatBar({ stats }: { stats: Stats | null }) {
  return (
    <div className="flex gap-6 font-mono text-xs">
      <div className="text-right">
        <div className="text-lg text-bp-yellow font-bold">{stats?.total_models ?? "—"}</div>
        <div className="text-[10px] text-bp-ink-dim uppercase">Modèles</div>
      </div>
      <div className="text-right">
        <div className="text-lg text-bp-yellow font-bold">{stats?.total_weight_g ?? "—"}</div>
        <div className="text-[10px] text-bp-ink-dim uppercase">Poids est. (g)</div>
      </div>
      <div className="text-right">
        <div className="text-lg text-bp-yellow font-bold">{stats?.total_print_time_h ?? "—"}</div>
        <div className="text-[10px] text-bp-ink-dim uppercase">Temps est. (h)</div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Write the Dashboard page**

Create `frontend/src/pages/Dashboard.tsx`:

```tsx
import { dimSvg } from "../lib/dimSvg";
import type { ListSummary, Model, Stats } from "../types";
import StatBar from "../components/StatBar";

interface DashboardProps {
  stats: Stats | null;
  lists: ListSummary[];
  onOpenList: (listId: number | null) => void;
}

function RecentCard({ model }: { model: Model }) {
  const isNew = Date.now() - new Date(model.added_at).getTime() < 24 * 3600 * 1000;
  return (
    <div className="w-[150px] flex-shrink-0 bg-bp-panel border border-white/10 rounded-sm p-2.5">
      {isNew && (
        <span className="inline-block bg-bp-yellow/10 text-bp-yellow border border-bp-yellow font-mono text-[9px] px-1 rounded-sm mb-1.5">
          NOUVEAU
        </span>
      )}
      <div className="h-20 bg-bp-deep border border-white/5 mb-2 flex items-center justify-center overflow-hidden">
        {model.thumbnail_path ? (
          <img src={`/api/models/${model.id}/thumbnail`} alt={model.name} className="w-full h-full object-contain" />
        ) : (
          <div
            className="w-full h-full"
            dangerouslySetInnerHTML={{ __html: dimSvg(model.size_x, model.size_y, model.size_z) }}
          />
        )}
      </div>
      <div className="font-display text-[13px] uppercase mb-1">{model.name}</div>
      <div className="font-mono text-[10px] text-bp-ink-dim">
        {new Date(model.added_at).toLocaleDateString("fr-FR")}
      </div>
    </div>
  );
}

export default function Dashboard({ stats, lists, onOpenList }: DashboardProps) {
  return (
    <div className="flex-1 p-8 pb-24">
      <div className="flex justify-between items-end mb-7 border-b border-dashed border-white/10 pb-4">
        <h1 className="font-display uppercase text-2xl tracking-wide m-0">Accueil</h1>
        <StatBar stats={stats} />
      </div>

      <div className="font-mono text-[11px] text-bp-cyan uppercase tracking-wide mb-3">
        Derniers téléchargements
      </div>
      <div className="flex gap-3.5 overflow-x-auto pb-2">
        {(stats?.recent ?? []).map((m) => (
          <RecentCard key={m.id} model={m} />
        ))}
        {stats && stats.recent.length === 0 && (
          <div className="font-mono text-xs text-bp-ink-dim">Aucun modèle pour le moment.</div>
        )}
      </div>

      <div className="font-mono text-[11px] text-bp-cyan uppercase tracking-wide mt-7 mb-3">
        Mes listes
      </div>
      <div className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-3.5">
        {lists.map((list) => (
          <div
            key={list.id}
            className="bg-bp-panel border border-white/10 rounded-sm p-3.5 cursor-pointer hover:border-bp-cyan"
            onClick={() => onOpenList(list.id)}
          >
            <div className="font-display text-sm uppercase flex justify-between">
              <span>{list.name}</span>
              <span className="font-mono text-[11px] text-bp-ink-dim font-normal">{list.model_count}</span>
            </div>
          </div>
        ))}
        {lists.length === 0 && (
          <div className="font-mono text-xs text-bp-ink-dim">
            Aucune liste encore — crée-en une depuis la bibliothèque.
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Wire the App shell**

Replace `frontend/src/App.tsx`:

```tsx
import { useState } from "react";
import Sidebar from "./components/Sidebar";
import Dashboard from "./pages/Dashboard";
import { useLists } from "./hooks/useLists";
import { useStats } from "./hooks/useStats";

type View = "dashboard" | "library";

export default function App() {
  const [view, setView] = useState<View>("dashboard");
  const [libraryListFilter, setLibraryListFilter] = useState<number | null>(null);
  const [showingTrash, setShowingTrash] = useState(false);

  const { lists, refresh: refreshLists } = useLists();
  const { stats, refresh: refreshStats } = useStats();

  function openLibrary(listId: number | null) {
    setLibraryListFilter(listId);
    setShowingTrash(false);
    setView("library");
  }

  function openTrash() {
    setShowingTrash(true);
    setView("library");
  }

  return (
    <div className="flex min-h-screen">
      <Sidebar
        view={view}
        trashCount={stats?.trash_count ?? 0}
        lists={lists}
        activeListId={libraryListFilter}
        showingTrash={showingTrash}
        onSelectDashboard={() => {
          setView("dashboard");
          refreshStats();
        }}
        onSelectLibrary={openLibrary}
        onSelectTrash={openTrash}
      />
      {view === "dashboard" && <Dashboard stats={stats} lists={lists} onOpenList={openLibrary} />}
      {view === "library" && (
        <div className="flex-1 p-8">
          {/* Remplacé par le composant Library dans la Tâche 4 */}
          <p className="font-mono text-xs text-bp-ink-dim">
            Bibliothèque (liste={String(libraryListFilter)}, corbeille={String(showingTrash)}) — à venir.
          </p>
        </div>
      )}
    </div>
  );
}
```

Note: `refreshLists` is currently unused outside this file — it's re-exported
implicitly for Task 4+ once `Library` needs to refresh the sidebar's counts
after a list CRUD action or a trash/restore. Leave the `useLists()` call as
written; Task 4 will thread `refreshLists`/`refreshStats` into `Library`'s
props.

- [ ] **Step 6: Verify in the browser**

Run: `cd frontend && npm run dev`, open `http://localhost:5173`.
Expected: sidebar with "3D Library", "Accueil" (active), "Bibliothèque",
"Listes" section (empty unless you've created some via `curl` against a
running backend), "Corbeille". Dashboard shows stat bar (dashes if no
backend running), "Derniers téléchargements" and "Mes listes" sections.
Clicking "Bibliothèque" or a list switches the right panel to the
placeholder text. For a fuller check, run the backend too
(`LIBRARY_DB_PATH=<path-to-a-real-or-test-library.db> python3 -m webapp --port 8000`
in another terminal) and point Vite's dev server at it by adding to
`frontend/vite.config.ts`:
```ts
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
});
```
then reload — stats and lists should now show real data.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/hooks/useLists.ts frontend/src/hooks/useStats.ts \
  frontend/src/components/Sidebar.tsx frontend/src/components/StatBar.tsx \
  frontend/src/pages/Dashboard.tsx frontend/src/App.tsx frontend/vite.config.ts
git commit -m "feat(frontend): add sidebar navigation and dashboard page"
```

---

### Task 4: Library page — grid view, search, filters, sort

**Files:**
- Create: `frontend/src/hooks/useModels.ts`, `frontend/src/components/FilterBar.tsx`, `frontend/src/components/ModelCard.tsx`, `frontend/src/pages/Library.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `getModels`, `getTrash` (Task 2); `useLists` (Task 3, lifted to `App` and passed down).
- Produces: `Library` component with props `{ listFilter: number | null, showingTrash: boolean, lists: ListSummary[], onListsChanged: () => void, onStatsChanged: () => void }` (Task 5 extends this same component with selection/batch — no new top-level component). `ModelCard` props `{ model: Model, selected: boolean, onToggleSelect: () => void, onOpenDetail: () => void, showingTrash: boolean }` (reused as-is by Task 6's detail overlay trigger).

- [ ] **Step 1: Write the `useModels` hook**

Create `frontend/src/hooks/useModels.ts`:

```ts
import { useCallback, useEffect, useState } from "react";
import { getModels, getTrash } from "../api";
import type { Model, ModelListParams } from "../types";

export function useModels(params: ModelListParams, showingTrash: boolean) {
  const [models, setModels] = useState<Model[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(() => {
    setLoading(true);
    const promise = showingTrash ? getTrash() : getModels(params);
    promise
      .then(setModels)
      .catch(() => setModels([]))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showingTrash, JSON.stringify(params)]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { models, loading, refresh };
}
```

- [ ] **Step 2: Write the FilterBar**

Create `frontend/src/components/FilterBar.tsx`:

```tsx
import type { ListSummary, SortKey } from "../types";

interface FilterBarProps {
  q: string;
  onQChange: (q: string) => void;
  lists: ListSummary[];
  activeListIds: number[];
  onToggleList: (id: number) => void;
  printed: boolean | undefined;
  onTogglePrinted: () => void;
  sort: SortKey;
  onSortChange: (sort: SortKey) => void;
  viewMode: "grid" | "list";
  onViewModeChange: (mode: "grid" | "list") => void;
  showingTrash: boolean;
  trashCount: number;
  onToggleTrash: () => void;
}

const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: "added_desc", label: "Date d'ajout (récent → ancien)" },
  { value: "added_asc", label: "Date d'ajout (ancien → récent)" },
  { value: "name_asc", label: "Nom (A → Z)" },
  { value: "name_desc", label: "Nom (Z → A)" },
  { value: "weight_desc", label: "Poids (lourd → léger)" },
  { value: "weight_asc", label: "Poids (léger → lourd)" },
  { value: "volume_desc", label: "Volume (grand → petit)" },
  { value: "volume_asc", label: "Volume (petit → grand)" },
];

export default function FilterBar(props: FilterBarProps) {
  return (
    <div className="flex gap-2.5 items-center flex-wrap pb-4 border-b border-dashed border-white/10 mb-4">
      <input
        className="flex-1 min-w-[180px] bg-bp-panel border border-white/10 rounded-sm px-3 py-2 text-sm font-mono text-bp-ink placeholder:text-bp-ink-dim outline-none"
        placeholder="nom, tag, fichier d'origine…"
        value={props.q}
        onChange={(e) => props.onQChange(e.target.value)}
        disabled={props.showingTrash}
      />

      {!props.showingTrash &&
        props.lists.map((list) => (
          <div
            key={list.id}
            className={`bp-chip ${props.activeListIds.includes(list.id) ? "active" : ""}`}
            onClick={() => props.onToggleList(list.id)}
          >
            {list.name}
          </div>
        ))}

      {!props.showingTrash && (
        <div className={`bp-chip ${props.printed === true ? "active" : ""}`} onClick={props.onTogglePrinted}>
          {props.printed === true ? "Imprimé" : "Non imprimé/tous"}
        </div>
      )}

      {!props.showingTrash && (
        <select
          className="bg-bp-panel border border-white/10 text-bp-ink rounded-sm px-2.5 py-1.5 font-mono text-[11px]"
          value={props.sort}
          onChange={(e) => props.onSortChange(e.target.value as SortKey)}
        >
          {SORT_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      )}

      <div className="flex border border-white/10 rounded-sm overflow-hidden">
        <button
          className={`px-2.5 py-1.5 text-sm ${props.viewMode === "grid" ? "bg-bp-cyan text-bp-deep" : "bg-bp-panel text-bp-ink-dim"}`}
          onClick={() => props.onViewModeChange("grid")}
        >
          ▦
        </button>
        <button
          className={`px-2.5 py-1.5 text-sm ${props.viewMode === "list" ? "bg-bp-cyan text-bp-deep" : "bg-bp-panel text-bp-ink-dim"}`}
          onClick={() => props.onViewModeChange("list")}
        >
          ☰
        </button>
      </div>

      <button
        className={`ml-auto bp-btn ${props.showingTrash ? "primary" : ""}`}
        onClick={props.onToggleTrash}
      >
        🗑 Corbeille ({props.trashCount})
      </button>
    </div>
  );
}
```

- [ ] **Step 3: Write the ModelCard**

Create `frontend/src/components/ModelCard.tsx`:

```tsx
import { dimSvg } from "../lib/dimSvg";
import type { Model } from "../types";

interface ModelCardProps {
  model: Model;
  selected: boolean;
  onToggleSelect: () => void;
  onOpenDetail: () => void;
}

export default function ModelCard({ model, selected, onToggleSelect, onOpenDetail }: ModelCardProps) {
  return (
    <div className={`bp-card cursor-pointer ${selected ? "selected" : ""}`} onClick={onOpenDetail}>
      <div
        className="bp-checkbox"
        onClick={(e) => {
          e.stopPropagation();
          onToggleSelect();
        }}
      >
        {selected ? "✓" : ""}
      </div>
      {model.printed === 1 && <div className="bp-printed-badge">✓ imprimé</div>}
      <div className="bp-thumb">
        {model.thumbnail_path ? (
          <img src={`/api/models/${model.id}/thumbnail`} alt={model.name} loading="lazy" />
        ) : (
          <div
            className="w-full h-full"
            dangerouslySetInnerHTML={{ __html: dimSvg(model.size_x, model.size_y, model.size_z) }}
          />
        )}
      </div>
      <div className="bp-name">{model.name}</div>
      {model.lists.length > 0 && (
        <div className="flex gap-1.5 flex-wrap mb-2">
          {model.lists.map((l) => (
            <span key={l.id} className="bp-pill">
              {l.name}
            </span>
          ))}
        </div>
      )}
      <div className="bp-meta">
        <span>{model.estimated_weight_g != null ? `${model.estimated_weight_g} g` : "—"}</span>
        <span>{new Date(model.added_at).toLocaleDateString("fr-FR")}</span>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Write the Library page (grid mode only — list mode and selection land in Task 5)**

Create `frontend/src/pages/Library.tsx`:

```tsx
import { useEffect, useMemo, useState } from "react";
import FilterBar from "../components/FilterBar";
import ModelCard from "../components/ModelCard";
import { useModels } from "../hooks/useModels";
import type { ListSummary, SortKey } from "../types";

interface LibraryProps {
  listFilter: number | null;
  showingTrash: boolean;
  lists: ListSummary[];
  trashCount: number;
  onToggleTrash: () => void;
}

export default function Library({ listFilter, showingTrash, lists, trashCount, onToggleTrash }: LibraryProps) {
  const [q, setQ] = useState("");
  const [activeListIds, setActiveListIds] = useState<number[]>(listFilter ? [listFilter] : []);
  const [printed, setPrinted] = useState<boolean | undefined>(undefined);
  const [sort, setSort] = useState<SortKey>("added_desc");
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid");

  useEffect(() => {
    setActiveListIds(listFilter ? [listFilter] : []);
  }, [listFilter]);

  const params = useMemo(
    () => ({ q: q || undefined, lists: activeListIds, printed, sort }),
    [q, activeListIds, printed, sort]
  );
  const { models, loading, refresh } = useModels(params, showingTrash);

  function toggleList(id: number) {
    setActiveListIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  }

  return (
    <div className="flex-1 p-8 pb-24">
      <h1 className="font-display uppercase text-2xl tracking-wide mb-4">
        {showingTrash ? "Corbeille" : "Bibliothèque"}
      </h1>

      <FilterBar
        q={q}
        onQChange={setQ}
        lists={lists}
        activeListIds={activeListIds}
        onToggleList={toggleList}
        printed={printed}
        onTogglePrinted={() => setPrinted((p) => (p === true ? undefined : true))}
        sort={sort}
        onSortChange={setSort}
        viewMode={viewMode}
        onViewModeChange={setViewMode}
        showingTrash={showingTrash}
        trashCount={trashCount}
        onToggleTrash={onToggleTrash}
      />

      {loading && <p className="font-mono text-xs text-bp-ink-dim">Chargement…</p>}
      {!loading && models.length === 0 && (
        <p className="font-mono text-xs text-bp-ink-dim border border-dashed border-white/10 rounded-sm p-8 text-center">
          {showingTrash ? "La corbeille est vide." : "Aucun modèle ne correspond à ces filtres."}
        </p>
      )}

      {!loading && models.length > 0 && viewMode === "grid" && (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(210px,1fr))] gap-4">
          {models.map((model) => (
            <ModelCard
              key={model.id}
              model={model}
              selected={false}
              onToggleSelect={() => {}}
              onOpenDetail={() => {
                /* branché à la Tâche 6 (fiche détail) */
              }}
            />
          ))}
        </div>
      )}

      {!loading && models.length > 0 && viewMode === "list" && (
        <p className="font-mono text-xs text-bp-ink-dim">Mode liste — ajouté à la Tâche 5.</p>
      )}
    </div>
  );
}
```

`refresh` is intentionally unused here — Task 5 calls it after batch actions
and Task 6 after saving/trashing from the detail overlay.

- [ ] **Step 5: Wire `Library` into `App`**

In `frontend/src/App.tsx`, replace the placeholder `<div>` in the
`view === "library"` branch:

```tsx
import Library from "./pages/Library";

// ...

{view === "library" && (
  <Library
    listFilter={libraryListFilter}
    showingTrash={showingTrash}
    lists={lists}
    trashCount={stats?.trash_count ?? 0}
    onToggleTrash={() => setShowingTrash((t) => !t)}
  />
)}
```

- [ ] **Step 6: Verify in the browser**

With the backend running against a real/test `library.db` (see Task 3's Step
6 for the proxy setup), run `npm run dev`, click "Bibliothèque". Expected:
grid of cards (thumbnail or dimension diagram, name, list pills, weight,
date), search box filters as you type (after the debounce built into
`useModels`'s dependency array — typing updates `q` state immediately, the
re-fetch happens on every keystroke since there's no explicit debounce here;
confirm results still update correctly, just more chattily than the old
vanilla 200ms debounce). Click a list chip — grid narrows to that list.
Toggle "Corbeille" — grid should go empty (nothing trashed yet) and the
filter bar's list chips disappear.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/hooks/useModels.ts frontend/src/components/FilterBar.tsx \
  frontend/src/components/ModelCard.tsx frontend/src/pages/Library.tsx frontend/src/App.tsx
git commit -m "feat(frontend): add library page with grid view, search, filters, sort"
```

---

### Task 5: Selection, batch action bar, and list view mode

**Files:**
- Create: `frontend/src/components/BatchActionBar.tsx`, `frontend/src/components/ListPicker.tsx`, `frontend/src/components/ModelRow.tsx`
- Modify: `frontend/src/pages/Library.tsx`

**Interfaces:**
- Consumes: `ModelCard` (Task 4), `batchAction`/`createList` (Task 2).
- Produces: `ListPicker` component `{ lists: ListSummary[], onPick: (listId: number) => void, onListCreated: (list: ListSummary) => void }` (reused as-is by Task 6's detail overlay for per-model list editing).

- [ ] **Step 1: Write the ListPicker (small popover: pick existing list or create one)**

Create `frontend/src/components/ListPicker.tsx`:

```tsx
import { useState } from "react";
import { createList } from "../api";
import type { ListSummary } from "../types";

interface ListPickerProps {
  lists: ListSummary[];
  onPick: (listId: number) => void;
  onListCreated: (list: ListSummary) => void;
  onClose: () => void;
}

export default function ListPicker({ lists, onPick, onListCreated, onClose }: ListPickerProps) {
  const [newName, setNewName] = useState("");
  const [error, setError] = useState("");

  async function handleCreate() {
    const name = newName.trim();
    if (!name) return;
    try {
      const created = await createList(name);
      onListCreated(created);
      onPick(created.id);
      setNewName("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur");
    }
  }

  return (
    <div className="absolute bottom-full mb-2 left-0 bg-bp-panel2 border border-bp-cyan rounded-sm p-3 w-56 z-30">
      <div className="font-mono text-[10px] text-bp-ink-dim uppercase mb-2">Ajouter à une liste</div>
      <div className="max-h-40 overflow-y-auto flex flex-col gap-1 mb-2">
        {lists.map((l) => (
          <button
            key={l.id}
            className="text-left font-mono text-xs px-2 py-1 rounded-sm hover:bg-bp-panel"
            onClick={() => {
              onPick(l.id);
              onClose();
            }}
          >
            {l.name}
          </button>
        ))}
      </div>
      <div className="flex gap-1.5">
        <input
          className="flex-1 bg-bp-deep border border-white/10 rounded-sm px-2 py-1 text-xs font-mono text-bp-ink outline-none"
          placeholder="Nouvelle liste…"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleCreate()}
        />
        <button className="bp-btn" onClick={handleCreate}>
          +
        </button>
      </div>
      {error && <div className="text-bp-red text-[10px] font-mono mt-1">{error}</div>}
    </div>
  );
}
```

- [ ] **Step 2: Write the BatchActionBar**

Create `frontend/src/components/BatchActionBar.tsx`:

```tsx
import { useState } from "react";
import ListPicker from "./ListPicker";
import type { ListSummary } from "../types";

interface BatchActionBarProps {
  count: number;
  lists: ListSummary[];
  showingTrash: boolean;
  onAddToList: (listId: number) => void;
  onListCreated: (list: ListSummary) => void;
  onSetPrinted: () => void;
  onTrash: () => void;
  onRestore: () => void;
  onDeletePermanently: () => void;
  onClear: () => void;
}

export default function BatchActionBar(props: BatchActionBarProps) {
  const [pickerOpen, setPickerOpen] = useState(false);

  if (props.count === 0) return null;

  return (
    <div className="bp-batchbar relative">
      <span className="text-bp-yellow font-bold pr-2 border-r border-white/10">
        {props.count} sélectionné{props.count > 1 ? "s" : ""}
      </span>

      {!props.showingTrash && (
        <div className="relative">
          <button onClick={() => setPickerOpen((o) => !o)}>+ Liste</button>
          {pickerOpen && (
            <ListPicker
              lists={props.lists}
              onPick={(id) => {
                props.onAddToList(id);
                setPickerOpen(false);
              }}
              onListCreated={props.onListCreated}
              onClose={() => setPickerOpen(false)}
            />
          )}
        </div>
      )}

      {!props.showingTrash && <button onClick={props.onSetPrinted}>✓ Imprimé</button>}
      {!props.showingTrash && <button onClick={props.onTrash}>🗑 Corbeille</button>}
      {props.showingTrash && <button onClick={props.onRestore}>↺ Restaurer</button>}
      <button className="danger" onClick={props.onDeletePermanently}>
        Supprimer déf.
      </button>
      <button onClick={props.onClear}>Annuler</button>
    </div>
  );
}
```

- [ ] **Step 3: Write the ModelRow (list view mode)**

Create `frontend/src/components/ModelRow.tsx`:

```tsx
import { dimSvg } from "../lib/dimSvg";
import type { Model } from "../types";

interface ModelRowProps {
  model: Model;
  selected: boolean;
  onToggleSelect: () => void;
  onOpenDetail: () => void;
}

export default function ModelRow({ model, selected, onToggleSelect, onOpenDetail }: ModelRowProps) {
  return (
    <div
      className={`grid grid-cols-[32px_48px_2fr_1.4fr_90px_90px_90px_70px] items-center gap-2.5 px-3 py-2 border-t border-white/5 bg-bp-panel text-xs cursor-pointer ${selected ? "ring-1 ring-bp-yellow" : ""}`}
      onClick={onOpenDetail}
    >
      <div
        className="bp-checkbox relative top-0 left-0"
        onClick={(e) => {
          e.stopPropagation();
          onToggleSelect();
        }}
      >
        {selected ? "✓" : ""}
      </div>
      <div className="w-10 h-[30px] bg-bp-deep border border-white/5 overflow-hidden">
        {model.thumbnail_path ? (
          <img src={`/api/models/${model.id}/thumbnail`} alt="" className="w-full h-full object-contain" />
        ) : (
          <div
            className="w-full h-full [&_svg]:w-full [&_svg]:h-full"
            dangerouslySetInnerHTML={{ __html: dimSvg(model.size_x, model.size_y, model.size_z) }}
          />
        )}
      </div>
      <div className="font-display text-[13px] uppercase">{model.name}</div>
      <div className="flex gap-1 flex-wrap">
        {model.lists.map((l) => (
          <span key={l.id} className="bp-pill">
            {l.name}
          </span>
        ))}
      </div>
      <div className="font-mono text-[11px] text-bp-ink-dim">
        {model.estimated_weight_g != null ? `${model.estimated_weight_g} g` : "—"}
      </div>
      <div className="font-mono text-[11px] text-bp-ink-dim">
        {model.volume != null ? `${model.volume} cm³` : "—"}
      </div>
      <div className="font-mono text-[11px] text-bp-ink-dim">
        {new Date(model.added_at).toLocaleDateString("fr-FR")}
      </div>
      <div className="text-bp-green">{model.printed === 1 ? "✓" : "—"}</div>
    </div>
  );
}
```

- [ ] **Step 4: Wire selection, batch actions, and list mode into `Library`**

Replace `frontend/src/pages/Library.tsx`'s body (keep the state/hooks from
Task 4, add the following):

```tsx
import { useEffect, useMemo, useState } from "react";
import BatchActionBar from "../components/BatchActionBar";
import FilterBar from "../components/FilterBar";
import ModelCard from "../components/ModelCard";
import ModelRow from "../components/ModelRow";
import { batchAction } from "../api";
import { useModels } from "../hooks/useModels";
import type { ListSummary, SortKey } from "../types";

interface LibraryProps {
  listFilter: number | null;
  showingTrash: boolean;
  lists: ListSummary[];
  trashCount: number;
  onToggleTrash: () => void;
  onListsChanged: () => void;
  onStatsChanged: () => void;
  onListCreated: (list: ListSummary) => void;
}

export default function Library({
  listFilter,
  showingTrash,
  lists,
  trashCount,
  onToggleTrash,
  onListsChanged,
  onStatsChanged,
  onListCreated,
}: LibraryProps) {
  const [q, setQ] = useState("");
  const [activeListIds, setActiveListIds] = useState<number[]>(listFilter ? [listFilter] : []);
  const [printed, setPrinted] = useState<boolean | undefined>(undefined);
  const [sort, setSort] = useState<SortKey>("added_desc");
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid");
  const [selected, setSelected] = useState<Set<number>>(new Set());

  useEffect(() => {
    setActiveListIds(listFilter ? [listFilter] : []);
    setSelected(new Set());
  }, [listFilter]);

  useEffect(() => {
    setSelected(new Set());
  }, [showingTrash]);

  const params = useMemo(
    () => ({ q: q || undefined, lists: activeListIds, printed, sort }),
    [q, activeListIds, printed, sort]
  );
  const { models, loading, refresh } = useModels(params, showingTrash);

  // Une fois les modèles rechargés (filtre changé), la sélection ne doit
  // référencer que des ids encore visibles — sinon "supprimer" sur une
  // sélection obsolète agirait sur du vide silencieusement.
  useEffect(() => {
    setSelected((prev) => {
      const visibleIds = new Set(models.map((m) => m.id));
      const next = new Set<number>();
      prev.forEach((id) => {
        if (visibleIds.has(id)) next.add(id);
      });
      return next;
    });
  }, [models]);

  function toggleList(id: number) {
    setActiveListIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  }

  function toggleSelect(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  async function runBatch(action: Parameters<typeof batchAction>[0]["action"], extra: object = {}) {
    if (selected.size === 0) return;
    await batchAction({ ids: Array.from(selected), action, ...extra });
    setSelected(new Set());
    refresh();
    onListsChanged();
    onStatsChanged();
  }

  return (
    <div className="flex-1 p-8 pb-24">
      <h1 className="font-display uppercase text-2xl tracking-wide mb-4">
        {showingTrash ? "Corbeille" : "Bibliothèque"}
      </h1>

      <FilterBar
        q={q}
        onQChange={setQ}
        lists={lists}
        activeListIds={activeListIds}
        onToggleList={toggleList}
        printed={printed}
        onTogglePrinted={() => setPrinted((p) => (p === true ? undefined : true))}
        sort={sort}
        onSortChange={setSort}
        viewMode={viewMode}
        onViewModeChange={setViewMode}
        showingTrash={showingTrash}
        trashCount={trashCount}
        onToggleTrash={onToggleTrash}
      />

      {loading && <p className="font-mono text-xs text-bp-ink-dim">Chargement…</p>}
      {!loading && models.length === 0 && (
        <p className="font-mono text-xs text-bp-ink-dim border border-dashed border-white/10 rounded-sm p-8 text-center">
          {showingTrash ? "La corbeille est vide." : "Aucun modèle ne correspond à ces filtres."}
        </p>
      )}

      {!loading && models.length > 0 && viewMode === "grid" && (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(210px,1fr))] gap-4">
          {models.map((model) => (
            <ModelCard
              key={model.id}
              model={model}
              selected={selected.has(model.id)}
              onToggleSelect={() => toggleSelect(model.id)}
              onOpenDetail={() => {
                /* branché à la Tâche 6 (fiche détail) */
              }}
            />
          ))}
        </div>
      )}

      {!loading && models.length > 0 && viewMode === "list" && (
        <div className="border border-white/10 rounded-sm overflow-hidden">
          <div className="grid grid-cols-[32px_48px_2fr_1.4fr_90px_90px_90px_70px] gap-2.5 px-3 py-2 bg-bp-panel2 font-mono text-[10px] text-bp-ink-dim uppercase">
            <span /> <span /> <span>Nom</span> <span>Listes</span> <span>Poids</span> <span>Volume</span>{" "}
            <span>Ajouté le</span> <span>Imprimé</span>
          </div>
          {models.map((model) => (
            <ModelRow
              key={model.id}
              model={model}
              selected={selected.has(model.id)}
              onToggleSelect={() => toggleSelect(model.id)}
              onOpenDetail={() => {}}
            />
          ))}
        </div>
      )}

      <BatchActionBar
        count={selected.size}
        lists={lists}
        showingTrash={showingTrash}
        onAddToList={(listId) => runBatch("add_list", { list_id: listId })}
        onListCreated={onListCreated}
        onSetPrinted={() => runBatch("set_printed", { printed: true })}
        onTrash={() => runBatch("trash")}
        onRestore={() => runBatch("restore")}
        onDeletePermanently={() => runBatch("delete")}
        onClear={() => setSelected(new Set())}
      />
    </div>
  );
}
```

Update `frontend/src/App.tsx`'s `<Library .../>` call to pass the three new
props:

```tsx
<Library
  listFilter={libraryListFilter}
  showingTrash={showingTrash}
  lists={lists}
  trashCount={stats?.trash_count ?? 0}
  onToggleTrash={() => setShowingTrash((t) => !t)}
  onListsChanged={refreshLists}
  onStatsChanged={refreshStats}
  onListCreated={() => refreshLists()}
/>
```

- [ ] **Step 5: Verify in the browser**

With the backend running: create two or three test models directly via
`curl` against `POST /api/models/batch`-adjacent endpoints or by scanning a
real folder. In the UI: select two cards (checkbox), confirm the floating
batch bar appears bottom-center with uniform-height buttons; click "+
Liste", type a new name, press Enter — confirm it's created, the model is
added to it, and the new list immediately appears as a chip option next
time you open the picker without reloading. Click "Mettre à la corbeille" on
a selection, confirm those cards disappear from the normal view and the
sidebar's "Corbeille" count increments. Toggle to "Corbeille", select a
model, click "Restaurer", confirm it reappears in the normal view. Switch to
list mode (☰) and confirm the same selection/columns work there too. Change
a filter while 2 items are selected and confirm the selection count drops to
only the still-visible ones (or to 0) instead of silently keeping stale ids.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/BatchActionBar.tsx frontend/src/components/ListPicker.tsx \
  frontend/src/components/ModelRow.tsx frontend/src/pages/Library.tsx frontend/src/App.tsx
git commit -m "feat(frontend): add multi-select, batch actions, and list view mode"
```

---

### Task 6: Model detail overlay (incl. ported Three.js viewer)

**Files:**
- Create: `frontend/src/components/Viewer3D.tsx`, `frontend/src/components/ModelDetailOverlay.tsx`
- Modify: `frontend/src/pages/Library.tsx`

**Interfaces:**
- Consumes: `getModel`, `updateModel`, `setModelLists`, `trashModel`, `restoreModel`, `deleteModelPermanently`, `openFolder`, `openOrcaSlicer` (Task 2); `ListPicker`-style list toggling (Task 5, but reimplemented here as checkboxes since the overlay shows all lists at once rather than a popover).
- Produces: `ModelDetailOverlay` props `{ modelId: number, showingTrash: boolean, lists: ListSummary[], onClose: () => void, onChanged: () => void }` — `onOpenDetail` callbacks wired in Tasks 4/5 now receive a real implementation.

- [ ] **Step 1: Port the Three.js viewer**

Create `frontend/src/components/Viewer3D.tsx` (direct port of
`static/index.html`'s `load3DViewer`, adapted to React's lifecycle):

```tsx
import { useEffect, useRef } from "react";
import * as THREE from "three";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

export default function Viewer3D({ modelId }: { modelId: number }) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    let rafId = 0;
    let disposed = false;
    const width = container.clientWidth || 300;
    const height = container.clientHeight || 200;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 10000);
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

    scene.add(new THREE.AmbientLight(0xffffff, 0.7));
    const key = new THREE.DirectionalLight(0xffffff, 0.9);
    key.position.set(1, 1, 1);
    scene.add(key);
    const fill = new THREE.DirectionalLight(0xffffff, 0.35);
    fill.position.set(-1, -0.5, -1);
    scene.add(fill);

    let controls: OrbitControls | undefined;

    new STLLoader().load(
      `/api/models/${modelId}/stl`,
      (geometry) => {
        if (disposed) return;
        geometry.center();
        geometry.computeBoundingBox();

        const material = new THREE.MeshStandardMaterial({
          color: 0xe9eff3,
          metalness: 0.05,
          roughness: 0.65,
        });
        const mesh = new THREE.Mesh(geometry, material);
        mesh.rotation.x = -Math.PI / 2;
        scene.add(mesh);

        const size = new THREE.Vector3();
        geometry.boundingBox!.getSize(size);
        const maxDim = Math.max(size.x, size.y, size.z) || 1;
        camera.position.set(maxDim * 1.1, maxDim * 0.9, maxDim * 1.4);
        camera.lookAt(0, 0, 0);

        controls = new OrbitControls(camera, renderer.domElement);
        controls.enableDamping = true;
        controls.dampingFactor = 0.08;

        container.innerHTML = "";
        container.appendChild(renderer.domElement);

        const animate = () => {
          rafId = requestAnimationFrame(animate);
          controls?.update();
          renderer.render(scene, camera);
        };
        animate();
      },
      undefined,
      () => {
        if (!disposed) {
          container.innerHTML =
            '<div class="font-mono text-xs text-bp-red p-2.5">Impossible de charger le rendu 3D</div>';
        }
      }
    );

    return () => {
      disposed = true;
      cancelAnimationFrame(rafId);
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [modelId]);

  return <div ref={containerRef} className="w-full h-full" />;
}
```

- [ ] **Step 2: Write the ModelDetailOverlay**

Create `frontend/src/components/ModelDetailOverlay.tsx`:

```tsx
import { useEffect, useState } from "react";
import {
  deleteModelPermanently,
  getModel,
  openFolder,
  openOrcaSlicer,
  restoreModel,
  setModelLists,
  trashModel,
  updateModel,
} from "../api";
import { dimSvg } from "../lib/dimSvg";
import type { ListSummary, Model } from "../types";
import Viewer3D from "./Viewer3D";

interface ModelDetailOverlayProps {
  modelId: number;
  showingTrash: boolean;
  lists: ListSummary[];
  onClose: () => void;
  onChanged: () => void;
}

function fmt(v: number | null | undefined, unit = ""): string {
  return v === null || v === undefined ? "—" : `${v}${unit}`;
}

export default function ModelDetailOverlay({
  modelId,
  showingTrash,
  lists,
  onClose,
  onChanged,
}: ModelDetailOverlayProps) {
  const [model, setModel] = useState<Model | null>(null);
  const [editing, setEditing] = useState(false);
  const [show3D, setShow3D] = useState(false);
  const [message, setMessage] = useState<{ text: string; kind: "ok" | "error" } | null>(null);

  const [form, setForm] = useState({ name: "", material: "", tags: "", printed: false, listIds: [] as number[] });

  useEffect(() => {
    getModel(modelId).then((m) => {
      setModel(m);
      setForm({
        name: m.name,
        material: m.material ?? "",
        tags: m.tags ?? "",
        printed: m.printed === 1,
        listIds: m.lists.map((l) => l.id),
      });
    });
  }, [modelId]);

  async function handleAction(fn: () => Promise<unknown>, okText: string) {
    try {
      await fn();
      setMessage({ text: okText, kind: "ok" });
      onChanged();
    } catch (e) {
      setMessage({ text: e instanceof Error ? e.message : "Erreur", kind: "error" });
    }
  }

  async function handleSave() {
    if (!model) return;
    try {
      await updateModel(model.id, {
        name: form.name,
        material: form.material,
        tags: form.tags,
        printed: form.printed,
      });
      await setModelLists(model.id, form.listIds);
      setMessage({ text: "Modifications sauvegardées", kind: "ok" });
      onChanged();
      const refreshed = await getModel(model.id);
      setModel(refreshed);
    } catch (e) {
      setMessage({ text: e instanceof Error ? e.message : "Erreur sauvegarde", kind: "error" });
    }
  }

  if (!model) return null;

  function toggleListId(id: number) {
    setForm((f) => ({
      ...f,
      listIds: f.listIds.includes(id) ? f.listIds.filter((x) => x !== id) : [...f.listIds, id],
    }));
  }

  return (
    <div className="bp-detail-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="bp-detail max-h-[90vh] overflow-y-auto">
        <h2 className="font-display uppercase text-xl m-0 mb-1">{model.name}</h2>
        <div className="font-mono text-[11px] text-bp-ink-dim break-all mb-4">{model.path}</div>

        <div className="bp-thumb h-[180px] my-3.5">
          {show3D ? (
            <Viewer3D modelId={model.id} />
          ) : model.thumbnail_path ? (
            <img src={`/api/models/${model.id}/thumbnail`} alt={model.name} />
          ) : (
            <div className="w-full" dangerouslySetInnerHTML={{ __html: dimSvg(model.size_x, model.size_y, model.size_z) }} />
          )}
        </div>
        {!show3D && (
          <button className="bp-btn w-full mb-2.5" onClick={() => setShow3D(true)}>
            Vue 3D interactive
          </button>
        )}

        <dl className="grid grid-cols-[auto_1fr] gap-2 gap-x-4 font-mono text-xs">
          <dt className="text-bp-ink-dim uppercase">Dimensions</dt>
          <dd className="m-0">{fmt(model.size_x)} × {fmt(model.size_y)} × {fmt(model.size_z)} mm</dd>
          <dt className="text-bp-ink-dim uppercase">Volume</dt>
          <dd className="m-0">{fmt(model.volume, " cm³")}</dd>
          <dt className="text-bp-ink-dim uppercase">Matériau</dt>
          <dd className="m-0">{model.material || "—"}</dd>
          <dt className="text-bp-ink-dim uppercase">Poids estimé</dt>
          <dd className="m-0">{fmt(model.estimated_weight_g, " g")}</dd>
          <dt className="text-bp-ink-dim uppercase">Temps estimé</dt>
          <dd className="m-0">{fmt(model.estimated_print_time_h, " h")}</dd>
          <dt className="text-bp-ink-dim uppercase">Mesh fermé</dt>
          <dd className="m-0">{model.is_watertight ? "oui" : "non (estimation approx.)"}</dd>
          <dt className="text-bp-ink-dim uppercase">Tags</dt>
          <dd className="m-0">{model.tags || "—"}</dd>
          <dt className="text-bp-ink-dim uppercase">Ajouté le</dt>
          <dd className="m-0">{model.added_at.split("T")[0]}</dd>
        </dl>

        {editing && (
          <div className="mt-5 flex flex-col gap-2.5">
            <label className="font-mono text-[11px] text-bp-ink-dim">
              Nom
              <input
                className="w-full bg-bp-deep border border-white/10 text-bp-ink p-2 font-mono mt-1"
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              />
            </label>
            <label className="font-mono text-[11px] text-bp-ink-dim">
              Matériau
              <input
                className="w-full bg-bp-deep border border-white/10 text-bp-ink p-2 font-mono mt-1"
                value={form.material}
                onChange={(e) => setForm((f) => ({ ...f, material: e.target.value }))}
              />
            </label>
            <label className="font-mono text-[11px] text-bp-ink-dim">
              Tags
              <input
                className="w-full bg-bp-deep border border-white/10 text-bp-ink p-2 font-mono mt-1"
                value={form.tags}
                onChange={(e) => setForm((f) => ({ ...f, tags: e.target.value }))}
              />
            </label>

            <div className="font-mono text-[11px] text-bp-ink-dim mt-1">Listes</div>
            <div className="flex gap-1.5 flex-wrap">
              {lists.map((l) => (
                <span
                  key={l.id}
                  className={`bp-pill cursor-pointer ${form.listIds.includes(l.id) ? "" : "opacity-40"}`}
                  onClick={() => toggleListId(l.id)}
                >
                  {l.name}
                </span>
              ))}
            </div>

            <label className="flex items-center gap-2 font-mono text-[11px] text-bp-ink-dim mt-1">
              <input
                type="checkbox"
                checked={form.printed}
                onChange={(e) => setForm((f) => ({ ...f, printed: e.target.checked }))}
              />
              Imprimé
            </label>

            <button className="bp-btn primary" onClick={handleSave}>
              Sauvegarder
            </button>
          </div>
        )}

        {!editing && model.lists.length > 0 && (
          <div className="flex gap-1.5 flex-wrap mt-4">
            {model.lists.map((l) => (
              <span key={l.id} className="bp-pill">
                {l.name}
              </span>
            ))}
          </div>
        )}

        <div className="flex gap-2.5 mt-4 flex-wrap">
          {!showingTrash && (
            <>
              <button className="bp-btn primary" onClick={() => handleAction(() => openOrcaSlicer(model.id), "Ouvert dans OrcaSlicer")}>
                Ouvrir dans OrcaSlicer
              </button>
              <button className="bp-btn" onClick={() => handleAction(async () => setMessage({ text: `Dossier ouvert : ${(await openFolder(model.id)).folder}`, kind: "ok" }), "")}>
                Ouvrir le dossier
              </button>
              <button className="bp-btn" onClick={() => setEditing((e) => !e)}>
                Modifier
              </button>
              <button className="bp-btn" onClick={() => handleAction(() => trashModel(model.id), "Mis à la corbeille").then(onClose)}>
                Mettre à la corbeille
              </button>
            </>
          )}
          {showingTrash && (
            <button className="bp-btn primary" onClick={() => handleAction(() => restoreModel(model.id), "Restauré").then(onClose)}>
              Restaurer
            </button>
          )}
          <button
            className="bp-btn"
            style={{ borderColor: "#E2725B", color: "#E2725B" }}
            onClick={() => handleAction(() => deleteModelPermanently(model.id), "Supprimé définitivement").then(onClose)}
          >
            Supprimer définitivement
          </button>
          <button className="bp-btn" onClick={onClose}>
            Fermer
          </button>
        </div>

        {message && (
          <div className={`font-mono text-[11px] mt-2.5 ${message.kind === "error" ? "text-bp-red" : "text-bp-green"}`}>
            {message.text}
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Wire the overlay into `Library`**

In `frontend/src/pages/Library.tsx`, add state and render the overlay,
replacing both `onOpenDetail={() => { /* ... */ }}` placeholders:

```tsx
import ModelDetailOverlay from "../components/ModelDetailOverlay";

// inside the component:
const [detailId, setDetailId] = useState<number | null>(null);

// ModelCard / ModelRow:
onOpenDetail={() => setDetailId(model.id)}

// at the end of the returned JSX, right before the closing </div>:
{detailId !== null && (
  <ModelDetailOverlay
    modelId={detailId}
    showingTrash={showingTrash}
    lists={lists}
    onClose={() => setDetailId(null)}
    onChanged={() => {
      refresh();
      onListsChanged();
      onStatsChanged();
    }}
  />
)}
```

- [ ] **Step 4: Verify in the browser**

Click a card: overlay opens with dimensions, volume, tags, lists as pills.
Click "Vue 3D interactive": the Three.js viewer loads and is orbit-draggable
(same behavior as the current `static/index.html`). Click "Modifier":
form appears with name/material/tags/list-pills (click to toggle, dimmed =
not selected)/printed checkbox — close the overlay without clicking
"Sauvegarder" and reopen it: confirm the list toggle you made was NOT
persisted. Reopen, toggle a list, click "Sauvegarder": confirm the pill
list updates and the grid behind it (after closing) shows the change.
Trash a model from the overlay: confirm the overlay closes and the model
disappears from the library view. Open a trashed model from the Corbeille
view: confirm only "Restaurer" and "Supprimer définitivement" show (no
"Mettre à la corbeille", no "Modifier").

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/Viewer3D.tsx frontend/src/components/ModelDetailOverlay.tsx \
  frontend/src/pages/Library.tsx
git commit -m "feat(frontend): add model detail overlay with 3D viewer, editing, and list toggles"
```

---

### Task 7: List management in the sidebar (rename/delete)

**Files:**
- Modify: `frontend/src/components/Sidebar.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `renameList`, `deleteList` (Task 2).
- Produces: nothing new consumed by later tasks — this is the last piece of list CRUD surfaced in the UI (creation already works via `ListPicker`, Task 5).

- [ ] **Step 1: Add inline rename/delete controls to the Sidebar**

Replace the list-rendering block in `frontend/src/components/Sidebar.tsx`
(inside the `lists.map(...)` from Task 3) with a version exposing a small
"⋯" affordance on hover, calling two new props:

```tsx
interface SidebarProps {
  // ...existing props from Task 3...
  onRenameList: (list: ListSummary) => void;
  onDeleteList: (list: ListSummary) => void;
}

// replace the lists.map(...) block:
{lists.map((list) => (
  <div
    key={list.id}
    className={`bp-nav-item group ${view === "library" && !showingTrash && activeListId === list.id ? "active" : ""}`}
  >
    <span className="flex-1 cursor-pointer" onClick={() => onSelectLibrary(list.id)}>
      {list.name}
    </span>
    <span className="bp-nav-count">{list.model_count}</span>
    <span
      className="opacity-0 group-hover:opacity-100 ml-1 cursor-pointer text-bp-ink-dim hover:text-bp-cyan"
      onClick={(e) => {
        e.stopPropagation();
        onRenameList(list);
      }}
      title="Renommer"
    >
      ✎
    </span>
    <span
      className="opacity-0 group-hover:opacity-100 ml-1 cursor-pointer text-bp-ink-dim hover:text-bp-red"
      onClick={(e) => {
        e.stopPropagation();
        onDeleteList(list);
      }}
      title="Supprimer la liste"
    >
      ✕
    </span>
  </div>
))}
```

- [ ] **Step 2: Wire rename/delete in `App.tsx`**

```tsx
import { deleteList, renameList } from "./api";

// inside App():
async function handleRenameList(list: ListSummary) {
  const name = window.prompt("Nouveau nom de la liste :", list.name);
  if (!name || name.trim() === list.name) return;
  await renameList(list.id, name.trim());
  refreshLists();
}

async function handleDeleteList(list: ListSummary) {
  if (!window.confirm(`Supprimer la liste "${list.name}" ? Les modèles ne seront pas supprimés.`)) return;
  await deleteList(list.id);
  refreshLists();
  if (libraryListFilter === list.id) setLibraryListFilter(null);
}

// pass to <Sidebar .../>:
onRenameList={handleRenameList}
onDeleteList={handleDeleteList}
```

- [ ] **Step 3: Verify in the browser**

Hover a list in the sidebar: "✎" and "✕" appear. Rename a list via the
prompt, confirm the sidebar and the library's filter chips update. Delete a
list that has models in it, confirm the models remain in the library
(just without that list's pill) and the sidebar entry disappears. If you
had that list active as a filter, confirm the library view resets to
unfiltered instead of showing a phantom empty filter.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/Sidebar.tsx frontend/src/App.tsx
git commit -m "feat(frontend): add list rename/delete from the sidebar"
```

---

### Task 8: Remove the legacy static page and update docs

**Files:**
- Delete: `static/index.html`
- Modify: `webapp.py` (drop the fallback branch now that it's unreachable)
- Modify: `README.md` (document the new `frontend/` dev/build workflow)

**Interfaces:**
- Consumes: everything above — this task only removes the now-dead fallback path and documents the new workflow. No new interfaces produced.

- [ ] **Step 1: Simplify `webapp.py`'s index route**

Replace the `index()` route and the comment above the static mount
(introduced in Task 1) with:

```python
FRONTEND_DIST = Path(__file__).parent / "frontend" / "dist"


@app.get("/")
def index():
    return FileResponse(FRONTEND_DIST / "index.html")


app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="frontend-assets")
```

Remove the now-unused `static_dir` creation/mount block entirely (the React
app serves everything that `static/index.html` used to).

- [ ] **Step 2: Delete the legacy file**

```bash
git rm static/index.html
```

- [ ] **Step 3: Update the README's "run the web UI" section**

Add a short section to `README.md` documenting:
```markdown
## Interface web (développement)

```bash
cd frontend
npm install
npm run dev        # serveur de dev Vite sur http://localhost:5173, proxy /api vers le backend FastAPI
```

## Interface web (production)

```bash
cd frontend
npm run build       # génère frontend/dist, servi par FastAPI à la racine
```
```
(Adjust to match whatever existing README sections already describe running
`webapp.py` — insert this alongside them rather than duplicating backend run
instructions.)

- [ ] **Step 4: Verify the full production flow end-to-end**

```bash
cd frontend && npm run build && cd ..
LIBRARY_DB_PATH=/tmp/ui-plan-check-final/library.db python3 -c "
from pathlib import Path
import scanner
Path('/tmp/ui-plan-check-final').mkdir(exist_ok=True)
scanner.init_db(Path('/tmp/ui-plan-check-final/library.db')).close()
"
python3 -m webapp --library /tmp/ui-plan-check-final --port 8020 &
sleep 1
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8020/
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8020/api/stats
kill %1
```
Expected: both `curl` calls print `200`. Then open `http://127.0.0.1:8020`
in a real browser (restart the server without `&`/`kill` for this) and
click through Accueil → Bibliothèque → a model's detail overlay to confirm
the production build behaves the same as the dev server did in earlier
tasks.

- [ ] **Step 5: Run the backend pytest suite one last time**

Run: `python3 -m pytest -v`
Expected: PASS — removing `static/index.html` must not break any backend
test (none of them reference it; `webapp.py`'s `/` route has no test
asserting the old file's content).

- [ ] **Step 6: Commit**

```bash
git add webapp.py README.md
git commit -m "chore(frontend): remove legacy static page now that the React app covers it"
```

---

## After this plan

The UI overhaul described in
`docs/superpowers/specs/2026-10-09-ui-overhaul-design.md` is complete:
dashboard, library with combined filters/sort/grid-or-list/selection/batch
actions, trash with timed purge, per-model lists replacing the old
auto-category, and a printed flag — all backed by tested API endpoints and
a from-scratch React UI that keeps the original visual identity.
