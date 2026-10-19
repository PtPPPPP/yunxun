import { describe, expect, it } from "vitest";
import { taskLedgerDraft } from "./taskLedger";
import { FarmTask, PlotSeason } from "../types";

const task: FarmTask = { id: "task", plot_id: "plot", plot_name: "东田", title: "追肥复查", due_on: "2025-04-01", done: true, done_at: "2026-10-19T12:00:00Z", notes: "记录长势", created_at: "" };
const season: PlotSeason = { id: "season", plot_id: "plot", crop: "玉米", started_on: "2026-10-01", ended_on: null, active: true, notes: "", created_at: "", updated_at: "" };

describe("待办记账草稿", () => {
  it("使用实际完成日而非计划日，不猜测实际作业类型和费用", () => {
    const draft = taskLedgerDraft(task, [season]);
    expect(draft.happened_on).toBe("2026-10-19");
    expect(draft.season_id).toBe("season");
    expect(draft.kind).toBe("其他");
    expect(draft.detail).toBe("追肥复查；记录长势");
    expect(draft).not.toHaveProperty("cost");
  });
  it("只带入日期唯一匹配且起始日明确的本人所选地块茬次", () => {
    expect(taskLedgerDraft(task, [season, { ...season, id: "overlap" }]).season_id).toBeUndefined();
    expect(taskLedgerDraft(task, [{ ...season, started_on: null }]).season_id).toBeUndefined();
    expect(taskLedgerDraft(task, [{ ...season, plot_id: "another" }]).season_id).toBeUndefined();
    expect(taskLedgerDraft(task, [{ ...season, ended_on: "2026-10-18" }]).season_id).toBeUndefined();
  });
  it("杂事不默认选择地块，长备注遵循台账字段长度", () => {
    const draft = taskLedgerDraft({ ...task, plot_id: null, notes: "长".repeat(1000) }, [season]);
    expect(draft.plot_id).toBe("");
    expect(draft.season_id).toBeUndefined();
    expect(draft.detail.length).toBe(300);
  });
  it("历史完成日匹配历史茬次，不取当前进行中茬次", () => {
    const old = { ...season, id: "old", started_on: "2026-04-01", ended_on: "2026-05-31", active: false };
    const draft = taskLedgerDraft({ ...task, done_at: "2026-04-30T12:00:00Z" }, [season, old]);
    expect(draft.season_id).toBe("old");
    expect(draft.happened_on).toBe("2026-04-30");
  });
});
