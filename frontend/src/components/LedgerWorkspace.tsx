import { CalendarPlus, Pencil, Trash2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { ConfirmDialog } from "./ConfirmDialog";
import { CsvExportButton } from "./CsvExportButton";
import { TaskInput } from "../hooks/useTasks";
import { useAsyncGuard } from "../hooks/useAsyncGuard";
import { useRequestLeave, useUnsavedChanges } from "../hooks/useUnsavedChanges";
import { api, getErrorMessage } from "../lib/api";
import { addDays, formatDate, todayIso } from "../lib/date";
import { LedgerDraft } from "../lib/taskLedger";
import { newSubmissionId } from "../lib/submission";
import { EconomicsScope, FarmRecord, FarmRecordFilters, FarmRecordKind, Plot, PlotSeason } from "../types";

const PAGE_SIZE = 20;
const recordKinds: FarmRecordKind[] = ["播种", "施肥", "打药", "灌溉", "除草", "采收", "其他"];

// 记完一次农活后按作业类型给一条续办建议。只做提示，点一下才真的建待办，
// 不自动创建，免得清单被塞满。
const followUps: Partial<Record<FarmRecordKind, { days: number; label: string }>> = {
  播种: { days: 7, label: "查苗情与出苗率" },
  施肥: { days: 7, label: "复查追肥后长势" },
  打药: { days: 3, label: "复查防效" },
  灌溉: { days: 2, label: "查看墒情与积水" },
  除草: { days: 10, label: "复查杂草复发" },
};

interface RecordsResponse {
  success: true;
  records: FarmRecord[];
  pagination: { has_more: boolean; next_cursor: string | null };
}

interface RecordResponse {
  success: true;
  record: FarmRecord;
}

interface LedgerWorkspaceProps {
  plots: Plot[];
  seasons: PlotSeason[];
  initialFilters?: Partial<FarmRecordFilters>;
  initialDraft?: LedgerDraft;
  initialSubmissionId?: string;
  formOnly?: boolean;
  onSaved?: (record: FarmRecord) => void;
  onCancel?: () => void;
  onError: (message: string) => void;
  /** 写入后刷新地块计数和采收提醒；统计面板每次进入时重新查询。 */
  onRecordsChanged: () => void | Promise<void>;
  onQuickTask: (input: TaskInput) => Promise<unknown>;
}

const emptyPagination = { has_more: false, next_cursor: null as string | null };

function emptyForm(plotId = "") {
  return {
    plot_id: plotId, kind: "施肥" as FarmRecordKind, happened_on: todayIso(), crop: "",
    quantity: "", cost: "", material: "", safe_days: "", yield_kg: "", unit_price: "", detail: "",
  };
}

function formatCost(value: number | null): string {
  return value === null ? "费用未填" : `¥${value}`;
}

function round2(value: number): number {
  return Math.round(value * 100) / 100;
}

export function LedgerWorkspace(props: LedgerWorkspaceProps) {
  const { plots, seasons, initialFilters, initialDraft, formOnly, onSaved, onCancel, onError, onRecordsChanged, onQuickTask } = props;
  const [form, setForm] = useState(() => ({ ...emptyForm(initialFilters?.plot_id || (initialDraft ? "" : plots[0]?.id)), ...initialDraft }));
  const [submissionId, setSubmissionId] = useState(() => props.initialSubmissionId ?? newSubmissionId());
  const [filters, setFilters] = useState<FarmRecordFilters>(() => ({
    data_scope: "all",
    plot_id: "", season_id: "", economics_scope: "all", kind: "", date_from: "", date_to: "", ...initialFilters,
  }));
  const [deletionNotice, setDeletionNotice] = useState("");
  const [editingRecord, setEditingRecord] = useState<FarmRecord | null>(null);
  const [selectedSeason, setSelectedSeason] = useState(initialDraft?.season_id ?? initialFilters?.season_id ?? "");
  const [records, setRecords] = useState<FarmRecord[]>([]);
  const [pagination, setPagination] = useState(emptyPagination);
  const listVersion = useRef(0);
  const loadMoreInFlight = useRef(false);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<FarmRecord | null>(null);
  const [followUp, setFollowUp] = useState<TaskInput | null>(null);
  const action = useAsyncGuard();
  const requestLeave = useRequestLeave();
  const [cleanSignature, setCleanSignature] = useState(() => JSON.stringify([form, selectedSeason]));
  const [saveUnconfirmed, setSaveUnconfirmed] = useState(false);
  const [saveNotice, setSaveNotice] = useState("");
  useUnsavedChanges(JSON.stringify([form, selectedSeason]) !== cleanSignature || saveUnconfirmed, action.busy, () => {
    const [savedForm, savedSeason] = JSON.parse(cleanSignature) as [typeof form, string];
    setForm(savedForm);
    setSelectedSeason(savedSeason);
    setSaveUnconfirmed(false);
    onError("");
  });
  const matchingSeasons = seasons.filter((season) => season.plot_id === form.plot_id
    && (!season.started_on || season.started_on <= form.happened_on)
    && (!season.ended_on || form.happened_on <= season.ended_on));
  const automaticSeason = matchingSeasons.length === 1 && matchingSeasons[0].started_on ? matchingSeasons[0] : null;
  const seasonHint = selectedSeason === "unassigned" ? "本次明确记为未归茬。"
    : selectedSeason ? (() => {
      const season = seasons.find((item) => item.id === selectedSeason && item.plot_id === form.plot_id);
      if (!season) return "所选茬次不可用，请重新选择。";
      return (season.started_on && form.happened_on < season.started_on) || (season.ended_on && form.happened_on > season.ended_on)
        ? "作业日期不在所选茬次内，请调整日期、选择对应历史茬次或明确选择未归茬。"
        : `本次记入 ${season.crop}（${season.started_on ?? "开始日未填"} 至 ${season.ended_on ?? "进行中"}）。`;
    })() : automaticSeason
      ? `按作业日期匹配：${automaticSeason.crop}（${automaticSeason.started_on} 至 ${automaticSeason.ended_on ?? "进行中"}）。`
      : matchingSeasons.length ? "日期对应的茬次有歧义或开始日未填，请选择具体茬次或未归茬。" : "此日期没有匹配茬次，将记为未归茬。";

  // 记采收时若该地块还在安全期内，提醒但不阻断：紧急采收是真实存在的，
  // 应用不该替农户做决定，只负责把事实摆出来。
  const safety = plots.find((item) => item.id === form.plot_id)?.harvest_safety ?? null;
  const harvestWarning =
    form.kind === "采收" && safety?.in_safe_window
      ? `该地块 ${safety.happened_on} 施过 ${safety.material}，登记的安全间隔期 ${safety.safe_days} 天，按输入计算最早采收日为 ${safety.earliest_harvest_on}（还有 ${safety.days_remaining} 天）。提醒覆盖该地块全部茬次与作物，请以产品标签为准。`
      : "";

  const loadRecords = useCallback(
    async (cursor: string | null, recordFilters: FarmRecordFilters) => {
      const params: Record<string, string | number> = { limit: PAGE_SIZE };
      for (const [key, value] of Object.entries(recordFilters)) {
        if (value) params[key] = value;
      }
      if (cursor) params.cursor = cursor;
      const response = await api.get<RecordsResponse>("/api/farm-records", { params });
      return response.data;
    },
    [],
  );

  const refreshRecords = useCallback(async () => {
    const version = ++listVersion.current;
    setRecords([]);
    setPagination(emptyPagination);
    setLoading(true);
    try {
      const data = await loadRecords(null, filters);
      if (version !== listVersion.current) return;
      setRecords(data.records);
      setPagination(data.pagination);
    } catch (error) {
      if (version === listVersion.current) onError(getErrorMessage(error));
    } finally {
      if (version === listVersion.current) setLoading(false);
    }
  }, [loadRecords, filters, onError]);

  useEffect(() => {
    if (formOnly) return;
    void refreshRecords();
    return () => { listVersion.current += 1; };
  }, [refreshRecords, formOnly]);

  function handleFilterChange(field: keyof FarmRecordFilters, value: string) {
    listVersion.current += 1;
    setRecords([]);
    setPagination(emptyPagination);
    setFilters((current) => ({ ...current, [field]: value, ...(field === "plot_id" ? { season_id: "" } : {}) }));
    onError("");
  }

  function handlePlotChange(plotId: string) {
    setSelectedSeason("");
    setForm((current) => ({ ...current, plot_id: plotId, crop: "" }));
  }

  function handleSeasonChange(seasonId: string) {
    setSelectedSeason(seasonId);
    setForm((current) => ({ ...current, crop: "" }));
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

  function cancelEdit() {
    const next = emptyForm(form.plot_id);
    setEditingRecord(null);
    setForm(next);
    setSelectedSeason("");
    setCleanSignature(JSON.stringify([next, ""]));
    setSaveUnconfirmed(false);
    onError("");
  }

  function startEdit(record: FarmRecord) {
    setEditingRecord(record);
    setSelectedSeason(record.season_id ?? "unassigned");
    setFollowUp(null);
    const next = {
      plot_id: record.plot_id, kind: record.kind, happened_on: record.happened_on,
      crop: record.crop, quantity: record.quantity, detail: record.detail,
      cost: record.cost === null ? "" : String(record.cost),
      material: ["施肥", "打药"].includes(record.kind) ? record.material : "",
      safe_days: record.kind === "打药" && record.safe_days !== null ? String(record.safe_days) : "",
      yield_kg: record.kind === "采收" && record.yield_kg !== null ? String(record.yield_kg) : "",
      unit_price: record.kind === "采收" && record.unit_price !== null ? String(record.unit_price) : "",
    };
    setForm(next);
    setCleanSignature(JSON.stringify([next, record.season_id ?? "unassigned"]));
    setSaveUnconfirmed(false);
    setSaveNotice("");
    onError("");
    document.getElementById("ledger-record-form")?.scrollIntoView({ behavior: "smooth" });
  }

  async function handleSubmit() {
    if (!form.plot_id) {
      onError("请先选择地块。");
      return;
    }
    await action.run(async () => {
      setSaveNotice("");
      setSaveUnconfirmed(true);
      try {
        const payload = {
          plot_id: form.plot_id,
          ...(selectedSeason ? { season_id: selectedSeason === "unassigned" ? null : selectedSeason } : {}),
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
          cancelEdit();
          setSaveNotice("修改已保存，收支将按更新后的台账重新汇总。");
        } else {
          const response = await api.post<RecordResponse>("/api/farm-records", { ...payload, submission_id: submissionId });
          setSubmissionId(newSubmissionId());
          onError("");
          onSaved?.(response.data.record);
          const next = {
            ...form, quantity: "", cost: "", material: "", safe_days: "",
            yield_kg: "", unit_price: "", detail: "",
          };
          setForm(next);
          setCleanSignature(JSON.stringify([next, selectedSeason]));
          setSaveUnconfirmed(false);
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
        if (!formOnly) await refreshRecords();
      } catch (error) {
        onError(getErrorMessage(error));
      }
    });
  }

  async function handleLoadMore() {
    if (!pagination.next_cursor || loading || loadMoreInFlight.current) return;
    const version = listVersion.current;
    loadMoreInFlight.current = true;
    setLoadingMore(true);
    try {
      const data = await loadRecords(pagination.next_cursor, filters);
      if (version !== listVersion.current) return;
      setRecords((current) => [...current, ...data.records]);
      setPagination(data.pagination);
    } catch (error) {
      if (version === listVersion.current) onError(getErrorMessage(error));
    } finally {
      loadMoreInFlight.current = false;
      setLoadingMore(false);
    }
  }

  async function confirmDelete() {
    if (!pendingDelete) return;
    await action.run(async () => {
      try {
        await api.delete(`/api/farm-records/${pendingDelete.id}`);
        setDeletionNotice("台账已移入回收站，可从回收站恢复；最终删除前会保留。");
        onError("");
        if (editingRecord?.id === pendingDelete.id) cancelEdit();
        setPendingDelete(null);
        await onRecordsChanged();
        await refreshRecords();
      } catch (error) {
        onError(getErrorMessage(error));
      }
    });
  }

  if (plots.length === 0) {
    return (
      <section className="workspace-grid">
        <div className="panel panel--full">
          <div className="panel__header">
            <div>
              <h3>还没有地块</h3>
              <p>农事台账要挂在地块上，先去「地块档案」登记一块地。</p>
            </div>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="workspace-grid">
      <form className="panel panel--full ledger-form" id="ledger-record-form" onSubmit={(event) => { event.preventDefault(); void handleSubmit(); }}>
        <div className="panel__header">
          <div>
            <h3>{editingRecord ? "编辑农事记录" : "记一次农事"}</h3>
            <p>确认地块、日期和作业类型即可保存，其余可留空，稍后编辑补齐。</p>
          </div>
        </div>

        {plots.find((plot) => plot.id === form.plot_id)?.is_demo && <p className="demo-notice">当前为演示地块。自行新增的台账会保留，清空演示时不会删除。</p>}
        <fieldset className="ledger-fields" disabled={action.busy}>
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

          <label className="field">
            <span>所属茬次</span>
            <div className="field-control field-control--select">
              <select value={selectedSeason} onChange={(event) => handleSeasonChange(event.target.value)}>
                <option value="">{automaticSeason ? `自动匹配：${automaticSeason.crop}（${automaticSeason.started_on} 至 ${automaticSeason.ended_on ?? "进行中"}）` : "按作业日期自动匹配（有歧义请明确选择）"}</option>
                <option value="unassigned">未归茬</option>
                {seasons.filter((season) => season.plot_id === form.plot_id).map((season) => (
                  <option key={season.id} value={season.id}>
                    {season.crop}（{season.started_on ?? "开始日未填"} 至 {season.ended_on ?? "进行中"}）{season.is_demo ? "【演示】" : ""}
                  </option>
                ))}
              </select>
            </div>
            {form.plot_id && <small className="season-hint">{seasonHint}</small>}
          </label>

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
                  setForm((current) => ({ ...current, happened_on: event.target.value, crop: "" }));
                  if (!editingRecord) setSelectedSeason("");
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
        <details className="ledger-extra" open={!formOnly || !!initialDraft?.detail}>
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
        {saveUnconfirmed && !action.busy && <p className="economics-note">本次保存尚未确认。填写内容仍保留，请检查网络后点击保存重试；不会在后台自动重试。</p>}

        {harvestWarning && <p className="form-warning" role="status">{harvestWarning}</p>}

        {followUp && (
          <p className="follow-up" role="status">
            已记入台账。接下来可以：
            <button
              className="ghost-button"
              type="button"
              onClick={() => {
                void onQuickTask(followUp).then(() => setFollowUp(null));
              }}
            >
              加为待办：{formatDate(followUp.due_on)} {followUp.title}
            </button>
          </p>
        )}

        <div className="ledger-form-actions">
        <button className="primary-button" type="submit" disabled={action.busy}>
          <CalendarPlus size={16} />
          {action.busy ? "保存中…" : editingRecord ? "保存修改" : "记入台账"}
        </button>
        {editingRecord && <button className="secondary-button" type="button" disabled={action.busy} onClick={() => requestLeave(cancelEdit)}>取消编辑</button>}
        {onCancel && <button className="secondary-button" type="button" disabled={action.busy} onClick={() => requestLeave(onCancel)}>取消记账</button>}
        </div>
      </form>

      {!formOnly && <><div className="panel panel--full">
        <div className="panel__header">
          <div>
            <h3>台账记录</h3>
            <p>按作业日期倒序排列。</p>
          </div>
        </div>
        <div className="field-grid">
          <label className="field"><span>台账数据来源</span><div className="field-control field-control--select">
            <select value={filters.data_scope ?? "all"} onChange={(event) => handleFilterChange("data_scope", event.target.value)} disabled={action.busy}>
              <option value="all">全部记录</option><option value="real">真实记录</option><option value="demo">演示记录</option>
            </select>
          </div></label>
          <label className="field">
            <span>按地块筛选</span>
            <div className="field-control field-control--select">
              <select value={filters.plot_id} disabled={action.busy} onChange={(event) => handleFilterChange("plot_id", event.target.value)}>
                <option value="">全部地块</option>
                {plots.map((plot) => (
                  <option key={plot.id} value={plot.id}>
                    {plot.name}
                  </option>
                ))}
              </select>
            </div>
          </label>
          <label className="field">
            <span>按作业类型筛选</span>
            <div className="field-control field-control--select">
              <select value={filters.kind} disabled={action.busy} onChange={(event) => handleFilterChange("kind", event.target.value)}>
                <option value="">全部作业类型</option>
                {recordKinds.map((kind) => <option key={kind} value={kind}>{kind}</option>)}
              </select>
            </div>
          </label>
          <label className="field">
            <span>按茬次筛选</span>
            <div className="field-control field-control--select">
              <select value={filters.season_id} disabled={action.busy} onChange={(event) => handleFilterChange("season_id", event.target.value)}>
                <option value="">全部茬次</option>
                <option value="unassigned">未归茬</option>
                {seasons.filter((season) => !filters.plot_id || season.plot_id === filters.plot_id).map((season) => (
                  <option key={season.id} value={season.id}>
                    {plots.find((plot) => plot.id === season.plot_id)?.name} · {season.crop}（{season.started_on ?? "开始日未填"} 至 {season.ended_on ?? "进行中"}）
                  </option>
                ))}
              </select>
            </div>
          </label>
          <label className="field">
            <span>账目范围</span>
            <div className="field-control field-control--select">
              <select value={filters.economics_scope} disabled={action.busy} onChange={(event) => handleFilterChange("economics_scope", event.target.value as EconomicsScope)}>
                <option value="all">全部账目</option>
                <option value="cost">已记录支出</option>
                <option value="revenue">已完整记录收入</option>
                <option value="missing_cost">费用未填</option>
                <option value="incomplete_harvest">采收待补录</option>
              </select>
            </div>
          </label>
          <label className="field">
            <span>筛选开始日期</span>
            <div className="field-control"><input type="date" value={filters.date_from} disabled={action.busy}
              onChange={(event) => handleFilterChange("date_from", event.target.value)} /></div>
          </label>
          <label className="field">
            <span>筛选结束日期</span>
            <div className="field-control"><input type="date" value={filters.date_to} disabled={action.busy}
              onChange={(event) => handleFilterChange("date_to", event.target.value)} /></div>
          </label>
        </div>

        <CsvExportButton endpoint="/api/farm-records/export.csv" params={filters} label="导出当前筛选台账 CSV" unit="条台账" disabled={loading} />
        <p className="economics-note">导出全部符合筛选的数据，包含尚未加载的页。CSV 用于留档和分析，不能作为完整数据库恢复备份。</p>
        {deletionNotice && <p role="status">{deletionNotice}</p>}
        {loading && <p role="status">正在加载台账…</p>}
        {records.length === 0 && !loading ? (
          <p className="stats-empty">暂无台账记录，先在上面记一次农事吧。</p>
        ) : (
          <ul className="stats-records">
            {records.map((record) => (
              <li className="stats-record" key={record.id}>
                <div className="stats-record__meta">
                  <span className="stats-badge">{record.kind}</span>
                  <strong>{record.plot_name}</strong>
                  {record.is_demo && <span className="demo-badge">演示记录</span>}
                  {!record.is_demo && plots.find((plot) => plot.id === record.plot_id)?.is_demo && <span className="demo-badge">自己的记录 · 关联演示地块</span>}
                  <span className="stats-record__time">{formatDate(record.happened_on)}</span>
                  <span className="stats-record__time">{record.crop}</span>
                  {record.quantity && <span className="stats-record__time">{record.quantity}</span>}
                  {record.material && <span className="stats-record__time">{record.material}</span>}
                  {record.season_id === null && <span className="stats-record__time">未归茬</span>}
                  <span className="stats-record__time">{formatCost(record.cost)}</span>
                  {record.earliest_harvest_on && (
                    <span className="stats-record__time">最早采收 {record.earliest_harvest_on}</span>
                  )}
                  {record.yield_kg !== null && <span className="stats-record__time">产量 {record.yield_kg} 公斤</span>}
                  {record.unit_price !== null && <span className="stats-record__time">{record.unit_price} 元/公斤</span>}
                  {record.kind === "采收" && (record.yield_kg === null || record.unit_price === null) && (
                    <span className="stats-record__time">采收待补录：{[record.yield_kg === null ? "产量" : "", record.unit_price === null ? "单价" : ""].filter(Boolean).join("、")}</span>
                  )}
                  {record.yield_kg !== null && record.unit_price !== null && (
                    <span className="stats-record__time">收入 ¥{round2(record.yield_kg * record.unit_price)}</span>
                  )}
                  <button
                    className="ghost-button"
                    type="button"
                    aria-label={`编辑 ${record.kind} 记录`}
                    onClick={() => requestLeave(() => startEdit(record))}
                    disabled={action.busy}
                  >
                    <Pencil size={15} />编辑
                  </button>
                  <button
                    className="ghost-button danger ledger-delete"
                    type="button"
                    aria-label={`删除 ${record.kind} 记录`}
                    onClick={() => setPendingDelete(record)}
                    disabled={action.busy}
                  >
                    <Trash2 size={15} />
                    删除
                  </button>
                </div>
                {record.detail && <p>{record.detail}</p>}
              </li>
            ))}
          </ul>
        )}

        {pagination.has_more && (
          <button className="secondary-button" type="button" onClick={() => void handleLoadMore()} disabled={loadingMore || action.busy}>
            {loadingMore ? "加载中…" : "加载更多"}
          </button>
        )}
      </div>

      <ConfirmDialog
        open={pendingDelete !== null}
        title="删除这条农事记录？"
        description={
          pendingDelete
            ? `${pendingDelete.plot_name} 在 ${pendingDelete.happened_on} 的「${pendingDelete.kind}」记录将移入回收站，可恢复；不影响所属地块和其他台账。`
            : ""
        }
        confirmLabel="确认删除"
        busy={action.busy}
        onConfirm={() => void confirmDelete()}
        onCancel={() => setPendingDelete(null)}
      />
      </>}
    </section>
  );
}
