import { CalendarPlus } from "lucide-react";
import { forwardRef, useImperativeHandle, useState } from "react";

import { TaskInput } from "../hooks/useTasks";
import { useAsyncGuard } from "../hooks/useAsyncGuard";
import { useSessionGuard } from "../hooks/useSessionBoundary";
import { useRequestLeave, useUnsavedChanges } from "../hooks/useUnsavedChanges";
import { api, getErrorMessage } from "../lib/api";
import { addDays, formatDate, todayIso } from "../lib/date";
import { LedgerDraft } from "../lib/taskLedger";
import { newSubmissionId } from "../lib/submission";
import { FarmRecord, FarmRecordKind, Plot, PlotSeason } from "../types";
import { RecordSeasonField } from "./RecordSeasonField";

export const recordKinds: FarmRecordKind[] = ["播种", "施肥", "打药", "灌溉", "除草", "采收", "其他"];

const followUps: Partial<Record<FarmRecordKind, { days: number; label: string }>> = {
  播种: { days: 7, label: "查苗情与出苗率" },
  施肥: { days: 7, label: "复查追肥后长势" },
  打药: { days: 3, label: "复查防效" },
  灌溉: { days: 2, label: "查看墒情与积水" },
  除草: { days: 10, label: "复查杂草复发" },
};

export interface FarmRecordFormHandle {
  edit: (record: FarmRecord) => void;
  discardDeletedRecord: (recordId: string) => void;
}

interface FarmRecordFormProps {
  plots: Plot[];
  seasons: PlotSeason[];
  initialDraft?: LedgerDraft;
  initialSubmissionId?: string;
  initialPlotId?: string;
  initialSeasonId?: string;
  compact?: boolean;
  writeGuard?: ReturnType<typeof useAsyncGuard>;
  onSaved?: (record: FarmRecord) => void;
  onCancel?: () => void;
  onError: (message: string) => void;
  onRecordsChanged: () => void | Promise<void>;
  onQuickTask: (input: TaskInput) => Promise<unknown>;
}

interface RecordResponse { success: true; record: FarmRecord }

function emptyForm(plotId = "") {
  return {
    plot_id: plotId, season_id: "", kind: "施肥" as FarmRecordKind, happened_on: todayIso(), crop: "",
    quantity: "", cost: "", material: "", safe_days: "", yield_kg: "", unit_price: "", detail: "",
  };
}

function fieldsDiffer(draft: Record<string, string>, saved: Record<string, string>) {
  return Object.keys(draft).some((field) => draft[field] !== saved[field]);
}

