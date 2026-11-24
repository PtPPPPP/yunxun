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
  accountId: string | null;
}

export function useTasks({ onError, accountId, onChanged }: UseTasksOptions) {
  const [data, setData] = useState({ accountId, items: [] as FarmTask[], recentDone: [] as FarmTask[] });
  const items = data.accountId === accountId ? data.items : [];
  const recentDone = data.accountId === accountId ? data.recentDone : [];
  const [loading, setLoading] = useState(false);
  const { run: runWrite, busy } = useAsyncGuard();
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
    if (accountId === null) {
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
  }, [refresh, accountId]);

  const refreshAfterWrite = useCallback(async () => {
    await refresh();
    if (isCurrent()) await onChanged?.();
  }, [refresh, isCurrent, onChanged]);

  const create = useCallback(
    async (payload: TaskInput) => {
      let created: FarmTask | undefined;
      await runWrite(async () => {
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
      if (created) await refreshAfterWrite();
      return isCurrent() ? created : undefined;
    },
    [runWrite, onError, refreshAfterWrite, isCurrent],
  );

  const update = useCallback(
    async (taskId: string, payload: TaskInput, done: boolean) => {
      let updated: FarmTask | undefined;
      await runWrite(async () => {
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
      if (updated) await refreshAfterWrite();
      return isCurrent() ? updated : undefined;
    },
    [runWrite, onError, refreshAfterWrite, isCurrent],
  );

  function toggle(task: FarmTask) {
    const { plot_id, title, due_on, notes } = task;
    return update(task.id, { plot_id, title, due_on, notes }, !task.done);
  }

  const remove = useCallback(
    async (taskId: string) => {
      let removed = false;
      await runWrite(async () => {
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
      if (removed) await refreshAfterWrite();
      return isCurrent() && removed;
    },
    [runWrite, onError, refreshAfterWrite, isCurrent],
  );

  return { items, recentDone, loading, busy, refresh, create, update, toggle, remove };
}
