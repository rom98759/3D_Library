import { useCallback, useEffect, useRef, useState } from "react";
import { getModels, getTrash } from "../api";
import type { Model, ModelListParams } from "../types";

export function useModels(params: ModelListParams, showingTrash: boolean) {
  const [models, setModels] = useState<Model[]>([]);
  const [loading, setLoading] = useState(true);
  const requestIdRef = useRef(0);

  const refresh = useCallback(() => {
    const requestId = ++requestIdRef.current;
    setLoading(true);
    const promise = showingTrash ? getTrash() : getModels(params);
    promise
      .then((result) => {
        // Ignore une réponse arrivée après une requête plus récente (ex. deux
        // frappes rapides dans la recherche) — sinon un résultat obsolète
        // pourrait écraser un résultat plus récent déjà affiché.
        if (requestIdRef.current === requestId) setModels(result);
      })
      .catch(() => {
        if (requestIdRef.current === requestId) setModels([]);
      })
      .finally(() => {
        if (requestIdRef.current === requestId) setLoading(false);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showingTrash, JSON.stringify(params)]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { models, loading, refresh };
}
