import { dimSvg } from "../lib/dimSvg";
import type { Model } from "../types";

interface ModelCardProps {
  model: Model;
  selected: boolean;
  onToggleSelect: () => void;
  onOpenDetail: () => void;
}

export default function ModelCard({ model, selected, onToggleSelect, onOpenDetail }: ModelCardProps) {
  return (
    <div className={`bp-card cursor-pointer ${selected ? "selected" : ""}`} onClick={onOpenDetail}>
      <div
        className="bp-checkbox"
        onClick={(e) => {
          e.stopPropagation();
          onToggleSelect();
        }}
      >
        {selected ? "✓" : ""}
      </div>
      {model.printed === 1 && <div className="bp-printed-badge">✓ imprimé</div>}
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
    </div>
  );
}
