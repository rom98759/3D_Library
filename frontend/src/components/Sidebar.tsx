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
