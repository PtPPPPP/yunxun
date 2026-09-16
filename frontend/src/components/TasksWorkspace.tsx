import { CalendarPlus, Check, Pencil, RotateCcw, Trash2, X } from "lucide-react";
import { useMemo, useState } from "react";

import { ConfirmDialog } from "./ConfirmDialog";
import { TaskInput } from "../hooks/useTasks";
import { addDays, diffDays, formatDate, todayIso } from "../lib/date";
import { FarmTask, Plot } from "../types";

interface TasksWorkspaceProps {
  tasks: FarmTask[];
  recentDone: FarmTask[];
  plots: Plot[];
  loading: boolean;
  busy: boolean;
  onCreate: (payload: TaskInput) => Promise<FarmTask | undefined>;
  onUpdate: (taskId: string, payload: TaskInput, done: boolean) => Promise<FarmTask | undefined>;
  onToggle: (task: FarmTask) => Promise<FarmTask | undefined>;
  onRemove: (taskId: string) => Promise<boolean>;
}

function groupLabel(dueOn: string, today: string): string {
  const offset = diffDays(today, dueOn);
  if (offset < 0) return "已逾期";
  if (offset === 0) return "今天";
  if (offset <= 7) return "本周内";
  return "更远";
}

export function TasksWorkspace(props: TasksWorkspaceProps) {
  const { tasks, recentDone, plots, loading, busy, onCreate, onUpdate, onToggle, onRemove } = props;
  const today = todayIso();
  const [form, setForm] = useState<TaskInput>({
    plot_id: null,
    title: "",
    due_on: addDays(today, 1),
    notes: "",
  });
  const [editingId, setEditingId] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<FarmTask | null>(null);

  const grouped = useMemo(() => {
    const order = ["已逾期", "今天", "本周内", "更远"];
    const buckets = new Map<string, FarmTask[]>(order.map((label) => [label, []]));
    for (const task of tasks) {
      buckets.get(groupLabel(task.due_on, today))?.push(task);
    }
    return order
      .map((label) => ({ label, items: buckets.get(label) ?? [] }))
      .filter((group) => group.items.length > 0);
  }, [tasks, today]);

  function resetForm() {
    setForm({ plot_id: null, title: "", due_on: addDays(today, 1), notes: "" });
    setEditingId(null);
  }

  async function handleSubmit() {
    if (!form.title.trim()) return;
    const saved = editingId ? await onUpdate(editingId, form, false) : await onCreate(form);
    if (saved) resetForm();
  }

  function handleEdit(task: FarmTask) {
    setEditingId(task.id);
    setForm({
      plot_id: task.plot_id,
      title: task.title,
      due_on: task.due_on,
      notes: task.notes,
    });
  }

  async function confirmDelete() {
    if (!pendingDelete) return;
    const removed = await onRemove(pendingDelete.id);
    if (removed) {
      if (editingId === pendingDelete.id) resetForm();
      setPendingDelete(null);
    }
  }

  return (
    <section className="workspace-grid workspace-grid--tasks">
      <div className="panel">
        <div className="panel__header">
          <div>
            <h3>{editingId ? "编辑待办" : "新增待办"}</h3>
            <p>把接下来要做的事记下来，到期会在顶栏提醒。</p>
          </div>
        </div>

        <div className="field-stack">
          <label className="field">
            <span>要做的事</span>
            <div className="field-control">
              <input
                value={form.title}
                maxLength={60}
                placeholder="例如：追肥后 7 天复查长势"
                onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))}
              />
            </div>
          </label>

          <label className="field">
            <span>到期日</span>
            <div className="field-control">
              <input
                type="date"
                value={form.due_on}
                onChange={(event) => setForm((current) => ({ ...current, due_on: event.target.value }))}
              />
            </div>
          </label>

          <label className="field">
            <span>关联地块（可不选）</span>
            <div className="field-control field-control--select">
              <select
                value={form.plot_id ?? ""}
                onChange={(event) => setForm((current) => ({ ...current, plot_id: event.target.value || null }))}
              >
                <option value="">不关联地块</option>
                {plots.map((plot) => (
                  <option key={plot.id} value={plot.id}>
                    {plot.name}
                  </option>
                ))}
              </select>
            </div>
          </label>

          <label className="field">
            <span>备注</span>
            <div className="field-control field-control--textarea">
              <textarea
                value={form.notes}
                maxLength={1000}
                placeholder="补充说明，也可以粘贴整段农活建议"
                onChange={(event) => setForm((current) => ({ ...current, notes: event.target.value }))}
              />
            </div>
          </label>
        </div>

        <div className="inline-actions">
          <button className="primary-button" type="button" onClick={() => void handleSubmit()} disabled={busy || !form.title.trim()}>
            {editingId ? <Pencil size={16} /> : <CalendarPlus size={16} />}
            {busy ? "保存中…" : editingId ? "保存修改" : "新增待办"}
          </button>
          {editingId && (
            <button className="ghost-button" type="button" onClick={resetForm} disabled={busy}>
              <X size={16} />
              取消编辑
            </button>
          )}
        </div>
      </div>

      <div className="panel">
        <div className="panel__header">
          <div>
            <h3>待办清单</h3>
            <p>共 {tasks.length} 项未完成。</p>
          </div>
        </div>

        {tasks.length === 0 && !loading ? (
          <p className="stats-empty">没有待办事项，先在左边加一条吧。</p>
        ) : (
          grouped.map((group) => (
            <div className="task-group" key={group.label}>
              <div className={group.label === "已逾期" ? "task-group__title task-group__title--overdue" : "task-group__title"}>
                {group.label}（{group.items.length}）
              </div>
              <ul className="task-list">
                {group.items.map((task) => (
                  <li className="task-card" key={task.id}>
                    <div className="task-card__head">
                      <span className="task-card__title">{task.title}</span>
                      <span className="stats-record__time">{formatDate(task.due_on)}</span>
                    </div>
                    {task.plot_name && <div className="plot-card__meta"><span>{task.plot_name}</span></div>}
                    {task.notes && <p className="task-card__notes">{task.notes}</p>}
                    <div className="inline-actions">
                      <button className="ghost-button" type="button" onClick={() => void onToggle(task)} disabled={busy}>
                        <Check size={15} />
                        标记完成
                      </button>
                      <button className="ghost-button" type="button" onClick={() => handleEdit(task)} disabled={busy}>
                        <Pencil size={15} />
                        编辑
                      </button>
                      <button className="ghost-button danger" type="button" onClick={() => setPendingDelete(task)} disabled={busy}>
                        <Trash2 size={15} />
                        删除
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          ))
        )}

        {recentDone.length > 0 && (
          <div className="task-group">
            <div className="task-group__title">最近完成</div>
            <ul className="task-list">
              {recentDone.map((task) => (
                <li className="task-card task-card--done" key={task.id}>
                  <div className="task-card__head">
                    <span className="task-card__title">{task.title}</span>
                    <span className="stats-record__time">{formatDate(task.due_on)}</span>
                  </div>
                  <div className="inline-actions">
                    <button className="ghost-button" type="button" onClick={() => void onToggle(task)} disabled={busy}>
                      <RotateCcw size={15} />
                      重新打开
                    </button>
                    <button className="ghost-button danger" type="button" onClick={() => setPendingDelete(task)} disabled={busy}>
                      <Trash2 size={15} />
                      删除
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      <ConfirmDialog
        open={pendingDelete !== null}
        title="删除这条待办？"
        description={pendingDelete ? `「${pendingDelete.title}」会被永久删除，删除后无法恢复。` : ""}
        confirmLabel="确认删除"
        busy={busy}
        onConfirm={() => void confirmDelete()}
        onCancel={() => setPendingDelete(null)}
      />
    </section>
  );
}
