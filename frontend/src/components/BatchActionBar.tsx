import { useState } from "react";
import ListPicker from "./ListPicker";
import type { ListSummary } from "../types";

interface BatchActionBarProps {
  count: number;
  lists: ListSummary[];
  showingTrash: boolean;
  onAddToList: (listId: number) => void;
  onListCreated: (list: ListSummary) => void;
  onSetPrinted: () => void;
  onTrash: () => void;
  onRestore: () => void;
  onDeletePermanently: () => void;
  onClear: () => void;
}

export default function BatchActionBar(props: BatchActionBarProps) {
  const [pickerOpen, setPickerOpen] = useState(false);

  if (props.count === 0) return null;

  return (
    <div className="bp-batchbar">
      <span className="text-bp-yellow font-bold pr-2 border-r border-white/10">
        {props.count} sélectionné{props.count > 1 ? "s" : ""}
      </span>

      {!props.showingTrash && (
        <div className="relative">
          <button className="bp-batchbar-btn" onClick={() => setPickerOpen((o) => !o)}>
            + Liste
          </button>
          {pickerOpen && (
            <ListPicker
              lists={props.lists}
              onPick={(id) => {
                props.onAddToList(id);
                setPickerOpen(false);
              }}
              onListCreated={props.onListCreated}
              onClose={() => setPickerOpen(false)}
            />
          )}
        </div>
      )}

      {!props.showingTrash && (
        <button className="bp-batchbar-btn" onClick={props.onSetPrinted}>
          ✓ Imprimé
        </button>
      )}
      {!props.showingTrash && (
        <button className="bp-batchbar-btn" onClick={props.onTrash}>
          🗑 Corbeille
        </button>
      )}
      {props.showingTrash && (
        <button className="bp-batchbar-btn" onClick={props.onRestore}>
          ↺ Restaurer
        </button>
      )}
      <button className="bp-batchbar-btn danger" onClick={props.onDeletePermanently}>
        Supprimer déf.
      </button>
      <button className="bp-batchbar-btn" onClick={props.onClear}>
        Annuler
      </button>
    </div>
  );
}
