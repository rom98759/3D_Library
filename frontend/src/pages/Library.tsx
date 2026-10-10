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
  const { models, loading } = useModels(params, showingTrash);

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
