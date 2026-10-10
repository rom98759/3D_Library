import { useCallback, useEffect, useState } from "react";
import { getStats } from "../api";
import type { Stats } from "../types";

export function useStats() {
  const [stats, setStats] = useState<Stats | null>(null);

  const refresh = useCallback(() => {
    getStats().then(setStats).catch(() => setStats(null));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { stats, refresh };
}
