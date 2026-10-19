import { useCallback, useEffect, useRef, useState } from "react";

import { LedgerWorkspace } from "./LedgerWorkspace";
import { CsvExportButton } from "./CsvExportButton";
import { TaskInput } from "../hooks/useTasks";
import { useRequestLeave } from "../hooks/useUnsavedChanges";
import { api, getErrorMessage } from "../lib/api";
import { formatDate } from "../lib/date";
import { EconomicsFilters, EconomicsScope, FarmRecordFilters, Plot, PlotEconomics, PlotSeason } from "../types";

interface EconomicsPanelProps {
  plots: Plot[];
  seasons: PlotSeason[];
  filters: EconomicsFilters;
  onFiltersChange: (filters: EconomicsFilters) => void;
  onError: (message: string) => void;
  onRecordsChanged: () => void | Promise<void>;
  onQuickTask: (input: TaskInput) => Promise<unknown>;
}

const scopeNames: Record<EconomicsScope, string> = {
  all: "全部账目", cost: "已记录支出", revenue: "已完整记录收入",
  missing_cost: "费用未填", incomplete_harvest: "采收待补录",
};
const money = (value: number | null) => value === null ? "—" : `¥${value}`;
const kilograms = (value: number | null) => value === null ? "—" : `${value} 公斤`;
const sum = (rows: PlotEconomics[], key: "total_cost" | "total_revenue" | "net_revenue" | "missing_cost_count" | "incomplete_harvest_count" | "recorded_cost_count" | "complete_harvest_count") =>
  Math.round(rows.reduce((total, row) => total + row[key], 0) * 100) / 100;

