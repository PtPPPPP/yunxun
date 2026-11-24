import { Suspense, lazy, useCallback, useMemo, useRef, useState } from "react";

import { AuthScreen } from "./components/AuthScreen";
import { AppInfoDialog } from "./components/AppInfoDialog";
import { AccountSecurity, PasswordRecovery } from "./components/AccountSecurity";
import { TrashWorkspace } from "./components/TrashWorkspace";
import { Sidebar } from "./components/Sidebar";
import { TopBar } from "./components/TopBar";
import { HomeWorkspace } from "./components/HomeWorkspace";
import { OnboardingPanel } from "./components/OnboardingPanel";
import { GuestAccountPanel } from "./components/GuestAccountPanel";
import { useAsyncGuard } from "./hooks/useAsyncGuard";
import { useAccountGuard } from "./hooks/useAccountGuard";
import { SessionBoundary } from "./hooks/useSessionBoundary";
import { useAuthSession, SessionResetReason } from "./hooks/useAuthSession";
import { UnsavedChangesProvider, useRequestLeave } from "./hooks/useUnsavedChanges";
import { useDialogFocus } from "./hooks/useDialogFocus";
import { usePlots } from "./hooks/usePlots";
import { useSeasons } from "./hooks/useSeasons";
import { useTasks } from "./hooks/useTasks";
import { api, getErrorMessage } from "./lib/api";
import { matchRecordSeason } from "./lib/recordSeason";
import { todayIso } from "./lib/date";
import { LedgerDraft, taskLedgerDraft } from "./lib/taskLedger";
import { newSubmissionId } from "./lib/submission";
import { EconomicsFilters, FarmTask, FeatureKey } from "./types";

const DecisionWorkspace = lazy(() =>
  import("./components/DecisionWorkspace").then((module) => ({ default: module.DecisionWorkspace })),
);
const PlotsWorkspace = lazy(() =>
  import("./components/PlotsWorkspace").then((module) => ({ default: module.PlotsWorkspace })),
);
const LedgerWorkspace = lazy(() =>
  import("./components/LedgerWorkspace").then((module) => ({ default: module.LedgerWorkspace })),
);
const FarmRecordForm = lazy(() =>
  import("./components/FarmRecordForm").then((module) => ({ default: module.FarmRecordForm })),
);
const TasksWorkspace = lazy(() =>
  import("./components/TasksWorkspace").then((module) => ({ default: module.TasksWorkspace })),
);
const StatsWorkspace = lazy(() =>
  import("./components/StatsWorkspace").then((module) => ({ default: module.StatsWorkspace })),
);

const defaultDecisionForm = { crop: "玉米", stage: "快速生长期", rainProb: 55, soilMoisture: 42, temperature: 24.5 };

type DecisionAdvice = {
  input: typeof defaultDecisionForm;
  plotId: string;
  plotName: string;
  reply: string;
  saved: boolean;
};

export default function App() {
  return <SessionBoundary><UnsavedChangesProvider><AppContent /></UnsavedChangesProvider></SessionBoundary>;
}

