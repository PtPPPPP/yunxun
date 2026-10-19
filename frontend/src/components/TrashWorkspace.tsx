import { useCallback, useEffect, useState } from "react";

import { ConfirmDialog } from "./ConfirmDialog";
import { useAsyncGuard } from "../hooks/useAsyncGuard";
import { api, getErrorMessage } from "../lib/api";

export interface PlotDeleteImpact {
  season_count: number;
  record_count: number;
  trashed_record_count: number;
  task_count: number;
  revision: string;
}
interface TrashPlot extends PlotDeleteImpact { id: string; name: string; deleted_at: string; is_demo: boolean }
interface TrashRecord { id: string; plot_name: string; kind: string; happened_on: string; parent_deleted_at: string | null; deleted_at: string; revision: string; is_demo: boolean }
interface TrashResponse { plots: TrashPlot[]; records: TrashRecord[]; retention: string }
type PendingPurge = { kind: "plots" | "records"; id: string; revision: string; description: string };

export function TrashWorkspace({ onChanged }: { onChanged: () => Promise<void> }) {
  const [data, setData] = useState<TrashResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState<PendingPurge | null>(null);
  const action = useAsyncGuard();
  const reload = useCallback(async () => {
    setLoading(true); setData(null);
    try { setData((await api.get<TrashResponse>("/api/trash")).data); }
    catch (requestError) { setError(getErrorMessage(requestError)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void reload(); }, [reload]);

  async function operate(kind: string, id: string, revision?: string) {
    await action.run(async () => {
      setError(""); setMessage("");
      try {
        const response = revision
          ? await api.delete<{ message: string }>(`/api/trash/${kind}/${id}`, { params: { confirm: true, expected_revision: revision } })
          : await api.post<{ message: string }>(`/api/trash/${kind}/${id}/restore`);
        setPending(null); setMessage(response.data.message);
        await onChanged(); await reload();
      } catch (requestError) { setError(getErrorMessage(requestError)); setPending(null); await reload(); }
    });
  }

  return <section className="panel panel--full" aria-label="回收站资料">
    <h3>回收站</h3>
    <p>资料保留至你主动最终删除；当前没有自动清理。最终删除后无法从回收站恢复，历史已硬删除的数据也无法在这里找回。</p>
    <p>地块的茬次、台账和待办一起保留。恢复地块会恢复关联资料的可见性，此前单独删除的台账需要再单独恢复。</p>
    {message && <p role="status">{message}</p>}{error && <p role="alert">{error}</p>}
    <button type="button" className="ghost-button" disabled={loading || action.busy} onClick={() => { setError(""); void reload(); }}>刷新回收站</button>
    {loading ? <p role="status">正在读取回收站…</p> : data && <>
      <section aria-label="回收站地块"><h4>地块</h4>{data.plots.length === 0 ? <p>没有已删除地块。</p> : data.plots.map((plot) => <article className="trash-card" key={plot.id}>
        <h4>{plot.name}{plot.is_demo && <span className="demo-badge">演示资料</span>}</h4>
        <p>{plot.season_count} 茬、{plot.record_count} 条台账（含单独删除 {plot.trashed_record_count} 条）、{plot.task_count} 项待办（含已完成）</p>
        <p>移入时间：{new Date(plot.deleted_at).toLocaleString("zh-CN")}</p>
        <div className="inline-actions"><button className="secondary-button" type="button" disabled={action.busy} onClick={() => void operate("plots", plot.id)}>恢复地块 {plot.name}</button>
          <button className="ghost-button danger" type="button" disabled={action.busy} onClick={() => setPending({ kind: "plots", id: plot.id, revision: plot.revision,
            description: `「${plot.name}」及 ${plot.season_count} 茬、${plot.record_count} 条台账（包括单独删除的台账）、${plot.task_count} 项待办将永久删除，无法再从回收站恢复。` })}>最终删除地块 {plot.name}</button></div>
      </article>)}</section>
      <section aria-label="回收站台账"><h4>单独删除的台账</h4>{data.records.length === 0 ? <p>没有单独删除的台账。</p> : data.records.map((record) => <article className="trash-card" key={record.id}>
        <h4>{record.plot_name} · {record.kind} · {record.happened_on}{record.is_demo && <span className="demo-badge">演示记录</span>}</h4>
        <p>移入时间：{new Date(record.deleted_at).toLocaleString("zh-CN")}</p>
        {record.parent_deleted_at && <p>所属地块仍在回收站，请先恢复地块。</p>}
        <div className="inline-actions"><button type="button" className="secondary-button" disabled={action.busy || !!record.parent_deleted_at} onClick={() => void operate("records", record.id)}>恢复台账 {record.kind} {record.happened_on}</button>
          <button type="button" className="ghost-button danger" disabled={action.busy} onClick={() => setPending({ kind: "records", id: record.id, revision: record.revision,
            description: `${record.plot_name} 在 ${record.happened_on} 的「${record.kind}」台账将永久删除，无法再从回收站恢复。所属地块不受影响。` })}>最终删除台账 {record.kind} {record.happened_on}</button></div>
      </article>)}</section>
    </>}
    <ConfirmDialog open={pending !== null} title="确认最终删除？" description={pending?.description ?? ""} confirmLabel="最终删除（不可恢复）" busy={action.busy}
      onCancel={() => setPending(null)} onConfirm={() => { if (pending) void operate(pending.kind, pending.id, pending.revision); }} />
  </section>;
}
