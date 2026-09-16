import { useCallback, useEffect, useState } from "react";

import { useAsyncGuard } from "./useAsyncGuard";
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
  /** 未登录时不拉取，避免登录页弹出 401 错误横幅。 */
  enabled: boolean;
}

export function useTasks({ onError, enabled }: UseTasksOptions) {
  const [items, setItems] = useState<FarmTask[]>([]);
  const [recentDone, setRecentDone] = useState<FarmTask[]>([]);
  const [loading, setLoading] = useState(false);
  const action = useAsyncGuard();

  const refresh = useCallback(async () => {
    try {
      const response = await api.get<TasksResponse>("/api/farm-tasks");
      setItems(response.data.tasks);
      setRecentDone(response.data.recent_done);
      onError("");
    } catch (error) {
      onError(getErrorMessage(error));
    }
  }, [onError]);

  useEffect(() => {
    if (!enabled) {
      setItems([]);
      setRecentDone([]);
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
    async (payload: TaskInput) => {
      let created: FarmTask | undefined;
      await action.run(async () => {
        try {
          const response = await api.post<TaskResponse>("/api/farm-tasks", payload);
          created = response.data.task;
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
    async (taskId: string, payload: TaskInput, done: boolean) => {
      let updated: FarmTask | undefined;
      await action.run(async () => {
        try {
          const response = await api.patch<TaskResponse>(`/api/farm-tasks/${taskId}`, { ...payload, done });
          updated = response.data.task;
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

  const toggle = useCallback(
    async (task: FarmTask) => {
      let updated: FarmTask | undefined;
      await action.run(async () => {
        try {
          const response = await api.patch<TaskResponse>(`/api/farm-tasks/${task.id}`, {
            plot_id: task.plot_id,
            title: task.title,
            due_on: task.due_on,
            notes: task.notes,
            done: !task.done,
          });
          updated = response.data.task;
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
    async (taskId: string) => {
      let removed = false;
      await action.run(async () => {
        try {
          await api.delete(`/api/farm-tasks/${taskId}`);
          removed = true;
          onError("");
        } catch (error) {
          onError(getErrorMessage(error));
        }
      });
      if (removed) await refresh();
      return removed;
    },
    [action, onError, refresh],
  );

  return { items, recentDone, loading, busy: action.busy, refresh, create, update, toggle, remove };
}
