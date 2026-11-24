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
  accountId: string | null;
}

export function usePlots({ onError, accountId }: UsePlotsOptions) {
  const [data, setData] = useState({ accountId, items: [] as Plot[] });
  const items = data.accountId === accountId ? data.items : [];
  const [loading, setLoading] = useState(false);
  const { run: runWrite, busy } = useAsyncGuard();
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
    if (accountId === null) {
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
  }, [refresh, accountId]);

  const create = useCallback(
    async (payload: PlotInput) => {
      let created: Plot | undefined;
      await runWrite(async () => {
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
    [runWrite, onError, refresh, isCurrent],
  );

  const update = useCallback(
    async (plotId: string, payload: PlotInput) => {
      let updated: Plot | undefined;
      await runWrite(async () => {
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
    [runWrite, onError, refresh, isCurrent],
  );

  const remove = useCallback(
    async (plotId: string, expectedRevision?: string) => {
      let removedRecords: number | undefined;
      await runWrite(async () => {
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
    [runWrite, onError, refresh, isCurrent],
  );

  return { items, loading, busy, refresh, create, update, remove };
}
