import { useCallback, useEffect, useState } from "react";

import { useAsyncGuard } from "./useAsyncGuard";
import { useAccountGuard } from "./useAccountGuard";
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
  accountId: string | null;
  /** 茬次变化会改动地块上的当前作物与本季计数，通知外层顺手刷新地块。 */
  onChanged: () => void;
}

export function useSeasons({ onError, enabled, accountId, onChanged }: UseSeasonsOptions) {
  const [data, setData] = useState({ accountId, items: [] as PlotSeason[] });
  const items = data.accountId === accountId ? data.items : [];
  const [loading, setLoading] = useState(false);
  const action = useAsyncGuard();
  const isCurrent = useAccountGuard(accountId);

  const refresh = useCallback(async () => {
    if (!isCurrent()) return;
    try {
      const response = await api.get<SeasonsResponse>("/api/seasons");
      if (!isCurrent()) return;
      setData({ accountId, items: response.data.seasons });
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
    async (payload: SeasonInput) => {
      let created: PlotSeason | undefined;
      await action.run(async () => {
        if (!isCurrent()) return;
        try {
          const response = await api.post<SeasonResponse>("/api/seasons", payload);
          if (!isCurrent()) return;
          created = response.data.season;
          onError("");
        } catch (error) {
          if (isCurrent()) onError(getErrorMessage(error));
        }
      });
      if (created) {
        await refresh();
        if (isCurrent()) onChanged();
      }
      return isCurrent() ? created : undefined;
    },
    [action, onChanged, onError, refresh, isCurrent],
  );

  const update = useCallback(
    async (seasonId: string, payload: SeasonUpdateInput) => {
      let updated: PlotSeason | undefined;
      await action.run(async () => {
        if (!isCurrent()) return;
        try {
          const response = await api.patch<SeasonResponse>(`/api/seasons/${seasonId}`, payload);
          if (!isCurrent()) return;
          updated = response.data.season;
          onError("");
        } catch (error) {
          if (isCurrent()) onError(getErrorMessage(error));
        }
      });
      if (updated) {
        await refresh();
        if (isCurrent()) onChanged();
      }
      return isCurrent() ? updated : undefined;
    },
    [action, onChanged, onError, refresh, isCurrent],
  );

  const remove = useCallback(
    async (seasonId: string) => {
      let removed = false;
      await action.run(async () => {
        if (!isCurrent()) return;
        try {
          await api.delete(`/api/seasons/${seasonId}`);
          if (!isCurrent()) return;
          removed = true;
          onError("");
        } catch (error) {
          if (isCurrent()) onError(getErrorMessage(error));
        }
      });
      if (removed) {
        await refresh();
        if (isCurrent()) onChanged();
      }
      return isCurrent() && removed;
    },
    [action, onChanged, onError, refresh, isCurrent],
  );

  return { items, loading, busy: action.busy, refresh, create, update, remove };
}
