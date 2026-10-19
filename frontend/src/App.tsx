import { FormEvent, Suspense, lazy, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { AuthScreen } from "./components/AuthScreen";
import { AccountSecurity, PasswordRecovery } from "./components/AccountSecurity";
import { TrashWorkspace } from "./components/TrashWorkspace";
import { Sidebar } from "./components/Sidebar";
import { TopBar } from "./components/TopBar";
import { HomeWorkspace } from "./components/HomeWorkspace";
import { OnboardingPanel } from "./components/OnboardingPanel";
import { GuestAccountPanel } from "./components/GuestAccountPanel";
import { useAsyncGuard } from "./hooks/useAsyncGuard";
import { useAccountGuard } from "./hooks/useAccountGuard";
import { UnsavedChangesProvider, useRequestLeave } from "./hooks/useUnsavedChanges";
import { useDialogFocus } from "./hooks/useDialogFocus";
import { usePlots } from "./hooks/usePlots";
import { useSeasons } from "./hooks/useSeasons";
import { useTasks } from "./hooks/useTasks";
import { api, getErrorMessage } from "./lib/api";
import { formatAppVersion } from "./lib/appVersion";
import { todayIso } from "./lib/date";
import { LedgerDraft, taskLedgerDraft } from "./lib/taskLedger";
import { newSubmissionId } from "./lib/submission";
import { EconomicsFilters, FarmTask, FeatureKey, HealthPayload, User } from "./types";

const DecisionWorkspace = lazy(() =>
  import("./components/DecisionWorkspace").then((module) => ({ default: module.DecisionWorkspace })),
);
const PlotsWorkspace = lazy(() =>
  import("./components/PlotsWorkspace").then((module) => ({ default: module.PlotsWorkspace })),
);
const LedgerWorkspace = lazy(() =>
  import("./components/LedgerWorkspace").then((module) => ({ default: module.LedgerWorkspace })),
);
const TasksWorkspace = lazy(() =>
  import("./components/TasksWorkspace").then((module) => ({ default: module.TasksWorkspace })),
);
const StatsWorkspace = lazy(() =>
  import("./components/StatsWorkspace").then((module) => ({ default: module.StatsWorkspace })),
);

const defaultDecisionForm = { crop: "玉米", stage: "快速生长期", rainProb: 55, soilMoisture: 42, temperature: 24.5 };

export default function App() {
  return <UnsavedChangesProvider><AppContent /></UnsavedChangesProvider>;
}

function AppContent() {
  const requestLeave = useRequestLeave();
  const [health, setHealth] = useState<HealthPayload | null>(null);
  const [bootLoading, setBootLoading] = useState(true);
  const [error, setError] = useState("");
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [recovering, setRecovering] = useState(false);
  const [authForm, setAuthForm] = useState({ username: "", password: "", displayName: "" });
  const [user, setUser] = useState<User | null>(null);
  const [activeFeature, setActiveFeature] = useState<FeatureKey>("home");
  const [completedTask, setCompletedTask] = useState<FarmTask | null>(null);
  const [recordDraft, setRecordDraft] = useState<{ key: string; draft: LedgerDraft; task?: FarmTask } | null>(null);
  const [notice, setNotice] = useState("");
  const [workspaceRevision, setWorkspaceRevision] = useState(0);
  const [plotRequest, setPlotRequest] = useState<{ key: number; seasonPlotId?: string }>({ key: 0 });
  const [economicsFilters, setEconomicsFilters] = useState<EconomicsFilters>({ plot_id: "", season_id: "", year: "", data_scope: "real" });
  const [settingsName, setSettingsName] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [infoPanel, setInfoPanel] = useState<"help" | "about" | null>(null);
  const recordDialog = useRef<HTMLElement>(null);
  useDialogFocus(recordDialog, recordDraft !== null, () => requestLeave(() => { setRecordDraft(null); setError(""); }));
  const navigate = (feature: FeatureKey) => {
    if (feature === activeFeature) return;
    requestLeave(() => { setActiveFeature(feature); setSidebarOpen(false); setError(""); });
  };
  const [decisionForm, setDecisionForm] = useState(defaultDecisionForm);
  const [decisionResult, setDecisionResult] = useState("");
  const [selectedPlotId, setSelectedPlotId] = useState("");
  const [adviceSaved, setAdviceSaved] = useState(false);
  const accountCurrent = useAccountGuard(user?.id ?? null);
  const resetDecisionView = useCallback(() => {
    setDecisionForm(defaultDecisionForm);
    setDecisionResult("");
    setSelectedPlotId("");
    setAdviceSaved(false);
  }, []);

  const authAction = useAsyncGuard();
  const settingsAction = useAsyncGuard();
  const decisionAction = useAsyncGuard();
  const handleError = useCallback((message: string) => setError(message), []);
  const plots = usePlots({ onError: handleError, enabled: user !== null, accountId: user?.id ?? null });
  const tasks = useTasks({ onError: handleError, enabled: user !== null, accountId: user?.id ?? null, onChanged: plots.refresh });
  // 茬次变化会改动地块上的当前作物与本季计数，所以顺手刷新地块列表。
  const seasons = useSeasons({
    onError: handleError,
    enabled: user !== null,
    accountId: user?.id ?? null,
    onChanged: () => void plots.refresh(),
  });

  const loadMe = useCallback(async () => {
    const response = await api.get<{ success: true; user: User }>("/api/me");
    setUser(response.data.user);
    setSettingsName(response.data.user.display_name);
  }, []);

  useEffect(() => {
    async function bootstrap() {
      try {
        const response = await api.get<HealthPayload>("/api/health");
        setHealth(response.data);
        await api.get("/api/auth/csrf");
        try {
          await loadMe();
        } catch {
          // 未登录时 /api/me 返回 401；保留认证界面即可。
        }
      } catch (requestError) {
        setError(getErrorMessage(requestError, "后端未连接，请先启动服务。"));
      } finally {
        setBootLoading(false);
      }
    }

    void bootstrap();
  }, [loadMe]);

  const applyAuthenticatedUser = useCallback((nextUser: User) => {
    resetDecisionView();
    setError("");
    setSidebarOpen(false);
    setPlotRequest({ key: 0 });
    setWorkspaceRevision(0);
    setActiveFeature("home");
    setCompletedTask(null);
    setRecordDraft(null);
    setNotice("");
    setEconomicsFilters({ plot_id: "", season_id: "", year: "", data_scope: "real" });
    setUser(nextUser);
    setSettingsName(nextUser.display_name);
    setAuthForm({ username: "", password: "", displayName: "" });
  }, [resetDecisionView]);

  async function handleAuthSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await authAction.run(async () => {
      setError("");
      try {
        const endpoint = authMode === "login" ? "/api/auth/login" : "/api/auth/register";
        const payload =
          authMode === "login"
            ? { username: authForm.username, password: authForm.password }
            : {
                username: authForm.username,
                password: authForm.password,
                display_name: authForm.displayName,
              };
        const response = await api.post<{ success: true; token: string; user: User }>(endpoint, payload);
        applyAuthenticatedUser(response.data.user);
      } catch (requestError) {
        setError(getErrorMessage(requestError));
      }
    });
  }

  async function handleGuestLogin() {
    await authAction.run(async () => {
      setError("");
      try {
        const response = await api.post<{ success: true; token: string; user: User }>("/api/auth/guest");
        applyAuthenticatedUser(response.data.user);
      } catch (requestError) {
        setError(getErrorMessage(requestError));
      }
    });
  }

  async function handleSaveSettings() {
    await settingsAction.run(async () => {
      if (!settingsName.trim()) {
        setError("显示名称不能为空。");
        return;
      }
      try {
        const response = await api.patch<{ success: true; user: User }>("/api/me/profile", {
          display_name: settingsName,
        });
        setUser(response.data.user);
        setSettingsName(response.data.user.display_name);
        setError("");
      } catch (requestError) {
        setError(getErrorMessage(requestError));
      }
    });
  }

  async function handleLogout() {
    try {
      await api.post("/api/auth/logout");
    } catch {
      // 本地状态仍需清理，避免失效后端阻止用户退出。
    }
    setSidebarOpen(false);
    setUser(null);
    setAuthMode("login");
    setAuthForm({ username: "", password: "", displayName: "" });
    resetDecisionView();
    setCompletedTask(null);
    setRecordDraft(null);
    setNotice("");
    setEconomicsFilters({ plot_id: "", season_id: "", year: "", data_scope: "real" });
  }

  function returnToLogin(username: string, message = "") {
    resetDecisionView();
    setUser(null);
    setCompletedTask(null);
    setRecordDraft(null);
    setRecovering(false);
    setSidebarOpen(false);
    setError("");
    setNotice(message);
    setAuthMode("login");
    setAuthForm({ username, password: "", displayName: "" });
  }

  const taskSummary = useMemo(() => {
    const today = todayIso();
    return {
      open: tasks.items.length,
      dueToday: tasks.items.filter((item) => item.due_on === today).length,
      overdue: tasks.items.filter((item) => item.due_on < today).length,
    };
  }, [tasks.items]);

  async function handleToggleTask(task: FarmTask) {
    const updated = await tasks.toggle(task);
    if (updated?.done) {
      setCompletedTask(updated);
      setNotice("");
    } else if (updated && completedTask?.id === task.id) {
      setCompletedTask(null);
    }
    return updated;
  }

  function openTaskRecord(task: FarmTask) {
    if (!task.done) return;
    setError("");
    setRecordDraft({ key: newSubmissionId(), draft: taskLedgerDraft(task, seasons.items), task });
  }

  function openHomeRecord(plotId = "", seasonId?: string) {
    setError("");
    setNotice("");
    if (plots.items.length === 0) {
      setActiveFeature("plots");
      setNotice("请先登记地块，再记一笔农活。");
      return;
    }
    const today = todayIso();
    const candidates = seasons.items.filter((season) => season.plot_id === plotId
      && (!season.started_on || season.started_on <= today) && (!season.ended_on || today <= season.ended_on));
    const applicableId = seasonId ?? (candidates.length === 1 && candidates[0].started_on ? candidates[0].id : undefined);
    requestLeave(() => setRecordDraft({ key: newSubmissionId(), draft: { plot_id: plotId, happened_on: today, kind: "施肥", detail: "", ...(applicableId ? { season_id: applicableId } : {}) } }));
  }

  function handleFirstStep(step: "plot" | "season" | "record", plotId: string | null) {
    if (step === "record" && plotId) {
      openHomeRecord(plotId);
      return;
    }
    const needsSeason = step === "season" && plotId && !seasons.items.some((season) => season.plot_id === plotId);
    requestLeave(() => {
      setPlotRequest((current) => ({ key: current.key + 1, ...(needsSeason ? { seasonPlotId: plotId } : {}) }));
      setActiveFeature("plots");
    });
  }

  async function handleDemoChanged(loaded: boolean) {
    setPlotRequest({ key: 0 });
    setCompletedTask(null);
    setRecordDraft(null);
    setSelectedPlotId("");
    setEconomicsFilters({ plot_id: "", season_id: "", year: "", data_scope: loaded ? "demo" : "real" });
    setWorkspaceRevision((current) => current + 1);
    await Promise.all([plots.refresh(), seasons.refresh(), tasks.refresh()]);
  }

  async function handleSaveAdviceAsTask() {
    const plot = plots.items.find((item) => item.id === selectedPlotId);
    const created = await tasks.create({
      plot_id: selectedPlotId || null,
      title: `${plot?.crop ?? decisionForm.crop}：按今日建议安排农活`,
      due_on: todayIso(),
      notes: decisionResult.slice(0, 1000),
    });
    setAdviceSaved(created !== undefined);
  }

  /** 建地块会顺带建出第一茬、删地块会连带删茬，所以地块变更后要刷新茬次列表。 */
  async function withSeasonRefresh<T>(operation: () => Promise<T>): Promise<T> {
    const result = await operation();
    await seasons.refresh();
    return result;
  }

  function handleDecisionPlotChange(plotId: string) {
    setSelectedPlotId(plotId);
    const plot = plots.items.find((item) => item.id === plotId);
    if (plot) setDecisionForm((current) => ({ ...current, crop: plot.crop }));
  }

  async function handleDecisionSubmit() {
    await decisionAction.run(async () => {
      if (!accountCurrent()) return;
      try {
        setAdviceSaved(false);
        const response = await api.post<{ success: true; reply: string }>("/api/decision", {
          crop: decisionForm.crop,
          stage: decisionForm.stage,
          rain_prob: decisionForm.rainProb,
          soil_moisture: decisionForm.soilMoisture,
          temperature: decisionForm.temperature,
        });
        if (!accountCurrent()) return;
        setDecisionResult(response.data.reply);
        setError("");
      } catch (requestError) {
        if (accountCurrent()) setError(getErrorMessage(requestError));
      }
    });
  }

  if (bootLoading) {
    return <div className="app-loading">正在加载云寻...</div>;
  }
  if (!health) {
    return <div className="app-loading">{error || "后端未连接，请先启动服务。"}</div>;
  }
  if (!user) {
    return (
      <div className="app-shell app-shell--auth">
        {error && <div className="toast-banner">{error}</div>}
        {notice && <p className="panel" role="status">{notice}</p>}
        {recovering ? <PasswordRecovery onReturnToLogin={returnToLogin} /> : <AuthScreen
          mode={authMode}
          loading={authAction.busy}
          form={authForm}
          onModeChange={setAuthMode}
          onChange={(field, value) => setAuthForm((current) => ({ ...current, [field]: value }))}
          onSubmit={handleAuthSubmit}
          onGuestLogin={() => void handleGuestLogin()}
          onRecovery={() => { setRecovering(true); setError(""); setNotice(""); setAuthForm({ username: "", password: "", displayName: "" }); }}
        />}
      </div>
    );
  }

  return (
    <div className="app-shell">
      {error && <div className="toast-banner">{error}</div>}
      <button
        className={sidebarOpen ? "sidebar-backdrop is-visible" : "sidebar-backdrop"}
        type="button"
        aria-label="关闭导航"
        onClick={() => setSidebarOpen(false)}
      />
      <Sidebar
        user={user}
        activeFeature={activeFeature}
        settingsName={settingsName}
        mobileOpen={sidebarOpen}
        settingsBusy={settingsAction.busy}
        onClose={() => setSidebarOpen(false)}
        onFeatureChange={navigate}
        onSettingsNameChange={setSettingsName}
        onOpenHelp={() => setInfoPanel("help")}
        onOpenAbout={() => setInfoPanel("about")}
        onSaveSettings={() => void handleSaveSettings()}
        onLogout={() => requestLeave(() => { void handleLogout(); })}
      />

      <main className="workspace">
        <TopBar
          health={health}
          activeFeature={activeFeature}
          taskSummary={taskSummary}
          onOpenNavigation={() => setSidebarOpen(true)}
        />

        {activeFeature === "home" && <section className="panel home-actions home-quick-entry">
          <div><h3>今天的农活</h3><p>完成待办只更新清单，实际农活由你确认记账。</p></div>
          <button className="primary-button" type="button" onClick={() => openHomeRecord()}>记一笔农活</button>
        </section>}
        {user.is_guest && <GuestAccountPanel user={user}
          onSaved={(saved) => { setUser(saved); setSettingsName(saved.display_name); setError(""); setNotice(`账号已保存为 ${saved.username}，原有数据全部保留。`); }}
          onReturnToLogin={(username) => { void handleLogout().then(() => { setAuthMode("login"); setAuthForm({ username, password: "", displayName: "" }); }); }} />}
        {activeFeature !== "account" && activeFeature !== "trash" && <OnboardingPanel key={user.id} user={user} plots={plots.items} seasons={seasons.items}
          onStep={handleFirstStep} onNavigate={navigate} onDemoChanged={handleDemoChanged}
          onDemoStats={() => requestLeave(() => { setEconomicsFilters({ plot_id: "", season_id: "", year: "", data_scope: "demo" }); setActiveFeature("stats"); })} />}
        {activeFeature === "account" && !user.is_guest && <AccountSecurity key={user.id} onReturnToLogin={(message) => returnToLogin(user.username, message)} />}
        {notice && <p className="panel" role="status">{notice}</p>}
        {completedTask && <section className="panel completed-task" aria-label="待办完成提示">
          <h3>已完成：{completedTask.title}</h3>
          <p>待办已完成，尚未因此创建农事记录。需要记账时，请核对实际作业后保存。</p>
          <div className="inline-actions"><button className="primary-button" type="button" onClick={() => requestLeave(() => openTaskRecord(completedTask))}>顺便记入台账</button><button className="ghost-button" type="button" onClick={() => setCompletedTask(null)}>暂不记账</button></div>
        </section>}

        {activeFeature === "home" && <HomeWorkspace tasks={tasks.items} plots={plots.items}
          loading={plots.loading || tasks.loading} busy={tasks.busy} onNavigate={navigate}
          onComplete={handleToggleTask} onRecord={openHomeRecord} />}

        {activeFeature === "decision" && (
          <Suspense fallback={<div className="panel panel--loading">正在加载今日农活模块...</div>}>
            <DecisionWorkspace
              crop={decisionForm.crop}
              stage={decisionForm.stage}
              rainProb={decisionForm.rainProb}
              soilMoisture={decisionForm.soilMoisture}
              temperature={decisionForm.temperature}
              result={decisionResult}
              busy={decisionAction.busy}
              plots={plots.items}
              selectedPlotId={selectedPlotId}
              onChange={(field, value) => setDecisionForm((current) => ({ ...current, [field]: value }))}
              onPlotChange={handleDecisionPlotChange}
              onSubmit={() => void handleDecisionSubmit()}
              onSaveAdviceAsTask={() => void handleSaveAdviceAsTask()}
              adviceSaved={adviceSaved}
            />
          </Suspense>
        )}

        {activeFeature === "ledger" && (
          <Suspense fallback={<div className="panel panel--loading">正在加载农事台账...</div>}>
            <LedgerWorkspace
              key={`${user.id}:${workspaceRevision}`}
              plots={plots.items}
              seasons={seasons.items}
              onError={handleError}
              onRecordsChanged={plots.refresh}
              onQuickTask={tasks.create}
            />
          </Suspense>
        )}

        {activeFeature === "plots" && (
          <Suspense fallback={<div className="panel panel--loading">正在加载地块档案...</div>}>
            <PlotsWorkspace
              key={`${workspaceRevision}:${plotRequest.key}`} initialSeasonPlotId={plotRequest.seasonPlotId}
              plots={plots.items}
              seasons={seasons.items}
              loading={plots.loading}
              busy={plots.busy}
              seasonBusy={seasons.busy}
              onCreate={(payload) => withSeasonRefresh(() => plots.create(payload))}
              onUpdate={(plotId, payload) => withSeasonRefresh(() => plots.update(plotId, payload))}
              onRemove={async (plotId, revision) => {
                const result = await withSeasonRefresh(() => plots.remove(plotId, revision));
                if (result !== undefined) {
                  await tasks.refresh();
                  setCompletedTask(null); setRecordDraft(null); setSelectedPlotId("");
                  setEconomicsFilters({ plot_id: "", season_id: "", year: "", data_scope: "real" });
                  setDecisionForm((current) => ({ ...current, crop: "玉米" }));
                  setNotice("地块已移入回收站，茬次、台账和待办完整保留，可从回收站恢复。");
                }
                return result;
              }}
              onCreateSeason={async (payload) => {
                const result = await seasons.create(payload);
                if (result) setPlotRequest((current) => ({ key: current.key }));
                return result;
              }}
              onUpdateSeason={seasons.update}
              onRecord={openHomeRecord}
            />
          </Suspense>
        )}

        {activeFeature === "tasks" && (
          <Suspense fallback={<div className="panel panel--loading">正在加载农事待办...</div>}>
            <TasksWorkspace
              key={workspaceRevision}
              tasks={tasks.items}
              recentDone={tasks.recentDone}
              plots={plots.items}
              loading={tasks.loading}
              busy={tasks.busy}
              onCreate={tasks.create}
              onUpdate={tasks.update}
              onToggle={handleToggleTask}
              onRecord={(task) => requestLeave(() => openTaskRecord(task))}
              onRemove={tasks.remove}
            />
          </Suspense>
        )}

        {activeFeature === "trash" && <TrashWorkspace onChanged={async () => {
          setNotice("");
          setCompletedTask(null); setRecordDraft(null); setSelectedPlotId("");
          setDecisionForm((current) => ({ ...current, crop: "玉米" }));
          setEconomicsFilters({ plot_id: "", season_id: "", year: "", data_scope: "real" });
          await Promise.all([plots.refresh(), seasons.refresh(), tasks.refresh()]);
          setWorkspaceRevision((current) => current + 1);
        }} />}
        {activeFeature === "stats" && (
          <Suspense fallback={<div className="panel panel--loading">正在加载统计面板...</div>}>
            <StatsWorkspace key={workspaceRevision} onError={handleError} plots={plots.items} seasons={seasons.items}
              filters={economicsFilters} onFiltersChange={setEconomicsFilters}
              onRecordsChanged={plots.refresh} onQuickTask={tasks.create} />
          </Suspense>
        )}

      </main>

      {recordDraft && <div className="dialog-backdrop"><section ref={recordDialog} tabIndex={-1} className="record-dialog" role="dialog" aria-modal="true" aria-labelledby="record-dialog-title">
        <h3 id="record-dialog-title">{recordDraft.task ? "从已完成待办记账" : "记一笔农活"}</h3>
        {recordDraft.task && <p>来自「{recordDraft.task.title}」。日期取实际完成日；请核对作业类型、日期和内容。{!recordDraft.task.plot_id && "这条是杂事，请先选择地块。"}取消或保存失败不会重新打开待办。</p>}
        {error && <p className="form-warning" role="alert">{error}</p>}
        {plots.items.length === 0 ? <><p>农事台账需要关联地块，请先登记一块地。</p><button className="primary-button" type="button" onClick={() => { setRecordDraft(null); setActiveFeature("plots"); }}>登记地块</button><button className="ghost-button" type="button" onClick={() => setRecordDraft(null)}>取消记账</button></> :
          <Suspense fallback={<p>正在加载记账表单...</p>}><LedgerWorkspace key={recordDraft.key}
            plots={plots.items} seasons={seasons.items} initialDraft={recordDraft.draft} formOnly
            initialSubmissionId={recordDraft.task?.id}
            onError={handleError} onRecordsChanged={plots.refresh} onQuickTask={tasks.create}
            onCancel={() => { setRecordDraft(null); setError(""); }}
            onSaved={() => { setRecordDraft(null); setCompletedTask(null); setNotice("已记入台账，可到统计面板查看收支。"); }} />
          </Suspense>}
      </section></div>}

      {infoPanel && <div className="dialog-backdrop" role="presentation" onMouseDown={() => setInfoPanel(null)}><section className="confirm-dialog info-dialog" role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}><button className="ghost-button info-dialog__close" type="button" onClick={() => setInfoPanel(null)} aria-label="关闭">关闭</button>{infoPanel === "help" ? <><h3>使用帮助</h3><p>注册、登录或使用访客模式后，可以登记地块、记录农事并生成当天农活建议。</p><ul><li>首页和地块卡片可直接记一笔农活，补录日期会重新匹配茬次。费用等可选信息可稍后编辑补全。</li><li>记账失败保留填写内容，请检查网络后重试。未保存离开时可选择继续填写；草稿只在当前页面内，退出或确认放弃后不保留。</li><li>完成待办后可选择顺便记入台账，核对实际日期和内容后保存；取消不会撤销完成。</li><li>地块档案登记面积、土壤和灌溉条件，每块地按茬次记录当季作物。</li><li>结束一茬后可以开始新茬，投入产出按茬次分开算，不混季。</li><li>农事台账按地块记录每次作业的日期、用量、费用，采收还能记产量和单价。</li><li>采收提醒按同一地块全部相关登记施药记录取最晚日期，换茬不会解除未结束的提醒。仅核对登记日期和天数，请以具体产品标签为准。</li><li>农事待办把接下来要做的事排好，逾期会在顶栏标红。</li><li>地块或台账删除后可到回收站恢复；地块关联的茬次、台账和待办一起保留。回收站没有自动清理，最终删除后不能恢复。</li><li>今日农活可以直接选地块带出作物和土壤条件。</li><li>每茬收支差额等于已记录收入减已记录支出，不自动包含未登记的人工、地租。费用未填与 0 元分别提示，采收收入仅包含产量和单价均完整的记录。</li><li>统计年度按作业日期划分，跨年茬次只计所选年份；点击金额或待补录数量可追溯台账，返回保留筛选。</li><li>访客可保存为正式账号，原数据保留。演示资料有明确标识，可单独清空；新注册账号默认没有演示资料。</li><li>台账和每茬收支可按当前筛选导出 CSV，包含全部匹配记录。CSV 用于留档和分析，不能作为完整数据库恢复备份。</li><li>显示名称可以随时在个人设置里修改。</li><li>正式账号可在「账号安全」验证原密码后改密，或生成本人离线保管的一次性恢复码。改密或重置会退出全部设备，需重新生成恢复码。</li><li>忘记密码可在登录页使用恢复码；没有恢复码时请联系部署者线下核验身份后辅助恢复，无法核验时不能恢复。访客须先保存账号。</li></ul></> : <><h3>关于软件</h3><p>软件全称：{health.app_name}</p><p>软件简称：云寻</p><p>软件版本：{formatAppVersion(health.app_version)}</p><p>主要功能：首页、地块与茬次档案、农事台账与待办、每茬已记录收支及追溯、CSV 导出、回收站、账号安全与本机农活建议。</p></>}</section></div>}
    </div>
  );
}
