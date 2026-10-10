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
  onRenameList: (list: ListSummary) => void;
  onDeleteList: (list: ListSummary) => void;
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
  onRenameList,
  onDeleteList,
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
