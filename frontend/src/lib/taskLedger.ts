import { FarmRecordKind, FarmTask, PlotSeason } from "../types";
import { todayIso } from "./date";

export interface LedgerDraft {
  plot_id: string;
  happened_on: string;
  kind: FarmRecordKind;
  detail: string;
  season_id?: string;
}

export function taskLedgerDraft(task: FarmTask, seasons: PlotSeason[]): LedgerDraft {
  const completed = task.done_at ? new Date(task.done_at) : null;
  const happened_on = completed && Number.isFinite(completed.getTime())
    ? `${completed.getFullYear()}-${String(completed.getMonth() + 1).padStart(2, "0")}-${String(completed.getDate()).padStart(2, "0")}`
    : todayIso();
  const candidates = seasons.filter((season) => season.plot_id === task.plot_id
    && (!season.started_on || season.started_on <= happened_on)
    && (!season.ended_on || happened_on <= season.ended_on));
  const season = candidates.length === 1 && candidates[0].started_on ? candidates[0] : undefined;
  return {
    plot_id: task.plot_id ?? "", happened_on, kind: "其他",
    detail: [task.title, task.notes].filter(Boolean).join("；").slice(0, 300),
    ...(season ? { season_id: season.id } : {}),
  };
}
