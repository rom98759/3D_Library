import { useState } from "react";
import { createList } from "../api";
import type { ListSummary } from "../types";

interface ListPickerProps {
  lists: ListSummary[];
  onPick: (listId: number) => void;
  onListCreated: (list: ListSummary) => void;
  onClose: () => void;
}

export default function ListPicker({ lists, onPick, onListCreated, onClose }: ListPickerProps) {
  const [newName, setNewName] = useState("");
  const [error, setError] = useState("");

  async function handleCreate() {
    const name = newName.trim();
    if (!name) return;
    try {
      const created = await createList(name);
      onListCreated(created);
      onPick(created.id);
      setNewName("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur");
    }
  }

  return (
    <div className="absolute bottom-full mb-2 left-0 bg-bp-panel2 border border-bp-cyan rounded-sm p-3 w-56 z-30">
      <div className="font-mono text-[10px] text-bp-ink-dim uppercase mb-2">Ajouter à une liste</div>
      <div className="max-h-40 overflow-y-auto flex flex-col gap-1 mb-2">
        {lists.map((l) => (
          <button
            key={l.id}
            className="text-left font-mono text-xs px-2 py-1 rounded-sm hover:bg-bp-panel"
            onClick={() => {
              onPick(l.id);
              onClose();
            }}
          >
            {l.name}
          </button>
        ))}
      </div>
      <div className="flex gap-1.5">
        <input
          className="flex-1 bg-bp-deep border border-white/10 rounded-sm px-2 py-1 text-xs font-mono text-bp-ink outline-none"
          placeholder="Nouvelle liste…"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleCreate()}
        />
        <button className="bp-btn" onClick={handleCreate}>
          +
        </button>
      </div>
      {error && <div className="text-bp-red text-[10px] font-mono mt-1">{error}</div>}
    </div>
  );
}
