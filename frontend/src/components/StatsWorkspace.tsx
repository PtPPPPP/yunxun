import { useCallback, useEffect, useMemo, useState } from "react";

import { api, getErrorMessage } from "../lib/api";
import { ToolRecord, ToolRecordKind, ToolStatsPayload } from "../types";

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

function excerpt(text: string, max = 60): string {
  const compact = text.replace(/\s+/g, " ").trim();
  return compact.length > max ? `${compact.slice(0, max)}…` : compact;
}

export function StatsWorkspace({ onError }: StatsWorkspaceProps) {
  const [stats, setStats] = useState<ToolStatsPayload | null>(null);
  const [records, setRecords] = useState<ToolRecord[]>([]);
  const [pagination, setPagination] = useState<{ has_more: boolean; next_cursor: string | null }>({
    has_more: false,
    next_cursor: null,
  });
  const [kindFilter, setKindFilter] = useState<ToolRecordKind | "all">("all");
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);

  const loadStats = useCallback(async () => {
    try {
      const response = await api.get<{ success: true } & ToolStatsPayload>("/api/tool-records/stats");
      setStats(response.data);
      onError("");
    } catch (error) {
      onError(getErrorMessage(error));
    }
  }, [onError]);

  const loadRecords = useCallback(
    async (cursor: string | null, kind: ToolRecordKind | "all") => {
      const params: Record<string, string | number> = { limit: PAGE_SIZE };
      if (kind !== "all") params.kind = kind;
      if (cursor) params.cursor = cursor;
      const response = await api.get<RecordsResponse>("/api/tool-records", { params });
      return response.data;
    },
    [],
  );

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([loadStats(), loadRecords(null, kindFilter)])
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
  }, [kindFilter, loadRecords, loadStats, onError]);

  const handleLoadMore = useCallback(async () => {
    if (!pagination.next_cursor || loadingMore) return;
    setLoadingMore(true);
    try {
      const data = await loadRecords(pagination.next_cursor, kindFilter);
      setRecords((current) => [...current, ...data.records]);
      setPagination(data.pagination);
    } catch (error) {
      onError(getErrorMessage(error));
    } finally {
      setLoadingMore(false);
    }
  }, [kindFilter, loadRecords, loadingMore, onError, pagination.next_cursor]);

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
  const visionCount = stats?.counts_by_kind.vision ?? 0;
  const decisionCount = stats?.counts_by_kind.decision ?? 0;

  return (
    <section className="workspace-grid workspace-grid--stats">
      <div className="panel panel--full">
        <div className="panel__header">
          <div>
            <h3>使用汇总</h3>
            <p>图片诊断、农活建议和问答会话的累计情况。</p>
          </div>
        </div>
        <div className="stats-summary">
          <div className="stat-card"><span>图片诊断</span><strong>{loading ? "—" : visionCount}</strong></div>
          <div className="stat-card"><span>农活建议</span><strong>{loading ? "—" : decisionCount}</strong></div>
          <div className="stat-card"><span>会话总数</span><strong>{loading ? "—" : stats?.total_sessions ?? 0}</strong></div>
          <div className="stat-card"><span>消息总数</span><strong>{loading ? "—" : stats?.total_messages ?? 0}</strong></div>
        </div>
      </div>

      <div className="panel">
        <div className="panel__header">
          <div>
            <h3>近 {stats?.by_day_days ?? 14} 天诊断与建议</h3>
            <p>按天统计的图片诊断和农活建议次数。</p>
          </div>
        </div>
        <div className="stats-trend" role="img" aria-label="近两周诊断与建议趋势">
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
            <p>历史记录中最常诊断和建议的作物。</p>
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
          <p className="stats-empty">还没有记录，先去做一次诊断或生成建议吧。</p>
        )}
      </div>

      <div className="panel panel--full">
        <div className="panel__header">
          <div>
            <h3>历史记录</h3>
            <p>最近的图片诊断和农活建议结果。</p>
          </div>
          <div className="field-control field-control--select stats-filter">
            <select
              value={kindFilter}
              aria-label="筛选记录类型"
              onChange={(event) => setKindFilter(event.target.value as ToolRecordKind | "all")}
            >
              <option value="all">全部类型</option>
              <option value="vision">图片诊断</option>
              <option value="decision">农活建议</option>
            </select>
          </div>
        </div>
        {records.length === 0 && !loading ? (
          <p className="stats-empty">暂无历史记录。</p>
        ) : (
          <ul className="stats-records">
            {records.map((record) => (
              <li className="stats-record" key={record.id}>
                <div className="stats-record__meta">
                  <span className={record.kind === "vision" ? "stats-badge stats-badge--vision" : "stats-badge"}>
                    {record.kind === "vision" ? "图片诊断" : "农活建议"}
                  </span>
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
