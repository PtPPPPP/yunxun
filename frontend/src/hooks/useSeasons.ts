import { useCallback, useEffect, useState } from "react";

import { useAsyncGuard } from "./useAsyncGuard";
import { api, getErrorMessage } from "../lib/api";
import { PlotSeason } from "../types";

export interface SeasonInput {
  plot_id: string;
  crop: string;
  started_on: string | null;
  notes: string;
}

export interface SeasonUpdateInput {
  crop: string;
  started_on: string | null;
  ended_on: string | null;
  notes: string;
}

interface SeasonsResponse {
  success: true;
  seasons: PlotSeason[];
}

interface SeasonResponse {
  success: true;
  season: PlotSeason;
}

interface UseSeasonsOptions {
  onError: (message: string) => void;
  /** 未登录时不拉取，避免登录页弹出 401 错误横幅。 */
  enabled: boolean;
  /** 茬次变化会改动地块上的当前作物与本季计数，通知外层顺手刷新地块。 */
  onChanged: () => void;
}

export function useSeasons({ onError, enabled, onChanged }: UseSeasonsOptions) {
  const [items, setItems] = useState<PlotSeason[]>([]);
  const [loading, setLoading] = useState(false);
  const action = useAsyncGuard();

  const refresh = useCallback(async () => {
    try {
      const response = await api.get<SeasonsResponse>("/api/seasons");
      setItems(response.data.seasons);
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
    async (payload: SeasonInput) => {
      let created: PlotSeason | undefined;
      await action.run(async () => {
        try {
          const response = await api.post<SeasonResponse>("/api/seasons", payload);
          created = response.data.season;
          onError("");
        } catch (error) {
          onError(getErrorMessage(error));
        }
      });
      if (created) {
        await refresh();
        onChanged();
      }
      return created;
    },
    [action, onChanged, onError, refresh],
  );

  const update = useCallback(
    async (seasonId: string, payload: SeasonUpdateInput) => {
      let updated: PlotSeason | undefined;
      await action.run(async () => {
        try {
          const response = await api.patch<SeasonResponse>(`/api/seasons/${seasonId}`, payload);
          updated = response.data.season;
          onError("");
        } catch (error) {
          onError(getErrorMessage(error));
        }
      });
      if (updated) {
        await refresh();
        onChanged();
      }
      return updated;
    },
    [action, onChanged, onError, refresh],
  );

  const remove = useCallback(
    async (seasonId: string) => {
      let removed = false;
      await action.run(async () => {
        try {
          await api.delete(`/api/seasons/${seasonId}`);
          removed = true;
          onError("");
        } catch (error) {
          onError(getErrorMessage(error));
        }
      });
      if (removed) {
        await refresh();
        onChanged();
      }
      return removed;
    },
    [action, onChanged, onError, refresh],
  );

  return { items, loading, busy: action.busy, refresh, create, update, remove };
}
