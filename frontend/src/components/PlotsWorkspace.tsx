import { CalendarPlus, MapPin, Pencil, Plus, Sprout, Trash2, X } from "lucide-react";
import { useMemo, useState } from "react";

import { ConfirmDialog } from "./ConfirmDialog";
import { SeasonInput, SeasonUpdateInput } from "../hooks/useSeasons";
import { PlotInput } from "../hooks/usePlots";
import { formatDate, todayIso } from "../lib/date";
import { Plot, PlotSeason } from "../types";

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

type Panel = "create" | "edit" | "new-season" | "end-season";

interface PlotsWorkspaceProps {
  plots: Plot[];
  seasons: PlotSeason[];
  loading: boolean;
  busy: boolean;
  seasonBusy: boolean;
  onCreate: (payload: PlotInput) => Promise<Plot | undefined>;
  onUpdate: (plotId: string, payload: PlotInput) => Promise<Plot | undefined>;
  onRemove: (plotId: string) => Promise<number | undefined>;
  onCreateSeason: (payload: SeasonInput) => Promise<PlotSeason | undefined>;
  onUpdateSeason: (seasonId: string, payload: SeasonUpdateInput) => Promise<PlotSeason | undefined>;
}

export function PlotsWorkspace(props: PlotsWorkspaceProps) {
  const {
    plots, seasons, loading, busy, seasonBusy, onCreate, onUpdate, onRemove,
    onCreateSeason, onUpdateSeason,
  } = props;
  const [panel, setPanel] = useState<Panel>("create");
  const [form, setForm] = useState<PlotInput>(emptyForm);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [targetPlotId, setTargetPlotId] = useState<string | null>(null);
  const [seasonForm, setSeasonForm] = useState({
    crop: "玉米",
    started_on: todayIso(),
    ended_on: todayIso(),
  });
  const [pendingDelete, setPendingDelete] = useState<Plot | null>(null);

  const seasonCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const season of seasons) {
      counts.set(season.plot_id, (counts.get(season.plot_id) ?? 0) + 1);
    }
    return counts;
  }, [seasons]);

  const targetPlot = plots.find((item) => item.id === targetPlotId) ?? null;
  const targetSeason = seasons.find((item) => item.plot_id === targetPlotId && item.active) ?? null;

  function setField<Key extends keyof PlotInput>(field: Key, value: PlotInput[Key]) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  function openCreate() {
    setForm(emptyForm);
    setEditingId(null);
    setTargetPlotId(null);
    setPanel("create");
  }

  function handleEdit(plot: Plot) {
    setEditingId(plot.id);
    setTargetPlotId(null);
    setForm({
      name: plot.name,
      area_mu: plot.area_mu,
      soil_type: plot.soil_type,
      irrigation: plot.irrigation,
      crop: plot.crop || "玉米",
      planted_on: plot.planted_on,
      notes: plot.notes,
    });
    setPanel("edit");
  }

  function openNewSeason(plot: Plot) {
    setTargetPlotId(plot.id);
    setSeasonForm({ crop: plot.crop || "玉米", started_on: todayIso(), ended_on: todayIso() });
    setPanel("new-season");
  }

  function openEndSeason(plot: Plot) {
    setTargetPlotId(plot.id);
    setSeasonForm({
      crop: plot.active_season?.crop ?? "",
      started_on: plot.active_season?.started_on ?? "",
      ended_on: todayIso(),
    });
    setPanel("end-season");
  }

  async function handlePlotSubmit() {
    if (!form.name.trim()) return;
    const saved = editingId ? await onUpdate(editingId, form) : await onCreate(form);
    if (saved) openCreate();
  }

  async function handleSeasonSubmit() {
    if (!targetPlotId) return;
    if (panel === "new-season") {
      if (!seasonForm.crop.trim()) return;
      const created = await onCreateSeason({
        plot_id: targetPlotId,
        crop: seasonForm.crop,
        started_on: seasonForm.started_on || null,
        notes: "",
      });
      if (created) openCreate();
      return;
    }
    if (!targetSeason) return;
    // 结束本茬：只把结束日填上，其余字段原样带回。
    const updated = await onUpdateSeason(targetSeason.id, {
      crop: targetSeason.crop,
      started_on: targetSeason.started_on,
      ended_on: seasonForm.ended_on || null,
      notes: targetSeason.notes,
    });
    if (updated) openCreate();
  }

  async function confirmDelete() {
    if (!pendingDelete) return;
    const removed = await onRemove(pendingDelete.id);
    if (removed !== undefined) {
      if (editingId === pendingDelete.id) openCreate();
      setPendingDelete(null);
    }
  }

  const panelTitle: Record<Panel, string> = {
    create: "新建地块",
    edit: "编辑地块",
    "new-season": "开始新茬",
    "end-season": "结束本茬",
  };

  return (
    <section className="workspace-grid workspace-grid--plots">
      <div className="panel">
        <div className="panel__header">
          <div>
            <h3>{panelTitle[panel]}</h3>
            <p>
              {panel === "create" && "先把地块登记下来；填的作物与日期会成为第一茬。"}
              {panel === "edit" && "作物与日期属于茬次，改茬请用卡片上的「开始新茬」。"}
              {panel === "new-season" && `为「${targetPlot?.name ?? ""}」开一茬新的作物。`}
              {panel === "end-season" &&
                (targetSeason
                  ? `结束「${targetPlot?.name ?? ""}」当前的 ${targetSeason.crop} 一茬。`
                  : "该地块当前没有进行中的茬次。")}
            </p>
          </div>
        </div>

        {panel === "new-season" || panel === "end-season" ? (
          <>
            <div className="field-grid">
              {panel === "new-season" && (
                <label className="field">
                  <span>作物</span>
                  <div className="field-control field-control--select">
                    <select
                      value={seasonForm.crop}
                      onChange={(event) => setSeasonForm((current) => ({ ...current, crop: event.target.value }))}
                    >
                      {crops.map((item) => (
                        <option key={item} value={item}>
                          {item}
                        </option>
                      ))}
                    </select>
                  </div>
                </label>
              )}

              <label className="field">
                <span>{panel === "new-season" ? "播种或定植日期" : "结束或收获日期"}</span>
                <div className="field-control">
                  <input
                    type="date"
                    value={panel === "new-season" ? seasonForm.started_on : seasonForm.ended_on}
                    onChange={(event) =>
                      setSeasonForm((current) =>
                        panel === "new-season"
                          ? { ...current, started_on: event.target.value }
                          : { ...current, ended_on: event.target.value },
                      )
                    }
                  />
                </div>
              </label>
            </div>

            <div className="inline-actions">
              <button
                className="primary-button"
                type="button"
                onClick={() => void handleSeasonSubmit()}
                disabled={seasonBusy || (panel === "end-season" && !targetSeason)}
              >
                {panel === "new-season" ? <Sprout size={16} /> : <CalendarPlus size={16} />}
                {seasonBusy ? "保存中…" : panel === "new-season" ? "确认开始新茬" : "确认结束本茬"}
              </button>
              <button className="ghost-button" type="button" onClick={openCreate} disabled={seasonBusy}>
                <X size={16} />
                返回新建地块
              </button>
            </div>
          </>
        ) : (
          <>
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

              {panel === "create" && (
                <>
                  <label className="field">
                    <span>第一茬作物</span>
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
                    <span>播种或定植日期</span>
                    <div className="field-control">
                      <input
                        type="date"
                        value={form.planted_on ?? ""}
                        onChange={(event) => setField("planted_on", event.target.value || null)}
                      />
                    </div>
                  </label>
                </>
              )}

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
              <button className="primary-button" type="button" onClick={() => void handlePlotSubmit()} disabled={busy || !form.name.trim()}>
                {editingId ? <Pencil size={16} /> : <Plus size={16} />}
                {busy ? "保存中…" : editingId ? "保存修改" : "新建地块"}
              </button>
              {panel === "edit" && (
                <button className="ghost-button" type="button" onClick={openCreate} disabled={busy}>
                  <X size={16} />
                  取消编辑
                </button>
              )}
            </div>
          </>
        )}
      </div>

      <div className="panel">
        <div className="panel__header">
          <div>
            <h3>地块列表</h3>
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
                  {plot.active_season ? (
                    <span className="plot-card__season">
                      当前：{plot.active_season.crop}
                      {plot.active_season.started_on ? `（${formatDate(plot.active_season.started_on)} 起）` : ""}
                    </span>
                  ) : (
                    <span>无进行中的茬次{plot.crop ? `，最近种的是 ${plot.crop}` : ""}</span>
                  )}
                  <span>{plot.soil_type}</span>
                  <span>{plot.irrigation}</span>
                  <span>本季 {plot.season_record_count} 次作业</span>
                  <span>共 {seasonCounts.get(plot.id) ?? 0} 茬</span>
                  {plot.harvest_safety?.in_safe_window && (
                    <span className="plot-card__safety">
                      {plot.harvest_safety.material} 安全期内，最早 {plot.harvest_safety.earliest_harvest_on} 采收
                    </span>
                  )}
                </div>
                {plot.notes && <p className="plot-card__notes">{plot.notes}</p>}
                <div className="inline-actions">
                  {plot.active_season ? (
                    <button className="ghost-button" type="button" onClick={() => openEndSeason(plot)} disabled={busy || seasonBusy}>
                      <CalendarPlus size={15} />
                      结束本茬
                    </button>
                  ) : (
                    <button className="ghost-button" type="button" onClick={() => openNewSeason(plot)} disabled={busy || seasonBusy}>
                      <Sprout size={15} />
                      开始新茬
                    </button>
                  )}
                  <button className="ghost-button" type="button" onClick={() => handleEdit(plot)} disabled={busy || seasonBusy}>
                    <Pencil size={15} />
                    编辑
                  </button>
                  <button className="ghost-button danger" type="button" onClick={() => setPendingDelete(plot)} disabled={busy || seasonBusy}>
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
            ? `「${pendingDelete.name}」及其 ${pendingDelete.record_count} 条农事台账记录、${pendingDelete.open_task_count} 项待办、${seasonCounts.get(pendingDelete.id) ?? 0} 茬记录会被永久删除，删除后无法恢复。`
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
