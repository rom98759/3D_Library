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
