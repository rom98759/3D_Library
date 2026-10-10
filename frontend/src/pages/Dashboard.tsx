import { useState } from "react";
import { dimSvg } from "../lib/dimSvg";
import type { ListSummary, Model, Stats } from "../types";
import ModelDetailOverlay from "../components/ModelDetailOverlay";
import StatBar from "../components/StatBar";

interface DashboardProps {
  stats: Stats | null;
  lists: ListSummary[];
  onOpenList: (listId: number | null) => void;
  onStatsChanged: () => void;
}

function RecentCard({ model, onOpenDetail }: { model: Model; onOpenDetail: () => void }) {
  const isNew = Date.now() - new Date(model.added_at).getTime() < 24 * 3600 * 1000;
  return (
    <div
      className="w-[150px] flex-shrink-0 bg-bp-panel border border-white/10 rounded-sm p-2.5 cursor-pointer hover:border-bp-cyan"
      onClick={onOpenDetail}
    >
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

export default function Dashboard({ stats, lists, onOpenList, onStatsChanged }: DashboardProps) {
  const [detailId, setDetailId] = useState<number | null>(null);

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
          <RecentCard key={m.id} model={m} onOpenDetail={() => setDetailId(m.id)} />
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

      {detailId !== null && (
        <ModelDetailOverlay
          modelId={detailId}
          showingTrash={false}
          lists={lists}
          onClose={() => setDetailId(null)}
          onChanged={onStatsChanged}
        />
      )}
    </div>
  );
}
