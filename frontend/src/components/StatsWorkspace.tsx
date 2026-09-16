import { useCallback, useEffect, useMemo, useState } from "react";

import { api, getErrorMessage } from "../lib/api";
import { FarmStatsPayload, PlotEconomics, ToolRecord, ToolStatsPayload } from "../types";

const PAGE_SIZE = 20;

interface StatsWorkspaceProps {
  onError: (message: string) => void;
}

interface RecordsResponse {
  success: true;
  records: ToolRecord[];
  pagination: { has_more: boolean; next_cursor: string | null };
}

function formatDay(day: string): string {
  const [, month, date] = day.split("-");
  return `${Number(month)}/${Number(date)}`;
}

function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function round2(value: number): number {
  return Math.round(value * 100) / 100;
}

function excerpt(text: string, max = 60): string {
  const compact = text.replace(/\s+/g, " ").trim();
  return compact.length > max ? `${compact.slice(0, max)}…` : compact;
}

export function StatsWorkspace({ onError }: StatsWorkspaceProps) {
  const [stats, setStats] = useState<ToolStatsPayload | null>(null);
  const [farmStats, setFarmStats] = useState<FarmStatsPayload | null>(null);
  const [economics, setEconomics] = useState<PlotEconomics[]>([]);
  const [records, setRecords] = useState<ToolRecord[]>([]);
  const [pagination, setPagination] = useState<{ has_more: boolean; next_cursor: string | null }>({
    has_more: false,
    next_cursor: null,
  });
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);

  const loadStats = useCallback(async () => {
    try {
      const [adviceResponse, farmResponse, economicsResponse] = await Promise.all([
        api.get<{ success: true } & ToolStatsPayload>("/api/tool-records/stats"),
        api.get<{ success: true } & FarmStatsPayload>("/api/farm-records/stats"),
        api.get<{ success: true; plots: PlotEconomics[] }>("/api/farm-records/economics"),
      ]);
      setStats(adviceResponse.data);
      setFarmStats(farmResponse.data);
      setEconomics(economicsResponse.data.plots);
      onError("");
    } catch (error) {
      onError(getErrorMessage(error));
    }
  }, [onError]);

  const loadRecords = useCallback(async (cursor: string | null) => {
    const params: Record<string, string | number> = { limit: PAGE_SIZE };
    if (cursor) params.cursor = cursor;
    const response = await api.get<RecordsResponse>("/api/tool-records", { params });
    return response.data;
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([loadStats(), loadRecords(null)])
      .then(([, recordsData]) => {
        if (cancelled) return;
        setRecords(recordsData.records);
        setPagination(recordsData.pagination);
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
  }, [loadRecords, loadStats, onError]);

  const handleLoadMore = useCallback(async () => {
    if (!pagination.next_cursor || loadingMore) return;
    setLoadingMore(true);
    try {
      const data = await loadRecords(pagination.next_cursor);
      setRecords((current) => [...current, ...data.records]);
      setPagination(data.pagination);
    } catch (error) {
      onError(getErrorMessage(error));
    } finally {
      setLoadingMore(false);
    }
  }, [loadRecords, loadingMore, onError, pagination.next_cursor]);

  const trend = useMemo(() => {
    if (!stats) return [];
    const days: Array<{ day: string; total: number }> = [];
    const start = new Date(`${stats.by_day_since}T00:00:00`);
    for (let offset = 0; offset < stats.by_day_days; offset += 1) {
      const current = new Date(start);
      current.setDate(start.getDate() + offset);
      const key = current.toISOString().slice(0, 10);
      days.push({ day: key, total: stats.by_day[key] ?? 0 });
    }
    return days;
  }, [stats]);

  const maxDaily = useMemo(() => Math.max(1, ...trend.map((item) => item.total)), [trend]);
  const trendTotal = useMemo(() => trend.reduce((sum, item) => sum + item.total, 0), [trend]);
  const decisionCount = stats?.counts_by_kind.decision ?? 0;
  const cropCount = stats?.top_crops.length ?? 0;
  const totalCost = useMemo(() => economics.reduce((sum, item) => sum + item.total_cost, 0), [economics]);
  const totalRevenue = useMemo(() => economics.reduce((sum, item) => sum + item.total_revenue, 0), [economics]);

  function money(value: number | null): string {
    return value === null ? "—" : `¥${value}`;
  }

  function kilograms(value: number | null): string {
    return value === null ? "—" : `${value} 公斤`;
  }

  return (
    <section className="workspace-grid workspace-grid--stats">
      <div className="panel panel--full">
        <div className="panel__header">
          <div>
            <h3>使用汇总</h3>
            <p>地块、台账与农活建议的累计情况。</p>
          </div>
        </div>
        <div className="stats-summary">
          <div className="stat-card"><span>地块数</span><strong>{loading ? "—" : farmStats?.plot_count ?? 0}</strong></div>
          <div className="stat-card"><span>作业记录</span><strong>{loading ? "—" : farmStats?.record_count ?? 0}</strong></div>
          <div className="stat-card"><span>农活建议</span><strong>{loading ? "—" : decisionCount}</strong></div>
          <div className="stat-card"><span>覆盖作物</span><strong>{loading ? "—" : cropCount}</strong></div>
          <div className="stat-card"><span>{stats?.by_day_days ?? 14} 天记录</span><strong>{loading ? "—" : trendTotal}</strong></div>
          <div className="stat-card"><span>累计投入</span><strong>{loading ? "—" : `¥${round2(totalCost)}`}</strong></div>
          <div className="stat-card"><span>累计收入</span><strong>{loading ? "—" : `¥${round2(totalRevenue)}`}</strong></div>
          <div className="stat-card"><span>净收益</span><strong>{loading ? "—" : `¥${round2(totalRevenue - totalCost)}`}</strong></div>
        </div>
      </div>

      <div className="panel panel--full">
        <div className="panel__header">
          <div>
            <h3>投入产出</h3>
            <p>按地块汇总投入、产量与收入；采收记录填了产量和单价后这里才有数字。</p>
          </div>
        </div>
        {economics.length === 0 ? (
          <p className="stats-empty">还没有地块，先去「地块档案」登记一块地吧。</p>
        ) : (
          <div className="economics-table-wrap">
            <table className="economics-table">
              <thead>
                <tr>
                  <th>地块</th>
                  <th>面积</th>
                  <th>作物</th>
                  <th>投入</th>
                  <th>产量</th>
                  <th>收入</th>
                  <th>净收益</th>
                  <th>亩均成本</th>
                  <th>亩产</th>
                  <th>亩均净收益</th>
                </tr>
              </thead>
              <tbody>
                {economics.map((item) => (
                  <tr key={item.plot_id}>
                    <td>{item.plot_name}</td>
                    <td>{item.area_mu} 亩</td>
                    <td>{item.crop}</td>
                    <td>¥{item.total_cost}</td>
                    <td>{item.total_yield_kg} 公斤</td>
                    <td>¥{item.total_revenue}</td>
                    <td className={item.net_revenue < 0 ? "economics-negative" : ""}>¥{item.net_revenue}</td>
                    <td>{money(item.cost_per_mu)}</td>
                    <td>{kilograms(item.yield_per_mu)}</td>
                    <td className={item.net_per_mu !== null && item.net_per_mu < 0 ? "economics-negative" : ""}>
                      {money(item.net_per_mu)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="panel">
        <div className="panel__header">
          <div>
            <h3>近 {stats?.by_day_days ?? 14} 天建议次数</h3>
            <p>按天统计的农活建议次数。</p>
          </div>
        </div>
        <div className="stats-trend" role="img" aria-label="近两周农活建议趋势">
          {trend.map((item) => (
            <div className="stats-trend__col" key={item.day} title={`${item.day}：${item.total} 次`}>
              <div className="stats-trend__bar" style={{ height: `${Math.round((item.total / maxDaily) * 100)}%` }} />
              <span className="stats-trend__day">{formatDay(item.day)}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="panel">
        <div className="panel__header">
          <div>
            <h3>作物分布</h3>
            <p>历史记录中最常生成建议的作物。</p>
          </div>
        </div>
        {stats && stats.top_crops.length > 0 ? (
          <ul className="stats-crops">
            {stats.top_crops.map((item) => (
              <li key={item.crop}>
                <span>{item.crop}</span>
                <strong>{item.total} 次</strong>
              </li>
            ))}
          </ul>
        ) : (
          <p className="stats-empty">还没有记录，先去生成一次今日农活建议吧。</p>
        )}
      </div>

      <div className="panel panel--full">
        <div className="panel__header">
          <div>
            <h3>历史记录</h3>
            <p>最近的农活建议结果。</p>
          </div>
        </div>
        {records.length === 0 && !loading ? (
          <p className="stats-empty">暂无历史记录。</p>
        ) : (
          <ul className="stats-records">
            {records.map((record) => (
              <li className="stats-record" key={record.id}>
                <div className="stats-record__meta">
                  <span className="stats-badge">农活建议</span>
                  <strong>{record.crop}</strong>
                  <span className="stats-record__time">{formatDateTime(record.created_at)}</span>
                </div>
                <p>{excerpt(record.result)}</p>
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
    </section>
  );
}