export function EconomicsPanel({ plots, seasons, filters, onFiltersChange, onError, onRecordsChanged, onQuickTask }: EconomicsPanelProps) {
  const requestLeave = useRequestLeave();
  const [rows, setRows] = useState<PlotEconomics[]>([]);
  const [years, setYears] = useState<number[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const requestVersion = useRef(0);
  const [trace, setTrace] = useState<{ title: string; filters: FarmRecordFilters } | null>(null);

  const reload = useCallback(async () => {
    const version = ++requestVersion.current;
    setLoading(true);
    setRows([]);
    setError("");
    try {
      const params = Object.fromEntries(Object.entries(filters).filter(([, value]) => value));
      const response = await api.get<{ plots: PlotEconomics[]; available_years: number[] }>("/api/farm-records/economics", { params });
      if (version !== requestVersion.current) return;
      setRows(response.data.plots);
      setYears(response.data.available_years);
    } catch (requestError) {
      if (version === requestVersion.current) setError(getErrorMessage(requestError));
    } finally {
      if (version === requestVersion.current) setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    void reload();
    return () => { requestVersion.current += 1; };
  }, [reload]);

  function changeFilter(field: keyof EconomicsFilters, value: string) {
    requestVersion.current += 1;
    setRows([]);
    setLoading(true);
    onFiltersChange({ ...filters, [field]: value, ...(field === "plot_id" ? { season_id: "" } : {}),
      ...(field === "data_scope" ? { plot_id: "", season_id: "", year: "" } : {}) });
  }

  function openTrace(item: PlotEconomics | null, scope: EconomicsScope) {
    setTrace({
      title: `${item ? `${item.plot_name} · ${item.crop || "未归茬"}` : "当前统计范围"} · ${scopeNames[scope]}`,
      filters: {
        data_scope: filters.data_scope ?? "real",
        plot_id: item ? item.plot_id : filters.plot_id,
        season_id: item ? item.season_id ?? "unassigned" : filters.season_id, economics_scope: scope,
        kind: "", date_from: filters.year ? `${filters.year.padStart(4, "0")}-01-01` : "",
        date_to: filters.year ? `${filters.year.padStart(4, "0")}-12-31` : "",
      },
    });
  }

  function traceButton(item: PlotEconomics, scope: EconomicsScope, label: string) {
    return <button type="button" className="economics-link"
      aria-label={`查看${scopeNames[scope]}台账：${item.plot_name} · ${item.crop || "未归茬"} · ${item.started_on ?? "日期未填"}`}
      onClick={() => openTrace(item, scope)}>{label}</button>;
  }

  function cost(item: PlotEconomics) {
    return traceButton(item, item.recorded_cost_count === 0 && item.missing_cost_count > 0 ? "missing_cost" : "cost",
      item.recorded_cost_count === 0 && item.missing_cost_count > 0 ? "待补录" : money(item.total_cost));
  }

  function income(item: PlotEconomics) {
    const missing = item.complete_harvest_count === 0 && item.incomplete_harvest_count > 0;
    return traceButton(item, missing ? "incomplete_harvest" : "revenue", missing ? "待补录" : money(item.total_revenue));
  }

  function quality(item: PlotEconomics) {
    return <div className="economics-quality">
      {traceButton(item, "missing_cost", `费用未填 ${item.missing_cost_count} 条`)}
      {traceButton(item, "incomplete_harvest", `采收待补录 ${item.incomplete_harvest_count} 条`)}
    </div>;
  }

  function period(item: PlotEconomics) {
    return `${item.started_on ? formatDate(item.started_on) : "开始日未填"} ~ ${item.ended_on ? formatDate(item.ended_on) : item.season_id ? "进行中" : "未归茬"}`;
  }

  function perMu(item: PlotEconomics) {
    return <div className="economics-per-mu">
      <span>支出 {item.recorded_cost_count === 0 && item.missing_cost_count > 0 ? "待补录" : money(item.cost_per_mu)}</span>
      <span>收入 {item.complete_harvest_count === 0 && item.incomplete_harvest_count > 0 ? "待补录" : money(item.revenue_per_mu)}</span>
      <span>差额 {money(item.net_per_mu)}</span>
      <span>产量 {item.recorded_yield_count === 0 && item.incomplete_harvest_count > 0 ? "待补录" : kilograms(item.yield_per_mu)}</span>
    </div>;
  }

  if (trace) {
    return <div className="panel--full">
      <div className="panel economics-trace-header">
        <h3>收支台账明细</h3>
        <p>{trace.title}；{filters.year ? `${filters.year} 年作业日期范围` : "全部年份"}。可直接编辑补录，返回后保留统计筛选。</p>
        <button className="secondary-button" type="button" onClick={() => requestLeave(() => { setTrace(null); void reload(); })}>返回收支统计</button>
      </div>
      <LedgerWorkspace plots={plots} seasons={seasons} initialFilters={trace.filters} onError={onError}
        onQuickTask={onQuickTask} onRecordsChanged={async () => { await onRecordsChanged(); await reload(); }} />
    </div>;
  }

  const missingCost = sum(rows, "missing_cost_count");
  const missingHarvest = sum(rows, "incomplete_harvest_count");
  const yearOptions = Array.from(new Set([...years, ...(filters.year ? [Number(filters.year)] : [])])).sort((a, b) => b - a);

  return <div className="panel panel--full economics-panel">
    <div className="panel__header"><div><h3>每茬收支</h3><p>已记录收支差额 = 已记录收入 − 已记录支出。</p></div></div>
    <p className="economics-note">仅汇总已填写的费用与产量；收入仅包含产量、单价都完整的采收记录。未记录的人工、地租等成本不包含在内。</p>
    <p className="economics-note">年度按作业日期划分，跨年茬次只计所选年份内的记录；全部年份显示整茬累计。亩均指标按地块当前登记面积计算。</p>
    <div className="field-grid economics-filters">
      <label className="field"><span>收支数据来源</span><div className="field-control field-control--select">
        <select value={filters.data_scope ?? "real"} onChange={(event) => changeFilter("data_scope", event.target.value)}>
          <option value="real">真实记录</option><option value="demo">演示记录</option><option value="all">全部记录（含演示）</option>
        </select>
      </div></label>
      <label className="field"><span>统计地块</span><div className="field-control field-control--select">
        <select value={filters.plot_id} onChange={(event) => changeFilter("plot_id", event.target.value)}>
          <option value="">全部地块</option>{plots.map((plot) => <option key={plot.id} value={plot.id}>{plot.name}</option>)}
        </select>
      </div></label>
      <label className="field"><span>统计茬次</span><div className="field-control field-control--select">
        <select value={filters.season_id} onChange={(event) => changeFilter("season_id", event.target.value)}>
          <option value="">全部茬次（含历史）</option><option value="unassigned">未归茬</option>
          {seasons.filter((season) => !filters.plot_id || season.plot_id === filters.plot_id).map((season) => <option key={season.id} value={season.id}>
            {plots.find((plot) => plot.id === season.plot_id)?.name} · {season.crop}（{season.started_on ?? "开始日未填"} 至 {season.ended_on ?? "进行中"}）
          </option>)}
        </select>
      </div></label>
      <label className="field"><span>作业年份</span><div className="field-control field-control--select">
        <select value={filters.year} onChange={(event) => changeFilter("year", event.target.value)}>
          <option value="">全部年份</option>{yearOptions.map((year) => <option key={year} value={year}>{year} 年</option>)}
        </select>
      </div></label>
    </div>
    <p className="demo-notice">{filters.data_scope === "demo" ? "演示收支：示例金额不代表真实经营成果。" : filters.data_scope === "all" ? "全部记录可能包含演示金额，请切换真实记录查看自己的收支。" : "当前仅汇总真实记录，不包含演示金额。"}</p>
    <div className="csv-export-actions">
      <CsvExportButton endpoint="/api/farm-records/economics/export.csv" params={filters} label="导出收支汇总 CSV" unit="行汇总" disabled={loading || !!error} />
      <CsvExportButton endpoint="/api/farm-records/export.csv" params={filters} label="导出对应台账 CSV" unit="条台账" disabled={loading || !!error} />
    </div>
    <p className="economics-note">导出当前筛选范围全部数据；选定历史茬次可导出单茬收支及对应明细。CSV 用于留档和分析，不能作为完整数据库恢复备份。</p>
    {error && <p role="alert">{error}</p>}
    {loading ? <p role="status">正在核对收支…</p> : !error && <>
      <div className="stats-summary">
        <div className="stat-card"><span>已记录支出</span><strong><button type="button" className="economics-link" aria-label="查看当前范围支出台账"
          onClick={() => openTrace(null, sum(rows, "recorded_cost_count") === 0 && missingCost > 0 ? "missing_cost" : "cost")}>{sum(rows, "recorded_cost_count") === 0 && missingCost > 0 ? "待补录" : money(sum(rows, "total_cost"))}</button></strong></div>
        <div className="stat-card"><span>已记录收入</span><strong><button type="button" className="economics-link" aria-label="查看当前范围收入台账"
          onClick={() => openTrace(null, sum(rows, "complete_harvest_count") === 0 && missingHarvest > 0 ? "incomplete_harvest" : "revenue")}>{sum(rows, "complete_harvest_count") === 0 && missingHarvest > 0 ? "待补录" : money(sum(rows, "total_revenue"))}</button></strong></div>
        <div className="stat-card"><span>已记录收支差额</span><strong><button type="button" className="economics-link" aria-label="查看当前范围全部台账"
          onClick={() => openTrace(null, "all")}>{money(sum(rows, "net_revenue"))}</button></strong></div>
      </div>
      <p className="economics-completeness">当前范围：
        <button type="button" className="economics-link" aria-label="查看当前范围费用未填台账" onClick={() => openTrace(null, "missing_cost")}>费用未填 {missingCost} 条</button>，
        <button type="button" className="economics-link" aria-label="查看当前范围采收待补录台账" onClick={() => openTrace(null, "incomplete_harvest")}>采收待补录 {missingHarvest} 条</button>。
        同一记录可能同时出现在两类待补录中，待补录金额尚未计入差额。点击数字可查看组成台账。</p>
      {rows.length === 0 ? <p className="stats-empty">当前筛选下没有收支记录，请调整地块、茬次或年份。</p> : <>
        <div className="economics-table-wrap"><table className="economics-table">
          <thead><tr><th>地块</th><th>茬次</th><th>起止</th><th>登记面积</th><th>记录次数</th><th>已记录支出</th><th>已记录产量</th><th>已记录收入</th><th>已记录收支差额</th><th>亩均指标</th><th>待补录</th></tr></thead>
          <tbody>{rows.map((item) => <tr key={`${item.plot_id}:${item.season_id ?? "unassigned"}`}>
            <td>{item.plot_name}{item.is_demo && <span className="demo-badge">演示资料</span>}</td><td>{item.season_id ? item.crop : "未归茬"}</td><td>{period(item)}</td><td>{item.area_mu} 亩</td>
            <td>{traceButton(item, "all", `${item.record_count} 次`)}</td><td>{cost(item)}</td>
            <td>{item.recorded_yield_count === 0 && item.incomplete_harvest_count > 0 ? "待补录" : kilograms(item.total_yield_kg)}</td>
            <td>{income(item)}</td><td className={item.net_revenue < 0 ? "economics-negative" : ""}>{traceButton(item, "all", money(item.net_revenue))}</td>
            <td>{perMu(item)}</td><td>{quality(item)}</td>
          </tr>)}</tbody>
        </table></div>
        <div className="economics-cards">{rows.map((item) => <article className="economics-season-card" key={`${item.plot_id}:${item.season_id ?? "unassigned"}`}>
          <h4>{item.plot_name} · {item.season_id ? item.crop : "未归茬"}{item.is_demo && <span className="demo-badge">演示资料</span>}</h4><p>{period(item)}</p>
          <dl><dt>登记面积</dt><dd>{item.area_mu} 亩</dd><dt>记录次数</dt><dd>{traceButton(item, "all", `${item.record_count} 次`)}</dd>
            <dt>已记录支出</dt><dd>{cost(item)}</dd><dt>已记录收入</dt><dd>{income(item)}</dd>
            <dt>已记录收支差额</dt><dd>{traceButton(item, "all", money(item.net_revenue))}</dd>
            <dt>已记录产量</dt><dd>{item.recorded_yield_count === 0 && item.incomplete_harvest_count > 0 ? "待补录" : kilograms(item.total_yield_kg)}</dd>
            <dt>亩均指标</dt><dd>{perMu(item)}</dd></dl>{quality(item)}
        </article>)}</div>
      </>}
    </>}
  </div>;
}
