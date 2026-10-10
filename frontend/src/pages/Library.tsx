import { useEffect, useMemo, useState } from "react";
import BatchActionBar from "../components/BatchActionBar";
import FilterBar from "../components/FilterBar";
import ModelCard from "../components/ModelCard";
import ModelDetailOverlay from "../components/ModelDetailOverlay";
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
  const [detailId, setDetailId] = useState<number | null>(null);

  useEffect(() => {
    setActiveListIds(listFilter ? [listFilter] : []);
    setSelected(new Set());
  }, [listFilter]);

  useEffect(() => {
    setSelected(new Set());
  }, [showingTrash]);

  // Si une liste filtrée via une chip (plutôt que depuis la sidebar) est
  // supprimée ailleurs, elle disparaît de `lists` sans que `listFilter` ne
  // change — sans ce nettoyage, le filtre resterait bloqué sur un id de
  // liste qui n'existe plus, avec aucune chip pour le retirer.
  useEffect(() => {
    const validIds = new Set(lists.map((l) => l.id));
    setActiveListIds((prev) => prev.filter((id) => validIds.has(id)));
  }, [lists]);

  const params = useMemo(
    () => ({ q: q || undefined, lists: activeListIds, printed, sort }),
    [q, activeListIds, printed, sort]
  );
  const { models, loading, refresh } = useModels(params, showingTrash);

  // Dès qu'un filtre change, la sélection est vidée immédiatement — sans
  // attendre la fin du rechargement, sinon la barre d'actions resterait
  // active sur des ids qui ne correspondent déjà plus à ce qui est affiché
  // pendant la fenêtre de chargement.
  useEffect(() => {
    setSelected(new Set());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(params)]);

  // Une fois les modèles rechargés, la sélection ne doit référencer que des
  // ids encore visibles — filet de sécurité supplémentaire (ex. un modèle
  // supprimé par ailleurs entre deux rechargements).
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
    if (action === "delete") {
      const count = selected.size;
      if (!window.confirm(`Supprimer définitivement ${count} modèle${count > 1 ? "s" : ""} et ses fichiers ? Cette action est irréversible.`)) {
        return;
      }
    }
    try {
      await batchAction({ ids: Array.from(selected), action, ...extra });
      setSelected(new Set());
      refresh();
      onListsChanged();
      onStatsChanged();
    } catch (e) {
      window.alert(e instanceof Error ? e.message : "Erreur lors de l'action groupée");
    }
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
              onOpenDetail={() => setDetailId(model.id)}
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
              onOpenDetail={() => setDetailId(model.id)}
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
    </div>
  );
}
