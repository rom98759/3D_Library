import { useCallback, useEffect, useState } from "react";
import { getLists } from "../api";
import type { ListSummary } from "../types";

export function useLists() {
  const [lists, setLists] = useState<ListSummary[]>([]);

  const refresh = useCallback(() => {
    getLists().then(setLists).catch(() => setLists([]));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { lists, refresh };
}
