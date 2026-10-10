import { dimSvg } from "../lib/dimSvg";
import type { Model } from "../types";

interface ModelRowProps {
  model: Model;
  selected: boolean;
  onToggleSelect: (shiftKey: boolean) => void;
  onTogglePrinted: () => void;
  onOpenDetail: () => void;
}

export default function ModelRow({ model, selected, onToggleSelect, onTogglePrinted, onOpenDetail }: ModelRowProps) {
  return (
    <div
      className={`grid grid-cols-[32px_48px_2fr_1.4fr_90px_90px_90px_70px] items-center gap-2.5 px-3 py-2 border-t border-white/5 bg-bp-panel text-xs cursor-pointer ${selected ? "ring-1 ring-bp-yellow" : ""}`}
      onClick={onOpenDetail}
    >
      <div
        className="bp-checkbox relative top-0 left-0"
        onClick={(e) => {
          e.stopPropagation();
          onToggleSelect(e.shiftKey);
        }}
      >
        {selected ? "✓" : ""}
      </div>
      <div className="w-10 h-[30px] bg-bp-deep border border-white/5 overflow-hidden">
        {model.thumbnail_path ? (
          <img src={`/api/models/${model.id}/thumbnail`} alt="" className="w-full h-full object-contain" />
        ) : (
          <div
            className="w-full h-full [&_svg]:w-full [&_svg]:h-full"
            dangerouslySetInnerHTML={{ __html: dimSvg(model.size_x, model.size_y, model.size_z) }}
          />
        )}
      </div>
      <div className="font-display text-[13px] uppercase">{model.name}</div>
      <div className="flex gap-1 flex-wrap">
        {model.lists.map((l) => (
          <span key={l.id} className="bp-pill">
            {l.name}
          </span>
        ))}
      </div>
      <div className="font-mono text-[11px] text-bp-ink-dim">
        {model.estimated_weight_g != null ? `${model.estimated_weight_g} g` : "—"}
      </div>
      <div className="font-mono text-[11px] text-bp-ink-dim">
        {model.volume != null ? `${model.volume} cm³` : "—"}
      </div>
      <div className={`font-mono text-[11px] ${model.purge_at ? "text-bp-red" : "text-bp-ink-dim"}`}>
        {model.purge_at
          ? `Purge le ${new Date(model.purge_at).toLocaleDateString("fr-FR")}`
          : new Date(model.added_at).toLocaleDateString("fr-FR")}
      </div>
      <div
        className={`cursor-pointer ${model.printed === 1 ? "text-bp-green" : "text-bp-ink-dim"}`}
        title="Inverser le statut imprimé"
        onClick={(e) => {
          e.stopPropagation();
          onTogglePrinted();
        }}
      >
        {model.printed === 1 ? "✓" : "—"}
      </div>
    </div>
  );
}
