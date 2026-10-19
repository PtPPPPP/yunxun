import { FarmTask, FeatureKey, Plot } from "../types";
import { formatDate, todayIso } from "../lib/date";

interface HomeWorkspaceProps {
  tasks: FarmTask[];
  plots: Plot[];
  loading: boolean;
  busy: boolean;
  onNavigate: (feature: FeatureKey) => void;
  onComplete: (task: FarmTask) => Promise<unknown>;
  onRecord: (plotId?: string) => void;
}

export function HomeWorkspace({ tasks, plots, loading, busy, onNavigate, onComplete, onRecord }: HomeWorkspaceProps) {
  const today = todayIso();
  const overdue = tasks.filter((task) => task.due_on < today);
  const dueToday = tasks.filter((task) => task.due_on === today);
  const relevantIds = new Set([...overdue, ...dueToday].map((task) => task.plot_id));
  const relevantPlots = plots.filter((plot) => relevantIds.has(plot.id));
  const reminders = plots.filter((plot) => plot.harvest_safety?.in_safe_window);
  if (loading) return <div className="panel panel--loading">正在加载首页...</div>;

  return <section className="home-workspace">
    <div className="stat-grid home-summary">
      <div className="stat-card"><span>已逾期待办</span><strong>{overdue.length}</strong></div>
      <div className="stat-card"><span>今日待办</span><strong>{dueToday.length}</strong></div>
      <div className="stat-card"><span>已登记地块</span><strong>{plots.length}</strong></div>
      <div className="stat-card"><span>已记录农活</span><strong>{plots.reduce((sum, plot) => sum + plot.record_count, 0)}</strong></div>
    </div>
    <div className="home-task-grid">
      {[{ title: "已逾期", items: overdue }, { title: "今日待办", items: dueToday }].map((group) =>
        <section className="panel" key={group.title} aria-label={group.title}>
          <h3>{group.title}（{group.items.length}）</h3>
          {group.items.length === 0 ? <p className="stats-empty">{group.title === "已逾期" ? "没有已逾期待办。" : "今天没有到期的待办。"}</p> :
            <ul className="task-list">{group.items.map((task) => <li className="task-card" key={task.id}>
              <div className="task-card__head"><strong>{task.title}</strong>{task.is_demo && <span className="demo-badge">演示</span>}<span>{formatDate(task.due_on)}</span></div>
              <p>{task.plot_name || "未关联地块（杂事）"}</p>
              {task.notes && <p className="task-card__notes">{task.notes}</p>}
              <button className="ghost-button" type="button" disabled={busy} onClick={() => void onComplete(task)}>标记完成</button>
            </li>)}</ul>}
        </section>)}
    </div>
    <section className="panel">
      <h3>{tasks.length === 0 ? "还没有未完成待办" : `全部待办 ${tasks.length} 项`}</h3>
      <p>{tasks.length === 0 ? "把下一步要做的事记下来；也可以先看看今日农活建议。" : "可以到待办清单查看后续安排和最近完成的事项。"}</p>
      <div className="inline-actions"><button className="secondary-button" type="button" onClick={() => onNavigate("tasks")}>安排待办</button><button className="ghost-button" type="button" onClick={() => onNavigate("decision")}>查看今日农活建议</button></div>
    </section>
    <section className="panel">
      <h3>{plots.length === 0 ? "先登记一块地" : relevantPlots.length ? "今日与逾期待办相关地块" : "已登记地块"}</h3>
      {plots.length === 0 ? <p>还没有地块。登记后，就能按地块记农活、查看每一茬的收支。</p> :
        <ul className="home-plots">{(relevantPlots.length ? relevantPlots : plots).map((plot) => <li key={plot.id}>
          <strong>{plot.name}{plot.is_demo && <span className="demo-badge">演示</span>}</strong><span>{plot.area_mu} 亩 · {plot.active_season?.crop || "暂无进行中茬次"} · 农活 {plot.record_count} 笔 · 待办 {plot.open_task_count} 项</span>
          <button className="ghost-button" type="button" onClick={() => onRecord(plot.id)}>为{plot.name}记农活</button>
        </li>)}</ul>}
      <button className="secondary-button" type="button" onClick={() => onNavigate("plots")}>{plots.length ? "管理地块与茬次" : "登记地块"}</button>
    </section>
    {reminders.length > 0 && <section className="panel" aria-label="登记间隔期提醒">
      <h3>登记间隔期提醒</h3><p>复用登记施药日与间隔天数的计算结果，覆盖该地块全部茬次与作物；请核对具体产品标签。</p>
      <ul>{reminders.map((plot) => <li key={plot.id}>{plot.name}：登记的 {plot.harvest_safety!.material || "施药"} 间隔期尚未结束，按登记数据计算最早采收日为 {plot.harvest_safety!.earliest_harvest_on}。</li>)}</ul>
      <button className="ghost-button" type="button" onClick={() => onNavigate("ledger")}>查看施药台账</button>
    </section>}
  </section>;
}
