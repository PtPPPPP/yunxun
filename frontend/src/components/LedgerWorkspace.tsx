import { CalendarPlus, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { ConfirmDialog } from "./ConfirmDialog";
import { useAsyncGuard } from "../hooks/useAsyncGuard";
import { api, getErrorMessage } from "../lib/api";
import { FarmRecord, FarmRecordKind, Plot } from "../types";

const PAGE_SIZE = 20;
const recordKinds: FarmRecordKind[] = ["播种", "施肥", "打药", "灌溉", "除草", "采收", "其他"];

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
  onError: (message: string) => void;
  /** 增删记录后通知外层刷新地块列表，让「本季 N 次作业」保持同步。 */
  onRecordsChanged: () => void;
}

function todayIso(): string {
  const now = new Date();
  return new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}

function formatDate(value: string): string {
  const [year, month, date] = value.split("-");
  return `${year}/${Number(month)}/${Number(date)}`;
}

function formatCost(value: number | null): string {
  return value === null ? "未记费用" : `¥${value}`;
}

function round2(value: number): number {
  return Math.round(value * 100) / 100;
}

export function LedgerWorkspace(props: LedgerWorkspaceProps) {
  const { plots, onError, onRecordsChanged } = props;
  const [form, setForm] = useState({
    plot_id: "",
    kind: "施肥" as FarmRecordKind,
    happened_on: todayIso(),
    crop: "",
    quantity: "",
    cost: "",
    yield_kg: "",
    unit_price: "",
    detail: "",
  });
  const [plotFilter, setPlotFilter] = useState("");
  const [records, setRecords] = useState<FarmRecord[]>([]);
  const [pagination, setPagination] = useState<{ has_more: boolean; next_cursor: string | null }>({
    has_more: false,
    next_cursor: null,
  });
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<FarmRecord | null>(null);
  const action = useAsyncGuard();

  const loadRecords = useCallback(
    async (cursor: string | null, plotId: string) => {
      const params: Record<string, string | number> = { limit: PAGE_SIZE };
      if (plotId) params.plot_id = plotId;
      if (cursor) params.cursor = cursor;
      const response = await api.get<RecordsResponse>("/api/farm-records", { params });
      return response.data;
    },
    [],
  );

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    loadRecords(null, plotFilter)
      .then((data) => {
        if (cancelled) return;
        setRecords(data.records);
        setPagination(data.pagination);
      })
      .catch((error: unknown) => {
        if (!cancelled) onError(getErrorMessage(error));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [loadRecords, onError, plotFilter]);

  // 地块列表就绪后默认选中第一块，避免每次都要手动挑选。
  useEffect(() => {
    if (form.plot_id || plots.length === 0) return;
    setForm((current) => ({ ...current, plot_id: plots[0].id, crop: plots[0].crop }));
  }, [form.plot_id, plots]);

  function handlePlotChange(plotId: string) {
    const plot = plots.find((item) => item.id === plotId);
    setForm((current) => ({ ...current, plot_id: plotId, crop: plot?.crop ?? "" }));
  }

  async function handleSubmit() {
    if (!form.plot_id) {
      onError("请先选择地块。");
      return;
    }
    await action.run(async () => {
      try {
        await api.post<RecordResponse>("/api/farm-records", {
          plot_id: form.plot_id,
          kind: form.kind,
          happened_on: form.happened_on,
          crop: form.crop,
          quantity: form.quantity,
          cost: form.cost.trim() === "" ? null : Number(form.cost),
          yield_kg: form.yield_kg.trim() === "" ? null : Number(form.yield_kg),
          unit_price: form.unit_price.trim() === "" ? null : Number(form.unit_price),
          detail: form.detail,
        });
        setForm((current) => ({ ...current, quantity: "", cost: "", yield_kg: "", unit_price: "", detail: "" }));
        onError("");
        const data = await loadRecords(null, plotFilter);
        setRecords(data.records);
        setPagination(data.pagination);
        onRecordsChanged();
      } catch (error) {
        onError(getErrorMessage(error));
      }
    });
  }

  async function handleLoadMore() {
    if (!pagination.next_cursor || loadingMore) return;
    setLoadingMore(true);
    try {
      const data = await loadRecords(pagination.next_cursor, plotFilter);
      setRecords((current) => [...current, ...data.records]);
      setPagination(data.pagination);
    } catch (error) {
      onError(getErrorMessage(error));
    } finally {
      setLoadingMore(false);
    }
  }

  async function confirmDelete() {
    if (!pendingDelete) return;
    await action.run(async () => {
      try {
        await api.delete(`/api/farm-records/${pendingDelete.id}`);
        onError("");
        const data = await loadRecords(null, plotFilter);
        setRecords(data.records);
        setPagination(data.pagination);
        onRecordsChanged();
        setPendingDelete(null);
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
      <div className="panel panel--full">
        <div className="panel__header">
          <div>
            <h3>记一次农事</h3>
            <p>记录作业日期、用量和费用，形成可回溯的田块台账。</p>
          </div>
        </div>

        <div className="field-grid">
          <label className="field">
            <span>记录到地块</span>
            <div className="field-control field-control--select">
              <select value={form.plot_id} onChange={(event) => handlePlotChange(event.target.value)}>
                {plots.map((plot) => (
                  <option key={plot.id} value={plot.id}>
                    {plot.name}
                  </option>
                ))}
              </select>
            </div>
          </label>

          <label className="field">
            <span>作业类型</span>
            <div className="field-control field-control--select">
              <select
                value={form.kind}
                onChange={(event) => setForm((current) => ({ ...current, kind: event.target.value as FarmRecordKind }))}
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
                onChange={(event) => setForm((current) => ({ ...current, happened_on: event.target.value }))}
              />
            </div>
          </label>

          <label className="field">
            <span>作物</span>
            <div className="field-control">
              <input
                value={form.crop}
                maxLength={20}
                placeholder="留空则记为地块当前作物"
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

          <label className="field">
            <span>费用（元）</span>
            <div className="field-control">
              <input
                type="number"
                value={form.cost}
                min={0}
                step={0.01}
                placeholder="可留空"
                onChange={(event) => setForm((current) => ({ ...current, cost: event.target.value }))}
              />
            </div>
          </label>

          {form.kind === "采收" && (
            <>
              <label className="field">
                <span>产量（公斤）</span>
                <div className="field-control">
                  <input
                    type="number"
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

        <button className="primary-button" type="button" onClick={() => void handleSubmit()} disabled={action.busy}>
          <CalendarPlus size={16} />
          {action.busy ? "保存中…" : "记入台账"}
        </button>
      </div>

      <div className="panel panel--full">
        <div className="panel__header">
          <div>
            <h3>台账记录</h3>
            <p>按作业日期倒序排列。</p>
          </div>
          <label className="field ledger-filter">
            <span>按地块筛选</span>
            <div className="field-control field-control--select">
              <select value={plotFilter} onChange={(event) => setPlotFilter(event.target.value)}>
                <option value="">全部地块</option>
                {plots.map((plot) => (
                  <option key={plot.id} value={plot.id}>
                    {plot.name}
                  </option>
                ))}
              </select>
            </div>
          </label>
        </div>

        {records.length === 0 && !loading ? (
          <p className="stats-empty">暂无台账记录，先在上面记一次农事吧。</p>
        ) : (
          <ul className="stats-records">
            {records.map((record) => (
              <li className="stats-record" key={record.id}>
                <div className="stats-record__meta">
                  <span className="stats-badge">{record.kind}</span>
                  <strong>{record.plot_name}</strong>
                  <span className="stats-record__time">{formatDate(record.happened_on)}</span>
                  <span className="stats-record__time">{record.crop}</span>
                  {record.quantity && <span className="stats-record__time">{record.quantity}</span>}
                  <span className="stats-record__time">{formatCost(record.cost)}</span>
                  {record.yield_kg !== null && <span className="stats-record__time">产量 {record.yield_kg} 公斤</span>}
                  {record.unit_price !== null && <span className="stats-record__time">{record.unit_price} 元/公斤</span>}
                  {record.yield_kg !== null && record.unit_price !== null && (
                    <span className="stats-record__time">收入 ¥{round2(record.yield_kg * record.unit_price)}</span>
                  )}
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
          <button className="secondary-button" type="button" onClick={() => void handleLoadMore()} disabled={loadingMore}>
            {loadingMore ? "加载中…" : "加载更多"}
          </button>
        )}
      </div>

      <ConfirmDialog
        open={pendingDelete !== null}
        title="删除这条农事记录？"
        description={
          pendingDelete
            ? `${pendingDelete.plot_name} 在 ${pendingDelete.happened_on} 的「${pendingDelete.kind}」记录会被永久删除，删除后无法恢复。`
            : ""
        }
        confirmLabel="确认删除"
        busy={action.busy}
        onConfirm={() => void confirmDelete()}
        onCancel={() => setPendingDelete(null)}
      />
    </section>
  );
}
