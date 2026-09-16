import { useCallback, useEffect, useState } from "react";

import { useAsyncGuard } from "./useAsyncGuard";
import { api, getErrorMessage } from "../lib/api";
import { Plot } from "../types";

export interface PlotInput {
  name: string;
  area_mu: number;
  soil_type: string;
  irrigation: string;
  crop: string;
  planted_on: string | null;
  notes: string;
}

interface PlotsResponse {
  success: true;
  plots: Plot[];
}

interface PlotResponse {
  success: true;
  plot: Plot;
}

interface DeleteResponse {
  success: true;
  message: string;
  deleted_records: number;
}

interface UsePlotsOptions {
  onError: (message: string) => void;
  /** 未登录时不拉取，避免登录页弹出 401 错误横幅。 */
  enabled: boolean;
}

export function usePlots({ onError, enabled }: UsePlotsOptions) {
  const [items, setItems] = useState<Plot[]>([]);
  const [loading, setLoading] = useState(false);
  const action = useAsyncGuard();

  const refresh = useCallback(async () => {
    try {
      const response = await api.get<PlotsResponse>("/api/plots");
      setItems(response.data.plots);
      onError("");
    } catch (error) {
      onError(getErrorMessage(error));
    }
  }, [onError]);

  useEffect(() => {
    if (!enabled) {
      setItems([]);
      return;
    }
    let cancelled = false;
    setLoading(true);
    void refresh().finally(() => {
      if (!cancelled) setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [enabled, refresh]);

  const create = useCallback(
    async (payload: PlotInput) => {
      let created: Plot | undefined;
      await action.run(async () => {
        try {
          const response = await api.post<PlotResponse>("/api/plots", payload);
          created = response.data.plot;
          onError("");
        } catch (error) {
          onError(getErrorMessage(error));
        }
      });
      if (created) await refresh();
      return created;
    },
    [action, onError, refresh],
  );

  const update = useCallback(
    async (plotId: string, payload: PlotInput) => {
      let updated: Plot | undefined;
      await action.run(async () => {
        try {
          const response = await api.patch<PlotResponse>(`/api/plots/${plotId}`, payload);
          updated = response.data.plot;
          onError("");
        } catch (error) {
          onError(getErrorMessage(error));
        }
      });
      if (updated) await refresh();
      return updated;
    },
    [action, onError, refresh],
  );

  const remove = useCallback(
    async (plotId: string) => {
      let removedRecords: number | undefined;
      await action.run(async () => {
        try {
          const response = await api.delete<DeleteResponse>(`/api/plots/${plotId}`);
          removedRecords = response.data.deleted_records;
          onError("");
        } catch (error) {
          onError(getErrorMessage(error));
        }
      });
      if (removedRecords !== undefined) await refresh();
      return removedRecords;
    },
    [action, onError, refresh],
  );

  return { items, loading, busy: action.busy, refresh, create, update, remove };
}
