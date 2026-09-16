import { MapPin, Pencil, Plus, Trash2, X } from "lucide-react";
import { useState } from "react";

import { ConfirmDialog } from "./ConfirmDialog";
import { PlotInput } from "../hooks/usePlots";
import { Plot } from "../types";

const crops = ["玉米", "水稻", "小麦", "大豆", "番茄", "黄瓜", "辣椒", "苹果", "柑橘"];
const soilTypes = ["壤土", "砂壤土", "砂土", "黏土", "砾质土"];
const irrigations = ["井灌", "渠灌", "喷灌", "滴灌", "雨养"];

const emptyForm: PlotInput = {
  name: "",
  area_mu: 1,
  soil_type: "壤土",
  irrigation: "井灌",
  crop: "玉米",
  planted_on: null,
  notes: "",
};

interface PlotsWorkspaceProps {
  plots: Plot[];
  loading: boolean;
  busy: boolean;
  onCreate: (payload: PlotInput) => Promise<Plot | undefined>;
  onUpdate: (plotId: string, payload: PlotInput) => Promise<Plot | undefined>;
  onRemove: (plotId: string) => Promise<number | undefined>;
}

export function PlotsWorkspace(props: PlotsWorkspaceProps) {
  const { plots, loading, busy, onCreate, onUpdate, onRemove } = props;
  const [form, setForm] = useState<PlotInput>(emptyForm);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<Plot | null>(null);

  function setField<Key extends keyof PlotInput>(field: Key, value: PlotInput[Key]) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  function resetForm() {
    setForm(emptyForm);
    setEditingId(null);
  }

  async function handleSubmit() {
    if (!form.name.trim()) return;
    const saved = editingId ? await onUpdate(editingId, form) : await onCreate(form);
    if (saved) resetForm();
  }

  function handleEdit(plot: Plot) {
    setEditingId(plot.id);
    setForm({
      name: plot.name,
      area_mu: plot.area_mu,
      soil_type: plot.soil_type,
      irrigation: plot.irrigation,
      crop: plot.crop,
      planted_on: plot.planted_on,
      notes: plot.notes,
    });
  }

  async function confirmDelete() {
    if (!pendingDelete) return;
    const removed = await onRemove(pendingDelete.id);
    if (removed !== undefined) {
      if (editingId === pendingDelete.id) resetForm();
      setPendingDelete(null);
    }
  }

  return (
    <section className="workspace-grid workspace-grid--plots">
      <div className="panel">
        <div className="panel__header">
          <div>
            <h3>{editingId ? "编辑地块" : "新建地块"}</h3>
            <p>先把地块登记下来，后续的农事台账都挂在地块上。</p>
          </div>
        </div>

        <div className="field-grid">
          <label className="field">
            <span>地块名称</span>
            <div className="field-control">
              <input
                value={form.name}
                maxLength={32}
                placeholder="例如：东坡三亩地"
                onChange={(event) => setField("name", event.target.value)}
              />
            </div>
          </label>

          <label className="field">
            <span>面积（亩）</span>
            <div className="field-control">
              <input
                type="number"
                value={form.area_mu}
                min={0.1}
                max={100000}
                step={0.1}
                onChange={(event) => setField("area_mu", Number(event.target.value))}
              />
            </div>
          </label>

          <label className="field">
            <span>当前作物</span>
            <div className="field-control field-control--select">
              <select value={form.crop} onChange={(event) => setField("crop", event.target.value)}>
                {crops.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </div>
          </label>

          <label className="field">
            <span>土壤类型</span>
            <div className="field-control field-control--select">
              <select value={form.soil_type} onChange={(event) => setField("soil_type", event.target.value)}>
                {soilTypes.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </div>
          </label>

          <label className="field">
            <span>灌溉条件</span>
            <div className="field-control field-control--select">
              <select value={form.irrigation} onChange={(event) => setField("irrigation", event.target.value)}>
                {irrigations.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </div>
          </label>

          <label className="field">
            <span>定植或播种日期</span>
            <div className="field-control">
              <input
                type="date"
                value={form.planted_on ?? ""}
                onChange={(event) => setField("planted_on", event.target.value || null)}
              />
            </div>
          </label>

          <label className="field field--full">
            <span>备注</span>
            <div className="field-control field-control--textarea">
              <textarea
                value={form.notes}
                maxLength={300}
                placeholder="例如：去年种过小麦，低洼处易积水"
                onChange={(event) => setField("notes", event.target.value)}
              />
            </div>
          </label>
        </div>

        <div className="inline-actions">
          <button className="primary-button" type="button" onClick={() => void handleSubmit()} disabled={busy || !form.name.trim()}>
            {editingId ? <Pencil size={16} /> : <Plus size={16} />}
            {busy ? "保存中…" : editingId ? "保存修改" : "新建地块"}
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
            <h3>地块档案</h3>
            <p>共 {plots.length} 块地，按最近更新排序。</p>
          </div>
        </div>

        {plots.length === 0 && !loading ? (
          <p className="stats-empty">还没有地块，先在左边登记一块地吧。</p>
        ) : (
          <ul className="plot-list">
            {plots.map((plot) => (
              <li className="plot-card" key={plot.id}>
                <div className="plot-card__head">
                  <span className="plot-card__name">
                    <MapPin size={15} />
                    {plot.name}
                  </span>
                  <span className="stats-badge">{plot.area_mu} 亩</span>
                </div>
                <div className="plot-card__meta">
                  <span>{plot.crop}</span>
                  <span>{plot.soil_type}</span>
                  <span>{plot.irrigation}</span>
                  <span>{plot.planted_on ? `${plot.planted_on} 定植` : "未填定植日期"}</span>
                  <span>本季 {plot.record_count} 次作业</span>
                  {plot.harvest_safety?.in_safe_window && (
                    <span className="plot-card__safety">
                      {plot.harvest_safety.material} 安全期内，最早 {plot.harvest_safety.earliest_harvest_on} 采收
                    </span>
                  )}
                </div>
                {plot.notes && <p className="plot-card__notes">{plot.notes}</p>}
                <div className="inline-actions">
                  <button className="ghost-button" type="button" onClick={() => handleEdit(plot)} disabled={busy}>
                    <Pencil size={15} />
                    编辑
                  </button>
                  <button className="ghost-button danger" type="button" onClick={() => setPendingDelete(plot)} disabled={busy}>
                    <Trash2 size={15} />
                    删除
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <ConfirmDialog
        open={pendingDelete !== null}
        title="删除这个地块？"
        description={
          pendingDelete
            ? `「${pendingDelete.name}」及其 ${pendingDelete.record_count} 条农事台账记录会被永久删除，删除后无法恢复。`
            : ""
        }
        confirmLabel="确认删除"
        busy={busy}
        onConfirm={() => void confirmDelete()}
        onCancel={() => setPendingDelete(null)}
      />
    </section>
  );
}
