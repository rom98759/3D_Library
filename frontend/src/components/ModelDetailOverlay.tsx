import { useEffect, useState } from "react";
import {
  deleteModelPermanently,
  getModel,
  openFolder,
  openOrcaSlicer,
  restoreModel,
  setModelLists,
  trashModel,
  updateModel,
} from "../api";
import { dimSvg } from "../lib/dimSvg";
import type { ListSummary, Model } from "../types";
import Viewer3D from "./Viewer3D";

interface ModelDetailOverlayProps {
  modelId: number;
  showingTrash: boolean;
  lists: ListSummary[];
  onClose: () => void;
  onChanged: () => void;
}

function fmt(v: number | null | undefined, unit = ""): string {
  return v === null || v === undefined ? "—" : `${v}${unit}`;
}

export default function ModelDetailOverlay({
  modelId,
  showingTrash,
  lists,
  onClose,
  onChanged,
}: ModelDetailOverlayProps) {
  const [model, setModel] = useState<Model | null>(null);
  const [editing, setEditing] = useState(false);
  const [show3D, setShow3D] = useState(false);
  const [message, setMessage] = useState<{ text: string; kind: "ok" | "error" } | null>(null);

  const [form, setForm] = useState({ name: "", material: "", tags: "", printed: false, listIds: [] as number[] });

  useEffect(() => {
    getModel(modelId).then((m) => {
      setModel(m);
      setForm({
        name: m.name,
        material: m.material ?? "",
        tags: m.tags ?? "",
        printed: m.printed === 1,
        listIds: m.lists.map((l) => l.id),
      });
    });
  }, [modelId]);

  async function handleAction(fn: () => Promise<unknown>, okText: string) {
    try {
      await fn();
      setMessage({ text: okText, kind: "ok" });
      onChanged();
    } catch (e) {
      setMessage({ text: e instanceof Error ? e.message : "Erreur", kind: "error" });
    }
  }

  async function handleSave() {
    if (!model) return;
    try {
      await updateModel(model.id, {
        name: form.name,
        material: form.material,
        tags: form.tags,
        printed: form.printed,
      });
      await setModelLists(model.id, form.listIds);
      setMessage({ text: "Modifications sauvegardées", kind: "ok" });
      onChanged();
      const refreshed = await getModel(model.id);
      setModel(refreshed);
    } catch (e) {
      setMessage({ text: e instanceof Error ? e.message : "Erreur sauvegarde", kind: "error" });
    }
  }

  if (!model) return null;

  function toggleListId(id: number) {
    setForm((f) => ({
      ...f,
      listIds: f.listIds.includes(id) ? f.listIds.filter((x) => x !== id) : [...f.listIds, id],
    }));
  }

  return (
    <div className="bp-detail-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="bp-detail max-h-[90vh] overflow-y-auto">
        <h2 className="font-display uppercase text-xl m-0 mb-1">{model.name}</h2>
        <div className="font-mono text-[11px] text-bp-ink-dim break-all mb-4">{model.path}</div>

        <div className="bp-thumb h-[180px] my-3.5">
          {show3D ? (
            <Viewer3D modelId={model.id} />
          ) : model.thumbnail_path ? (
            <img src={`/api/models/${model.id}/thumbnail`} alt={model.name} />
          ) : (
            <div className="w-full" dangerouslySetInnerHTML={{ __html: dimSvg(model.size_x, model.size_y, model.size_z) }} />
          )}
        </div>
        {!show3D && (
          <button className="bp-btn w-full mb-2.5" onClick={() => setShow3D(true)}>
            Vue 3D interactive
          </button>
        )}

        <dl className="grid grid-cols-[auto_1fr] gap-2 gap-x-4 font-mono text-xs">
          <dt className="text-bp-ink-dim uppercase">Dimensions</dt>
          <dd className="m-0">{fmt(model.size_x)} × {fmt(model.size_y)} × {fmt(model.size_z)} mm</dd>
          <dt className="text-bp-ink-dim uppercase">Volume</dt>
          <dd className="m-0">{fmt(model.volume, " cm³")}</dd>
          <dt className="text-bp-ink-dim uppercase">Matériau</dt>
          <dd className="m-0">{model.material || "—"}</dd>
          <dt className="text-bp-ink-dim uppercase">Poids estimé</dt>
          <dd className="m-0">{fmt(model.estimated_weight_g, " g")}</dd>
          <dt className="text-bp-ink-dim uppercase">Temps estimé</dt>
          <dd className="m-0">{fmt(model.estimated_print_time_h, " h")}</dd>
          <dt className="text-bp-ink-dim uppercase">Mesh fermé</dt>
          <dd className="m-0">{model.is_watertight ? "oui" : "non (estimation approx.)"}</dd>
          <dt className="text-bp-ink-dim uppercase">Tags</dt>
          <dd className="m-0">{model.tags || "—"}</dd>
          <dt className="text-bp-ink-dim uppercase">Ajouté le</dt>
          <dd className="m-0">{model.added_at.split("T")[0]}</dd>
        </dl>

        {editing && (
          <div className="mt-5 flex flex-col gap-2.5">
            <label className="font-mono text-[11px] text-bp-ink-dim">
              Nom
              <input
                className="w-full bg-bp-deep border border-white/10 text-bp-ink p-2 font-mono mt-1"
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              />
            </label>
            <label className="font-mono text-[11px] text-bp-ink-dim">
              Matériau
              <input
                className="w-full bg-bp-deep border border-white/10 text-bp-ink p-2 font-mono mt-1"
                value={form.material}
                onChange={(e) => setForm((f) => ({ ...f, material: e.target.value }))}
              />
            </label>
            <label className="font-mono text-[11px] text-bp-ink-dim">
              Tags
              <input
                className="w-full bg-bp-deep border border-white/10 text-bp-ink p-2 font-mono mt-1"
                value={form.tags}
                onChange={(e) => setForm((f) => ({ ...f, tags: e.target.value }))}
              />
            </label>

            <div className="font-mono text-[11px] text-bp-ink-dim mt-1">Listes</div>
            <div className="flex gap-1.5 flex-wrap">
              {lists.map((l) => (
                <span
                  key={l.id}
                  className={`bp-pill cursor-pointer ${form.listIds.includes(l.id) ? "" : "opacity-40"}`}
                  onClick={() => toggleListId(l.id)}
                >
                  {l.name}
                </span>
              ))}
            </div>

            <label className="flex items-center gap-2 font-mono text-[11px] text-bp-ink-dim mt-1">
              <input
                type="checkbox"
                checked={form.printed}
                onChange={(e) => setForm((f) => ({ ...f, printed: e.target.checked }))}
              />
              Imprimé
            </label>

            <button className="bp-btn primary" onClick={handleSave}>
              Sauvegarder
            </button>
          </div>
        )}

        {!editing && model.lists.length > 0 && (
          <div className="flex gap-1.5 flex-wrap mt-4">
            {model.lists.map((l) => (
              <span key={l.id} className="bp-pill">
                {l.name}
              </span>
            ))}
          </div>
        )}

        <div className="flex gap-2.5 mt-4 flex-wrap">
          {!showingTrash && (
            <>
              <button className="bp-btn primary" onClick={() => handleAction(() => openOrcaSlicer(model.id), "Ouvert dans OrcaSlicer")}>
                Ouvrir dans OrcaSlicer
              </button>
              <button className="bp-btn" onClick={() => handleAction(async () => setMessage({ text: `Dossier ouvert : ${(await openFolder(model.id)).folder}`, kind: "ok" }), "")}>
                Ouvrir le dossier
              </button>
              <button className="bp-btn" onClick={() => setEditing((e) => !e)}>
                Modifier
              </button>
              <button className="bp-btn" onClick={() => handleAction(() => trashModel(model.id), "Mis à la corbeille").then(onClose)}>
                Mettre à la corbeille
              </button>
            </>
          )}
          {showingTrash && (
            <button className="bp-btn primary" onClick={() => handleAction(() => restoreModel(model.id), "Restauré").then(onClose)}>
              Restaurer
            </button>
          )}
          <button
            className="bp-btn"
            style={{ borderColor: "#E2725B", color: "#E2725B" }}
            onClick={() => handleAction(() => deleteModelPermanently(model.id), "Supprimé définitivement").then(onClose)}
          >
            Supprimer définitivement
          </button>
          <button className="bp-btn" onClick={onClose}>
            Fermer
          </button>
        </div>

        {message && (
          <div className={`font-mono text-[11px] mt-2.5 ${message.kind === "error" ? "text-bp-red" : "text-bp-green"}`}>
            {message.text}
          </div>
        )}
      </div>
    </div>
  );
}
