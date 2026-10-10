import { useCallback, useEffect, useState } from "react";
import { getModels, getTrash } from "../api";
import type { Model, ModelListParams } from "../types";

export function useModels(params: ModelListParams, showingTrash: boolean) {
  const [models, setModels] = useState<Model[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(() => {
    setLoading(true);
    const promise = showingTrash ? getTrash() : getModels(params);
    promise
      .then(setModels)
      .catch(() => setModels([]))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showingTrash, JSON.stringify(params)]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { models, loading, refresh };
}