function AppContent() {
  const requestLeave = useRequestLeave();
  const [error, setError] = useState("");
  const [activeFeature, setActiveFeature] = useState<FeatureKey>("home");
  const [completedTask, setCompletedTask] = useState<FarmTask | null>(null);
  const [quickEntry, setQuickEntry] = useState<{ key: string; draft: LedgerDraft; task?: FarmTask } | null>(null);
  const [notice, setNotice] = useState("");
  const [workspaceRevision, setWorkspaceRevision] = useState(0);
  const [plotRequest, setPlotRequest] = useState<{ key: number; seasonPlotId?: string }>({ key: 0 });
  const [economicsFilters, setEconomicsFilters] = useState<EconomicsFilters>({ plot_id: "", season_id: "", year: "", data_scope: "real" });
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [infoPanel, setInfoPanel] = useState<"help" | "about" | null>(null);
  const recordDialog = useRef<HTMLElement>(null);
  useDialogFocus(recordDialog, quickEntry !== null, () => requestLeave(closeQuickEntry));
  const navigate = (feature: FeatureKey) => {
    if (feature === activeFeature) return;
    requestLeave(() => { setActiveFeature(feature); setSidebarOpen(false); setError(""); });
  };
  const [decisionForm, setDecisionForm] = useState(defaultDecisionForm);
  const [decisionResult, setDecisionResult] = useState<DecisionAdvice | null>(null);
  const decisionResultRef = useRef<DecisionAdvice | null>(null);
  const decisionVersion = useRef(0);
  const generatingVersion = useRef<number | null>(null);
  const [decisionBusy, setDecisionBusy] = useState(false);
  const adviceSaveAction = useAsyncGuard();
  const updateDecisionResult = useCallback((result: DecisionAdvice | null) => {
    decisionResultRef.current = result;
    setDecisionResult(result);
  }, []);
  const invalidateDecision = useCallback(() => {
    // 输入即使改回原值也换版，不能让旧请求重新激活建议。
    ++decisionVersion.current;
    updateDecisionResult(null);
    setDecisionBusy(false);
  }, [updateDecisionResult]);
  const [selectedPlotId, setSelectedPlotId] = useState("");
  const resetDecisionView = useCallback(() => {
    setDecisionForm(defaultDecisionForm);
    invalidateDecision();
    setSelectedPlotId("");
  }, [invalidateDecision]);

  const resetWorkspace = useCallback((reason: SessionResetReason) => {
    resetDecisionView();
    setSidebarOpen(false);
    setCompletedTask(null);
    setQuickEntry(null);
    if (reason !== "expired") setEconomicsFilters({ plot_id: "", season_id: "", year: "", data_scope: "real" });
    if (reason === "login") {
      setPlotRequest({ key: 0 });
      setWorkspaceRevision(0);
      setActiveFeature("home");
    }
    if (reason === "logout") setInfoPanel(null);
  }, [resetDecisionView]);
  const {
    health, bootLoading, user, logoutPending, logoutBusy, retryLogout,
    authMode, setAuthMode, authForm, setAuthForm, authBusy, handleAuthSubmit, handleGuestLogin,
    settingsName, setSettingsName, settingsBusy, handleSaveSettings, handleLogout,
    recovering, startRecovery, returnToLogin, acceptGuestUpgrade,
  } = useAuthSession({ onError: setError, onNotice: setNotice, onSessionReset: resetWorkspace });
  const accountId = user?.id ?? null;
  const accountCurrent = useAccountGuard(accountId);
  const plots = usePlots({ accountId, onError: setError });
  const tasks = useTasks({ accountId, onError: setError, onChanged: plots.refresh });
  const seasons = useSeasons({ accountId, onError: setError, onChanged: plots.refresh });

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
    setQuickEntry({ key: newSubmissionId(), draft: taskLedgerDraft(task, seasons.items), task });
  }

  function closeQuickEntry() {
    setQuickEntry(null);
    setError("");
  }

  function openQuickRecord(plotId = "", seasonId?: string) {
    setError("");
    setNotice("");
    if (plots.items.length === 0) {
      setActiveFeature("plots");
      setNotice("请先登记地块，再记一笔农活。");
      return;
    }
    const recordDate = todayIso();
    const draftSeasonId = seasonId ?? matchRecordSeason(seasons.items, plotId, recordDate).season?.id;
    const draft: LedgerDraft = {
      plot_id: plotId,
      happened_on: recordDate,
      kind: "施肥",
      detail: "",
      ...(draftSeasonId ? { season_id: draftSeasonId } : {}),
    };
    requestLeave(() => setQuickEntry({ key: newSubmissionId(), draft }));
  }

  function handleFirstStep(step: "plot" | "season" | "record", plotId: string | null) {
    if (step === "record" && plotId) {
      openQuickRecord(plotId);
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
    setQuickEntry(null);
    invalidateDecision();
    setSelectedPlotId("");
    setEconomicsFilters({ plot_id: "", season_id: "", year: "", data_scope: loaded ? "demo" : "real" });
    setWorkspaceRevision((current) => current + 1);
    await Promise.all([plots.refresh(), seasons.refresh(), tasks.refresh()]);
  }

  async function handleSaveAdviceAsTask() {
    // 标题、地块和内容始终从同一次生成的快照读取。
    const advice = decisionResultRef.current;
    if (!advice || advice.saved || !accountCurrent()) return;
    await adviceSaveAction.run(async () => {
      const created = await tasks.create({
        plot_id: advice.plotId || null,
        title: `${advice.input.crop}：按今日建议安排农活`,
        due_on: todayIso(),
        notes: `生成时地块：${advice.plotName || "未关联地块"}\n${advice.reply}`.slice(0, 1000),
      });
      if (!accountCurrent() || decisionResultRef.current !== advice) return;
      if (created) updateDecisionResult({ ...advice, saved: true });
    });
  }

  /** 建地块会顺带建出第一茬、删地块会连带删茬，所以地块变更后要刷新茬次列表。 */
  async function withSeasonRefresh<T>(operation: () => Promise<T>): Promise<T> {
    const result = await operation();
    await seasons.refresh();
    return result;
  }

  function handleDecisionChange(field: keyof typeof defaultDecisionForm, value: string | number) {
    if (adviceSaveAction.isRunning() || decisionForm[field] === value) return;
    invalidateDecision();
    setError("");
    setDecisionForm((current) => ({ ...current, [field]: value }));
  }

  function handleDecisionPlotChange(plotId: string) {
    if (adviceSaveAction.isRunning() || selectedPlotId === plotId) return;
    invalidateDecision();
    setError("");
    setSelectedPlotId(plotId);
    const plot = plots.items.find((item) => item.id === plotId);
    if (plot) setDecisionForm((current) => ({ ...current, crop: plot.crop }));
  }

  async function handleDecisionSubmit() {
    // 同版本重复点击忽略；改过输入后允许新版本先完成。
    if (!accountCurrent() || adviceSaveAction.isRunning() || generatingVersion.current === decisionVersion.current) return;
    const version = ++decisionVersion.current;
    generatingVersion.current = version;
    const input = { ...decisionForm };
    const plotId = selectedPlotId;
    const plotName = plots.items.find((item) => item.id === plotId)?.name ?? "";
    updateDecisionResult(null);
    setDecisionBusy(true);
    setError("");
    const current = () => accountCurrent() && decisionVersion.current === version;
    try {
      const response = await api.post<{ success: true; reply: string }>("/api/decision", {
        crop: input.crop,
        stage: input.stage,
        rain_prob: input.rainProb,
        soil_moisture: input.soilMoisture,
        temperature: input.temperature,
      });
      if (!current()) return;
      updateDecisionResult({ input, plotId, plotName, reply: response.data.reply, saved: false });
      setError("");
    } catch (requestError) {
      if (current()) setError(getErrorMessage(requestError));
    } finally {
      if (current()) setDecisionBusy(false);
      if (generatingVersion.current === version) generatingVersion.current = null;
    }
  }

  if (logoutPending) {
    return <div className="app-shell app-shell--auth"><section className="panel" aria-label="退出确认">
      <h2>退出尚未确认</h2>
      <p role="status">当前资料已隐藏，尚未确认服务端会话已退出。刷新或重新打开页面后仍会继续确认。</p>
      {error && <p role="alert">{error}</p>}
      <button className="primary-button" type="button" disabled={logoutBusy || bootLoading} onClick={retryLogout}>{logoutBusy || bootLoading ? "正在确认退出…" : "重试退出"}</button>
    </section></div>;
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
          loading={authBusy}
          form={authForm}
          onModeChange={setAuthMode}
          onChange={(field, value) => setAuthForm((current) => ({ ...current, [field]: value }))}
          onSubmit={handleAuthSubmit}
          onGuestLogin={() => void handleGuestLogin()}
          onRecovery={startRecovery}
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
        settingsBusy={settingsBusy}
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
          <button className="primary-button" type="button" onClick={() => openQuickRecord()}>记一笔农活</button>
        </section>}
        {user.is_guest && <GuestAccountPanel user={user}
          onSaved={acceptGuestUpgrade}
          onReturnToLogin={(username) => { void handleLogout(username); }} />}
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
          onComplete={handleToggleTask} onRecord={openQuickRecord} />}

        {activeFeature === "decision" && (
          <Suspense fallback={<div className="panel panel--loading">正在加载今日农活模块...</div>}>
            <DecisionWorkspace
              crop={decisionForm.crop}
              stage={decisionForm.stage}
              rainProb={decisionForm.rainProb}
              soilMoisture={decisionForm.soilMoisture}
              temperature={decisionForm.temperature}
              result={decisionResult?.reply ?? ""}
              resultContext={decisionResult ? `生成时地块：${decisionResult.plotName || "未关联地块"}；作物：${decisionResult.input.crop}；生长期：${decisionResult.input.stage}` : ""}
              busy={decisionBusy}
              saving={adviceSaveAction.busy}
              plots={plots.items}
              selectedPlotId={selectedPlotId}
              onChange={handleDecisionChange}
              onPlotChange={handleDecisionPlotChange}
              onSubmit={() => void handleDecisionSubmit()}
              onSaveAdviceAsTask={() => void handleSaveAdviceAsTask()}
              adviceSaved={decisionResult?.saved ?? false}
            />
          </Suspense>
        )}

        {activeFeature === "ledger" && (
          <Suspense fallback={<div className="panel panel--loading">正在加载农事台账...</div>}>
            <LedgerWorkspace
              key={`${user.id}:${workspaceRevision}`}
              plots={plots.items}
              seasons={seasons.items}
              onError={setError}
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
                  setCompletedTask(null); setQuickEntry(null); invalidateDecision(); setSelectedPlotId("");
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
              onRecord={openQuickRecord}
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
          setCompletedTask(null); setQuickEntry(null); invalidateDecision(); setSelectedPlotId("");
          setDecisionForm((current) => ({ ...current, crop: "玉米" }));
          setEconomicsFilters({ plot_id: "", season_id: "", year: "", data_scope: "real" });
          await Promise.all([plots.refresh(), seasons.refresh(), tasks.refresh()]);
          setWorkspaceRevision((current) => current + 1);
        }} />}
        {activeFeature === "stats" && (
          <Suspense fallback={<div className="panel panel--loading">正在加载统计面板...</div>}>
            <StatsWorkspace key={workspaceRevision} onError={setError} plots={plots.items} seasons={seasons.items}
              filters={economicsFilters} onFiltersChange={setEconomicsFilters}
              onRecordsChanged={plots.refresh} onQuickTask={tasks.create} />
          </Suspense>
        )}

      </main>

      {quickEntry && (
        <div className="dialog-backdrop">
          <section
            ref={recordDialog}
            tabIndex={-1}
            className="record-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="record-dialog-title"
          >
            <h3 id="record-dialog-title">{quickEntry.task ? "从已完成待办记账" : "记一笔农活"}</h3>
            {quickEntry.task && (
              <p>来自「{quickEntry.task.title}」。日期取实际完成日；请核对作业类型、日期和内容。{!quickEntry.task.plot_id && "这条是杂事，请先选择地块。"}取消或保存失败不会重新打开待办。</p>
            )}
            {error && <p className="form-warning" role="alert">{error}</p>}
            {plots.items.length === 0 ? (
              <>
                <p>农事台账需要关联地块，请先登记一块地。</p>
                <button className="primary-button" type="button" onClick={() => { setQuickEntry(null); setActiveFeature("plots"); }}>登记地块</button>
                <button className="ghost-button" type="button" onClick={() => setQuickEntry(null)}>取消记账</button>
              </>
            ) : (
              <Suspense fallback={<p>正在加载记账表单...</p>}>
                <section className="workspace-grid">
                  <FarmRecordForm
                    key={quickEntry.key}
                    compact
                    plots={plots.items}
                    seasons={seasons.items}
                    initialDraft={quickEntry.draft}
                    initialSubmissionId={quickEntry.task?.id}
                    onError={setError}
                    onRecordsChanged={plots.refresh}
                    onQuickTask={tasks.create}
                    onCancel={closeQuickEntry}
                    onSaved={() => {
                      setQuickEntry(null);
                      setCompletedTask(null);
                      setNotice("已记入台账，可到统计面板查看收支。");
                    }}
                  />
                </section>
              </Suspense>
            )}
          </section>
        </div>
      )}

      {infoPanel && (
        <AppInfoDialog
          page={infoPanel}
          appName={health.app_name}
          appVersion={health.app_version}
          onClose={() => setInfoPanel(null)}
        />
      )}
    </div>
  );
}
