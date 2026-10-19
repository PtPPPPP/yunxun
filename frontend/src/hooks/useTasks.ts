import { useCallback, useEffect, useState } from "react";

import { useAsyncGuard } from "./useAsyncGuard";
import { useAccountGuard } from "./useAccountGuard";
import { api, getErrorMessage } from "../lib/api";
import { FarmTask } from "../types";

export interface TaskInput {
  plot_id: string | null;
  title: string;
  due_on: string;
  notes: string;
}

interface TasksResponse {
  success: true;
  tasks: FarmTask[];
  recent_done: FarmTask[];
}

interface TaskResponse {
  success: true;
  task: FarmTask;
}

interface UseTasksOptions {
  onError: (message: string) => void;
  onChanged?: () => Promise<void>;
  /** 未登录时不拉取，避免登录页弹出 401 错误横幅。 */
  enabled: boolean;
  accountId: string | null;
}

export function useTasks({ onError, enabled, accountId, onChanged }: UseTasksOptions) {
  const [data, setData] = useState({ accountId, items: [] as FarmTask[], recentDone: [] as FarmTask[] });
  const items = data.accountId === accountId ? data.items : [];
  const recentDone = data.accountId === accountId ? data.recentDone : [];
  const [loading, setLoading] = useState(false);
  const action = useAsyncGuard();
  const isCurrent = useAccountGuard(accountId);

  const refresh = useCallback(async () => {
    if (!isCurrent()) return;
    try {
      const response = await api.get<TasksResponse>("/api/farm-tasks");
      if (!isCurrent()) return;
      setData({ accountId, items: response.data.tasks, recentDone: response.data.recent_done });
      onError("");
    } catch (error) {
      if (isCurrent()) onError(getErrorMessage(error));
    }
  }, [onError, accountId, isCurrent]);

  useEffect(() => {
    if (!enabled) {
      setData({ accountId, items: [], recentDone: [] });
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
    async (payload: TaskInput) => {
      let created: FarmTask | undefined;
      await action.run(async () => {
        if (!isCurrent()) return;
        try {
          const response = await api.post<TaskResponse>("/api/farm-tasks", payload);
          if (!isCurrent()) return;
          created = response.data.task;
          onError("");
        } catch (error) {
          if (isCurrent()) onError(getErrorMessage(error));
        }
      });
      if (created) { await refresh(); if (isCurrent()) await onChanged?.(); }
      return isCurrent() ? created : undefined;
    },
    [action, onError, refresh, onChanged, isCurrent],
  );

  const update = useCallback(
    async (taskId: string, payload: TaskInput, done: boolean) => {
      let updated: FarmTask | undefined;
      await action.run(async () => {
        if (!isCurrent()) return;
        try {
          const response = await api.patch<TaskResponse>(`/api/farm-tasks/${taskId}`, { ...payload, done });
          if (!isCurrent()) return;
          updated = response.data.task;
          onError("");
        } catch (error) {
          if (isCurrent()) onError(getErrorMessage(error));
        }
      });
      if (updated) { await refresh(); if (isCurrent()) await onChanged?.(); }
      return isCurrent() ? updated : undefined;
    },
    [action, onError, refresh, onChanged, isCurrent],
  );

  const toggle = useCallback(
    async (task: FarmTask) => {
      let updated: FarmTask | undefined;
      await action.run(async () => {
        if (!isCurrent()) return;
        try {
          const response = await api.patch<TaskResponse>(`/api/farm-tasks/${task.id}`, {
            plot_id: task.plot_id,
            title: task.title,
            due_on: task.due_on,
            notes: task.notes,
            done: !task.done,
          });
          if (!isCurrent()) return;
          updated = response.data.task;
          onError("");
        } catch (error) {
          if (isCurrent()) onError(getErrorMessage(error));
        }
      });
      if (updated) { await refresh(); if (isCurrent()) await onChanged?.(); }
      return isCurrent() ? updated : undefined;
    },
    [action, onError, refresh, onChanged, isCurrent],
  );

  const remove = useCallback(
    async (taskId: string) => {
      let removed = false;
      await action.run(async () => {
        if (!isCurrent()) return;
        try {
          await api.delete(`/api/farm-tasks/${taskId}`);
          if (!isCurrent()) return;
          removed = true;
          onError("");
        } catch (error) {
          if (isCurrent()) onError(getErrorMessage(error));
        }
      });
      if (removed) { await refresh(); if (isCurrent()) await onChanged?.(); }
      return isCurrent() && removed;
    },
    [action, onError, refresh, onChanged, isCurrent],
  );

  return { items, recentDone, loading, busy: action.busy, refresh, create, update, toggle, remove };
}
