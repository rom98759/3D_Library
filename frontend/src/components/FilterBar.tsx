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