export const FarmRecordForm = forwardRef<FarmRecordFormHandle, FarmRecordFormProps>(function FarmRecordForm(props, ref) {
  const { plots, seasons, initialDraft, initialPlotId, initialSeasonId, compact, onSaved, onCancel, onError, onRecordsChanged, onQuickTask } = props;
  const [form, setForm] = useState(() => ({
    ...emptyForm(initialPlotId || (initialDraft ? "" : plots[0]?.id)),
    ...initialDraft,
    season_id: initialDraft?.season_id ?? initialSeasonId ?? "",
  }));
  const [savedForm, setSavedForm] = useState(form);
  const [submissionId, setSubmissionId] = useState(() => props.initialSubmissionId ?? newSubmissionId());
  const [editingRecord, setEditingRecord] = useState<FarmRecord | null>(null);
  const [followUp, setFollowUp] = useState<TaskInput | null>(null);
  const localWriteGuard = useAsyncGuard();
  const writes = props.writeGuard ?? localWriteGuard;
  const requestLeave = useRequestLeave();
  const sessionCurrent = useSessionGuard();
  const [saveUnconfirmed, setSaveUnconfirmed] = useState(false);
  const [saveNotice, setSaveNotice] = useState("");
  useUnsavedChanges(fieldsDiffer(form, savedForm) || saveUnconfirmed, writes.busy, () => {
    setForm(savedForm);
    setSaveUnconfirmed(false);
    onError("");
  });

  const selectedPlot = plots.find((plot) => plot.id === form.plot_id);
  const safety = selectedPlot?.harvest_safety;
  const harvestWarning =
    form.kind === "采收" && safety?.in_safe_window
      ? `该地块 ${safety.happened_on} 施过 ${safety.material}，登记的安全间隔期 ${safety.safe_days} 天，按输入计算最早采收日为 ${safety.earliest_harvest_on}（还有 ${safety.days_remaining} 天）。提醒覆盖该地块全部茬次与作物，请以产品标签为准。`
      : "";

  function handlePlotChange(plotId: string) {
    setForm((current) => ({ ...current, plot_id: plotId, season_id: "", crop: "" }));
  }

  function handleSeasonChange(seasonId: string) {
    setForm((current) => ({ ...current, season_id: seasonId, crop: "" }));
  }

  function handleKindChange(kind: FarmRecordKind) {
    if (kind === form.kind) return;
    setForm((current) => ({
      ...current, kind, material: "", quantity: "",
      safe_days: kind === "打药" ? current.safe_days : "",
      yield_kg: kind === "采收" ? current.yield_kg : "",
      unit_price: kind === "采收" ? current.unit_price : "",
    }));
  }

  function resetForm(fields: typeof form) {
    setForm(fields);
    setSavedForm(fields);
    setSaveUnconfirmed(false);
  }

  function cancelEdit() {
    setEditingRecord(null);
    resetForm(emptyForm(form.plot_id));
    onError("");
  }

  function startEdit(record: FarmRecord) {
    setEditingRecord(record);
    setFollowUp(null);
    resetForm({
      plot_id: record.plot_id, season_id: record.season_id ?? "unassigned",
      kind: record.kind, happened_on: record.happened_on,
      crop: record.crop, quantity: record.quantity, detail: record.detail,
      cost: record.cost === null ? "" : String(record.cost),
      material: ["施肥", "打药"].includes(record.kind) ? record.material : "",
      safe_days: record.kind === "打药" && record.safe_days !== null ? String(record.safe_days) : "",
      yield_kg: record.kind === "采收" && record.yield_kg !== null ? String(record.yield_kg) : "",
      unit_price: record.kind === "采收" && record.unit_price !== null ? String(record.unit_price) : "",
    });
    setSaveNotice("");
    onError("");
    document.getElementById("ledger-record-form")?.scrollIntoView({ behavior: "smooth" });
  }

  async function handleSubmit() {
    if (!sessionCurrent()) return;
    if (!form.plot_id) {
      onError("请先选择地块。");
      return;
    }
    await writes.run(async () => {
      setSaveNotice("");
      setSaveUnconfirmed(true);
      try {
        const payload = {
          plot_id: form.plot_id,
          ...(form.season_id ? { season_id: form.season_id === "unassigned" ? null : form.season_id } : {}),
          kind: form.kind,
          happened_on: form.happened_on,
          crop: form.crop,
          quantity: form.quantity,
          cost: form.cost.trim() === "" ? null : Number(form.cost),
          material: ["施肥", "打药"].includes(form.kind) ? form.material : "",
          safe_days: form.kind !== "打药" || form.safe_days.trim() === "" ? null : Number(form.safe_days),
          yield_kg: form.kind !== "采收" || form.yield_kg.trim() === "" ? null : Number(form.yield_kg),
          unit_price: form.kind !== "采收" || form.unit_price.trim() === "" ? null : Number(form.unit_price),
          detail: form.detail,
        };
        if (editingRecord) {
          await api.patch<RecordResponse>(`/api/farm-records/${editingRecord.id}`, payload);
          if (!sessionCurrent()) return;
          cancelEdit();
          setSaveNotice("修改已保存，收支将按更新后的台账重新汇总。");
        } else {
          const response = await api.post<RecordResponse>("/api/farm-records", { ...payload, submission_id: submissionId });
          if (!sessionCurrent()) return;
          setSubmissionId(newSubmissionId());
          onError("");
          onSaved?.(response.data.record);
          resetForm({
            ...form, quantity: "", cost: "", material: "", safe_days: "",
            yield_kg: "", unit_price: "", detail: "",
          });
          setSaveNotice("已记入台账，可随时编辑补全费用、产量等信息。");
        }
        const rule = editingRecord ? undefined : followUps[form.kind];
        setFollowUp(
          rule
            ? {
                plot_id: form.plot_id,
                title: rule.label,
                due_on: addDays(form.happened_on, rule.days),
                notes: "",
              }
            : null,
        );
        onError("");
        await onRecordsChanged();
      } catch (error) {
        if (sessionCurrent()) onError(getErrorMessage(error));
      }
    });
  }

  useImperativeHandle(ref, () => ({
    edit: startEdit,
    discardDeletedRecord: (recordId) => { if (editingRecord?.id === recordId) cancelEdit(); },
  }));

  return (
    <form className="panel panel--full ledger-form" id="ledger-record-form" onSubmit={(event) => { event.preventDefault(); void handleSubmit(); }}>
      <div className="panel__header">
        <div>
          <h3>{editingRecord ? "编辑农事记录" : "记一次农事"}</h3>
          <p>确认地块、日期和作业类型即可保存，其余可留空，稍后编辑补齐。</p>
        </div>
      </div>

      {selectedPlot?.is_demo && <p className="demo-notice">当前为演示地块。自行新增的台账会保留，清空演示时不会删除。</p>}
      <fieldset className="ledger-fields" disabled={writes.busy}>
      <div className="record-kind-buttons" role="group" aria-label="快捷农活">
        {recordKinds.map((kind) => <button type="button" key={kind} aria-pressed={form.kind === kind}
          className={form.kind === kind ? "secondary-button is-selected" : "ghost-button"}
          onClick={() => handleKindChange(kind)}>{kind}</button>)}
      </div>
      <div className="field-grid">
        <label className="field">
          <span>记录到地块</span>
          <div className="field-control field-control--select">
            <select value={form.plot_id} onChange={(event) => handlePlotChange(event.target.value)}>
              <option value="">请选择地块</option>
              {plots.map((plot) => (
                <option key={plot.id} value={plot.id}>
                  {plot.name}{plot.is_demo ? "【演示】" : ""}
                </option>
              ))}
            </select>
          </div>
        </label>

        <RecordSeasonField
          seasons={seasons}
          plotId={form.plot_id}
          date={form.happened_on}
          value={form.season_id}
          onChange={handleSeasonChange}
        />

        <label className="field ledger-kind-field">
          <span>作业类型</span>
          <div className="field-control field-control--select">
            <select
              value={form.kind}
              onChange={(event) => handleKindChange(event.target.value as FarmRecordKind)}
            >
              {recordKinds.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </div>
        </label>

        <label className="field">
          <span>作业日期</span>
          <div className="field-control">
            <input
              type="date"
              value={form.happened_on}
              onChange={(event) => {
                const date = event.target.value;
                setForm((current) => ({
                  ...current, happened_on: date, season_id: editingRecord ? current.season_id : "", crop: "",
                }));
              }}
            />
          </div>
        </label>

        <label className="field">
          <span>费用（元）</span>
          <div className="field-control">
            <input
              type="number"
              inputMode="decimal"
              value={form.cost}
              min={0}
              step={0.01}
              placeholder="可留空"
              onChange={(event) => setForm((current) => ({ ...current, cost: event.target.value }))}
            />
          </div>
        </label>

        {["施肥", "打药"].includes(form.kind) && (
          <label className="field">
            <span>{form.kind === "打药" ? "农药名称" : "肥料名称"}</span>
            <div className="field-control">
              <input value={form.material} maxLength={40}
                placeholder={form.kind === "打药" ? "例如：吡虫啉" : "例如：尿素"}
                onChange={(event) => setForm((current) => ({ ...current, material: event.target.value }))} />
            </div>
          </label>
        )}

        {form.kind === "打药" && (
          <>
            <label className="field">
              <span>安全间隔期（天）</span>
              <div className="field-control">
                <input
                  type="number"
                  inputMode="numeric"
                  value={form.safe_days}
                  min={0}
                  max={365}
                  placeholder="按产品标签填写"
                  onChange={(event) => setForm((current) => ({ ...current, safe_days: event.target.value }))}
                />
              </div>
            </label>
          </>
        )}

        {form.kind === "采收" && (
          <>
            <label className="field">
              <span>产量（公斤）</span>
              <div className="field-control">
                <input
                  type="number"
                  inputMode="decimal"
                  value={form.yield_kg}
                  min={0}
                  step={0.1}
                  placeholder="例如：2100"
                  onChange={(event) => setForm((current) => ({ ...current, yield_kg: event.target.value }))}
                />
              </div>
            </label>

            <label className="field">
              <span>单价（元/公斤）</span>
              <div className="field-control">
                <input
                  type="number"
                  inputMode="decimal"
                  value={form.unit_price}
                  min={0}
                  step={0.01}
                  placeholder="例如：2.4"
                  onChange={(event) => setForm((current) => ({ ...current, unit_price: event.target.value }))}
                />
              </div>
            </label>
          </>
        )}

      </div>
      <details className="ledger-extra" open={!compact || !!initialDraft?.detail}>
        <summary>补充用量、作物与说明（选填）</summary>
        <div className="field-grid">
          <label className="field">
            <span>作物</span>
            <div className="field-control">
              <input
                value={form.crop}
                maxLength={20}
                placeholder="留空则使用匹配茬次的作物"
                onChange={(event) => setForm((current) => ({ ...current, crop: event.target.value }))}
              />
            </div>
          </label>

          <label className="field">
            <span>用量</span>
            <div className="field-control">
              <input
                value={form.quantity}
                maxLength={40}
                placeholder="例如：15 公斤/亩"
                onChange={(event) => setForm((current) => ({ ...current, quantity: event.target.value }))}
              />
            </div>
          </label>

          <label className="field field--full">
            <span>作业说明</span>
            <div className="field-control field-control--textarea">
              <textarea
                value={form.detail}
                maxLength={300}
                placeholder="例如：雨后追尿素，重点看低洼处"
                onChange={(event) => setForm((current) => ({ ...current, detail: event.target.value }))}
              />
            </div>
          </label>
        </div>
      </details>
      </fieldset>

      {saveNotice && <p className="ledger-save-notice" role="status">{saveNotice}</p>}
      {saveUnconfirmed && !writes.busy && <p className="economics-note">本次保存尚未确认。填写内容仍保留，请检查网络后点击保存重试；不会在后台自动重试。</p>}

      {harvestWarning && <p className="form-warning" role="status">{harvestWarning}</p>}

      {followUp && (
        <p className="follow-up" role="status">
          已记入台账。接下来可以：
          <button
            className="ghost-button"
            type="button"
            onClick={() => {
              void onQuickTask(followUp).then(() => { if (sessionCurrent()) setFollowUp(null); });
            }}
          >
            加为待办：{formatDate(followUp.due_on)} {followUp.title}
          </button>
        </p>
      )}

      <div className="ledger-form-actions">
      <button className="primary-button" type="submit" disabled={writes.busy}>
        <CalendarPlus size={16} />
        {writes.busy ? "保存中…" : editingRecord ? "保存修改" : "记入台账"}
      </button>
      {editingRecord && <button className="secondary-button" type="button" disabled={writes.busy} onClick={() => requestLeave(cancelEdit)}>取消编辑</button>}
      {onCancel && <button className="secondary-button" type="button" disabled={writes.busy} onClick={() => requestLeave(onCancel)}>取消记账</button>}
      </div>
    </form>

  );
});
