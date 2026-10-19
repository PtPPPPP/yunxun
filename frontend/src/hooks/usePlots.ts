import { useCallback, useEffect, useState } from "react";

import { useAsyncGuard } from "./useAsyncGuard";
import { useAccountGuard } from "./useAccountGuard";
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
  accountId: string | null;
}

export function usePlots({ onError, enabled, accountId }: UsePlotsOptions) {
  const [data, setData] = useState({ accountId, items: [] as Plot[] });
  const items = data.accountId === accountId ? data.items : [];
  const [loading, setLoading] = useState(false);
  const action = useAsyncGuard();
  const isCurrent = useAccountGuard(accountId);

  const refresh = useCallback(async () => {
    if (!isCurrent()) return;
    try {
      const response = await api.get<PlotsResponse>("/api/plots");
      if (!isCurrent()) return;
      setData({ accountId, items: response.data.plots });
      onError("");
    } catch (error) {
      if (isCurrent()) onError(getErrorMessage(error));
    }
  }, [onError, accountId, isCurrent]);

  useEffect(() => {
    if (!enabled) {
      setData({ accountId, items: [] });
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
  }, [enabled, refresh, accountId]);

  const create = useCallback(
    async (payload: PlotInput) => {
      let created: Plot | undefined;
      await action.run(async () => {
        if (!isCurrent()) return;
        try {
          const response = await api.post<PlotResponse>("/api/plots", payload);
          if (!isCurrent()) return;
          created = response.data.plot;
          onError("");
        } catch (error) {
          if (isCurrent()) onError(getErrorMessage(error));
        }
      });
      if (created) await refresh();
      return isCurrent() ? created : undefined;
    },
    [action, onError, refresh, isCurrent],
  );

  const update = useCallback(
    async (plotId: string, payload: PlotInput) => {
      let updated: Plot | undefined;
      await action.run(async () => {
        if (!isCurrent()) return;
        try {
          const response = await api.patch<PlotResponse>(`/api/plots/${plotId}`, payload);
          if (!isCurrent()) return;
          updated = response.data.plot;
          onError("");
        } catch (error) {
          if (isCurrent()) onError(getErrorMessage(error));
        }
      });
      if (updated) await refresh();
      return isCurrent() ? updated : undefined;
    },
    [action, onError, refresh, isCurrent],
  );

  const remove = useCallback(
    async (plotId: string, expectedRevision?: string) => {
      let removedRecords: number | undefined;
      await action.run(async () => {
        if (!isCurrent()) return;
        try {
          const response = await api.delete<DeleteResponse>(`/api/plots/${plotId}`, { params: { expected_revision: expectedRevision } });
          if (!isCurrent()) return;
          removedRecords = response.data.deleted_records;
          onError("");
        } catch (error) {
          if (isCurrent()) onError(getErrorMessage(error));
        }
      });
      if (removedRecords !== undefined) await refresh();
      return isCurrent() ? removedRecords : undefined;
    },
    [action, onError, refresh, isCurrent],
  );

  return { items, loading, busy: action.busy, refresh, create, update, remove };
}
