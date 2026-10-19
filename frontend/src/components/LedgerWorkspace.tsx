import { Pencil, Trash2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { ConfirmDialog } from "./ConfirmDialog";
import { CsvExportButton } from "./CsvExportButton";
import { FarmRecordForm, FarmRecordFormHandle, recordKinds } from "./FarmRecordForm";
import { TaskInput } from "../hooks/useTasks";
import { useAsyncGuard } from "../hooks/useAsyncGuard";
import { useSessionGuard } from "../hooks/useSessionBoundary";
import { useRequestLeave } from "../hooks/useUnsavedChanges";
import { api, getErrorMessage } from "../lib/api";
import { formatDate } from "../lib/date";
import { EconomicsScope, FarmRecord, FarmRecordFilters, Plot, PlotSeason } from "../types";

const PAGE_SIZE = 20;

interface RecordsResponse {
  success: true;
  records: FarmRecord[];
  pagination: { has_more: boolean; next_cursor: string | null };
}

interface LedgerWorkspaceProps {
  plots: Plot[];
  seasons: PlotSeason[];
  initialFilters?: Partial<FarmRecordFilters>;
  onError: (message: string) => void;
  onRecordsChanged: () => void | Promise<void>;
  onQuickTask: (input: TaskInput) => Promise<unknown>;
}

const emptyPagination = { has_more: false, next_cursor: null as string | null };

function formatCost(value: number | null): string {
  return value === null ? "费用未填" : `¥${value}`;
}

function round2(value: number): number {
  return Math.round(value * 100) / 100;
}

export function LedgerWorkspace({ plots, seasons, initialFilters, onError, onRecordsChanged, onQuickTask }: LedgerWorkspaceProps) {
  const recordForm = useRef<FarmRecordFormHandle>(null);
  const [filters, setFilters] = useState<FarmRecordFilters>(() => ({
    data_scope: "all",
    plot_id: "", season_id: "", economics_scope: "all", kind: "", date_from: "", date_to: "", ...initialFilters,
  }));
  const [deletionNotice, setDeletionNotice] = useState("");
  const [records, setRecords] = useState<FarmRecord[]>([]);
  const [pagination, setPagination] = useState(emptyPagination);
  const listVersion = useRef(0);
  const loadMoreInFlight = useRef(false);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<FarmRecord | null>(null);
  const action = useAsyncGuard();
  const requestLeave = useRequestLeave();
  const sessionCurrent = useSessionGuard();
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
    if (!sessionCurrent()) return;
    const version = ++listVersion.current;
    setRecords([]);
    setPagination(emptyPagination);
    setLoading(true);
    try {
      const data = await loadRecords(null, filters);
      if (version !== listVersion.current || !sessionCurrent()) return;
      setRecords(data.records);
      setPagination(data.pagination);
    } catch (error) {
      if (version === listVersion.current && sessionCurrent()) onError(getErrorMessage(error));
    } finally {
      if (version === listVersion.current && sessionCurrent()) setLoading(false);
    }
  }, [loadRecords, filters, onError, sessionCurrent]);

  useEffect(() => {
    void refreshRecords();
    return () => { listVersion.current += 1; };
  }, [refreshRecords]);

  function handleFilterChange(field: keyof FarmRecordFilters, value: string) {
    listVersion.current += 1;
    setRecords([]);
    setPagination(emptyPagination);
    setFilters((current) => ({ ...current, [field]: value, ...(field === "plot_id" ? { season_id: "" } : {}) }));
    onError("");
  }

  async function handleLoadMore() {
    if (!sessionCurrent() || !pagination.next_cursor || loading || loadMoreInFlight.current) return;
    const version = listVersion.current;
    loadMoreInFlight.current = true;
    setLoadingMore(true);
    try {
      const data = await loadRecords(pagination.next_cursor, filters);
      if (version !== listVersion.current || !sessionCurrent()) return;
      setRecords((current) => [...current, ...data.records]);
      setPagination(data.pagination);
    } catch (error) {
      if (version === listVersion.current && sessionCurrent()) onError(getErrorMessage(error));
    } finally {
      loadMoreInFlight.current = false;
      setLoadingMore(false);
    }
  }

  async function confirmDelete() {
    if (!pendingDelete || !sessionCurrent()) return;
    await action.run(async () => {
      try {
        await api.delete(`/api/farm-records/${pendingDelete.id}`);
        if (!sessionCurrent()) return;
        setDeletionNotice("台账已移入回收站，可从回收站恢复；最终删除前会保留。");
        onError("");
        recordForm.current?.discardDeletedRecord(pendingDelete.id);
        setPendingDelete(null);
        await onRecordsChanged();
        await refreshRecords();
      } catch (error) {
        if (sessionCurrent()) onError(getErrorMessage(error));
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
      <FarmRecordForm ref={recordForm} plots={plots} seasons={seasons} action={action}
        initialPlotId={initialFilters?.plot_id} initialSeasonId={initialFilters?.season_id}
        onError={onError} onQuickTask={onQuickTask}
        onRecordsChanged={async () => { await onRecordsChanged(); await refreshRecords(); }} />
      <div className="panel panel--full">
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
                    onClick={() => requestLeave(() => recordForm.current?.edit(record))}
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
    </section>
  );
}
