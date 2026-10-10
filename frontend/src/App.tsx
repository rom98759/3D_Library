import { useState } from "react";
import Sidebar from "./components/Sidebar";
import Dashboard from "./pages/Dashboard";
import Library from "./pages/Library";
import { deleteList, renameList } from "./api";
import { useLists } from "./hooks/useLists";
import { useStats } from "./hooks/useStats";
import type { ListSummary } from "./types";

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

  async function handleRenameList(list: ListSummary) {
    const name = window.prompt("Nouveau nom de la liste :", list.name);
    if (!name || name.trim() === list.name) return;
    try {
      await renameList(list.id, name.trim());
      refreshLists();
    } catch (e) {
      window.alert(e instanceof Error ? e.message : "Erreur lors du renommage de la liste");
    }
  }

  async function handleDeleteList(list: ListSummary) {
    if (!window.confirm(`Supprimer la liste "${list.name}" ? Les modèles ne seront pas supprimés.`)) return;
    try {
      await deleteList(list.id);
      refreshLists();
      if (libraryListFilter === list.id) setLibraryListFilter(null);
    } catch (e) {
      window.alert(e instanceof Error ? e.message : "Erreur lors de la suppression de la liste");
    }
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
        onRenameList={handleRenameList}
        onDeleteList={handleDeleteList}
      />
      {view === "dashboard" && (
        <Dashboard stats={stats} lists={lists} onOpenList={openLibrary} onStatsChanged={refreshStats} />
      )}
      {view === "library" && (
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
      )}
    </div>
  );
}
