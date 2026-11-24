import { FarmRecordKind, FarmTask, PlotSeason } from "../types";
import { todayIso, toIsoDate } from "./date";
import { matchRecordSeason } from "./recordSeason";

export interface LedgerDraft {
  plot_id: string;
  happened_on: string;
  kind: FarmRecordKind;
  detail: string;
  season_id?: string;
}

export function taskLedgerDraft(task: FarmTask, seasons: PlotSeason[]): LedgerDraft {
  const completedAt = task.done_at ? new Date(task.done_at) : null;
  const recordDate = completedAt && Number.isFinite(completedAt.getTime()) ? toIsoDate(completedAt) : todayIso();
  const { season } = matchRecordSeason(seasons, task.plot_id, recordDate);
  return {
    plot_id: task.plot_id ?? "",
    happened_on: recordDate,
    kind: "其他",
    detail: [task.title, task.notes].filter(Boolean).join("；").slice(0, 300),
    ...(season ? { season_id: season.id } : {}),
  };
}
