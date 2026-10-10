import { useState } from "react";
import Sidebar from "./components/Sidebar";
import Dashboard from "./pages/Dashboard";
import Library from "./pages/Library";
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
