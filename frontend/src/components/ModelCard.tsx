import { dimSvg } from "../lib/dimSvg";
import type { Model } from "../types";

interface ModelCardProps {
  model: Model;
  selected: boolean;
  onToggleSelect: (shiftKey: boolean) => void;
  onTogglePrinted: () => void;
  onOpenDetail: () => void;
}

export default function ModelCard({ model, selected, onToggleSelect, onTogglePrinted, onOpenDetail }: ModelCardProps) {
  return (
    <div className={`bp-card cursor-pointer ${selected ? "selected" : ""}`} onClick={onOpenDetail}>
      <div
        className="bp-checkbox"
        onClick={(e) => {
          e.stopPropagation();
          onToggleSelect(e.shiftKey);
        }}
      >
        {selected ? "✓" : ""}
      </div>
      <div
        className={`bp-printed-badge ${model.printed === 1 ? "" : "off"}`}
        title="Inverser le statut imprimé"
        onClick={(e) => {
          e.stopPropagation();
          onTogglePrinted();
        }}
      >
        {model.printed === 1 ? "✓ imprimé" : "à imprimer"}
      </div>
      <div className="bp-thumb">
        {model.thumbnail_path ? (
          <img src={`/api/models/${model.id}/thumbnail`} alt={model.name} loading="lazy" />
        ) : (
          <div
            className="w-full h-full"
            dangerouslySetInnerHTML={{ __html: dimSvg(model.size_x, model.size_y, model.size_z) }}
          />
        )}
      </div>
      <div className="bp-name">{model.name}</div>
      {model.lists.length > 0 && (
        <div className="flex gap-1.5 flex-wrap mb-2">
          {model.lists.map((l) => (
            <span key={l.id} className="bp-pill">
              {l.name}
            </span>
          ))}
        </div>
      )}
      <div className="bp-meta">
        <span>{model.estimated_weight_g != null ? `${model.estimated_weight_g} g` : "—"}</span>
        <span>{new Date(model.added_at).toLocaleDateString("fr-FR")}</span>
      </div>
      {model.purge_at && (
        <div className="font-mono text-[10px] text-bp-red mt-1.5">
          Purge prévue le {new Date(model.purge_at).toLocaleDateString("fr-FR")}
        </div>
      )}
    </div>
  );
}
