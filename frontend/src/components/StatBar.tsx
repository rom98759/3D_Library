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
