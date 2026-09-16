import { FormEvent, Suspense, lazy, useCallback, useEffect, useMemo, useState } from "react";

import { AuthScreen } from "./components/AuthScreen";
import { Sidebar } from "./components/Sidebar";
import { TopBar } from "./components/TopBar";
import { useAsyncGuard } from "./hooks/useAsyncGuard";
import { usePlots } from "./hooks/usePlots";
import { useSeasons } from "./hooks/useSeasons";
import { useTasks } from "./hooks/useTasks";
import { api, getErrorMessage } from "./lib/api";
import { formatAppVersion } from "./lib/appVersion";
import { todayIso } from "./lib/date";
import { FeatureKey, HealthPayload, User } from "./types";

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

export default function App() {
  const [health, setHealth] = useState<HealthPayload | null>(null);
  const [bootLoading, setBootLoading] = useState(true);
  const [error, setError] = useState("");
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [authForm, setAuthForm] = useState({ username: "", password: "", displayName: "" });
  const [user, setUser] = useState<User | null>(null);
  const [activeFeature, setActiveFeature] = useState<FeatureKey>("decision");
  const [settingsName, setSettingsName] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [infoPanel, setInfoPanel] = useState<"help" | "about" | null>(null);
  const [decisionForm, setDecisionForm] = useState({
    crop: "玉米",
    stage: "快速生长期",
    rainProb: 55,
    soilMoisture: 42,
    temperature: 24.5,
  });
  const [decisionResult, setDecisionResult] = useState("");
  const [selectedPlotId, setSelectedPlotId] = useState("");
  const [adviceSaved, setAdviceSaved] = useState(false);

  const authAction = useAsyncGuard();
  const settingsAction = useAsyncGuard();
  const decisionAction = useAsyncGuard();
  const handleError = useCallback((message: string) => setError(message), []);
  const plots = usePlots({ onError: handleError, enabled: user !== null });
  const tasks = useTasks({ onError: handleError, enabled: user !== null });
  // 茬次变化会改动地块上的当前作物与本季计数，所以顺手刷新地块列表。
  const seasons = useSeasons({
    onError: handleError,
    enabled: user !== null,
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
    setUser(nextUser);
    setSettingsName(nextUser.display_name);
    setAuthForm({ username: "", password: "", displayName: "" });
  }, []);

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
    setUser(null);
  }

  const taskSummary = useMemo(() => {
    const today = todayIso();
    return {
      open: tasks.items.length,
      dueToday: tasks.items.filter((item) => item.due_on === today).length,
      overdue: tasks.items.filter((item) => item.due_on < today).length,
    };
  }, [tasks.items]);

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
      try {
        setAdviceSaved(false);
        const response = await api.post<{ success: true; reply: string }>("/api/decision", {
          crop: decisionForm.crop,
          stage: decisionForm.stage,
          rain_prob: decisionForm.rainProb,
          soil_moisture: decisionForm.soilMoisture,
          temperature: decisionForm.temperature,
        });
        setDecisionResult(response.data.reply);
        setError("");
      } catch (requestError) {
        setError(getErrorMessage(requestError));
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
        <AuthScreen
          mode={authMode}
          loading={authAction.busy}
          form={authForm}
          onModeChange={setAuthMode}
          onChange={(field, value) => setAuthForm((current) => ({ ...current, [field]: value }))}
          onSubmit={handleAuthSubmit}
          onGuestLogin={() => void handleGuestLogin()}
        />
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
        onFeatureChange={setActiveFeature}
        onSettingsNameChange={setSettingsName}
        onOpenHelp={() => setInfoPanel("help")}
        onOpenAbout={() => setInfoPanel("about")}
        onSaveSettings={() => void handleSaveSettings()}
        onLogout={() => void handleLogout()}
      />

      <main className="workspace">
        <TopBar
          health={health}
          activeFeature={activeFeature}
          taskSummary={taskSummary}
          onOpenNavigation={() => setSidebarOpen(true)}
        />

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
              plots={plots.items}
              onError={handleError}
              onRecordsChanged={() => void plots.refresh()}
              onQuickTask={tasks.create}
            />
          </Suspense>
        )}

        {activeFeature === "plots" && (
          <Suspense fallback={<div className="panel panel--loading">正在加载地块档案...</div>}>
            <PlotsWorkspace
              plots={plots.items}
              seasons={seasons.items}
              loading={plots.loading}
              busy={plots.busy}
              seasonBusy={seasons.busy}
              onCreate={(payload) => withSeasonRefresh(() => plots.create(payload))}
              onUpdate={(plotId, payload) => withSeasonRefresh(() => plots.update(plotId, payload))}
              onRemove={(plotId) => withSeasonRefresh(() => plots.remove(plotId))}
              onCreateSeason={seasons.create}
              onUpdateSeason={seasons.update}
            />
          </Suspense>
        )}

        {activeFeature === "tasks" && (
          <Suspense fallback={<div className="panel panel--loading">正在加载农事待办...</div>}>
            <TasksWorkspace
              tasks={tasks.items}
              recentDone={tasks.recentDone}
              plots={plots.items}
              loading={tasks.loading}
              busy={tasks.busy}
              onCreate={tasks.create}
              onUpdate={tasks.update}
              onToggle={tasks.toggle}
              onRemove={tasks.remove}
            />
          </Suspense>
        )}

        {activeFeature === "stats" && (
          <Suspense fallback={<div className="panel panel--loading">正在加载统计面板...</div>}>
            <StatsWorkspace onError={handleError} />
          </Suspense>
        )}

      </main>

      {infoPanel && <div className="dialog-backdrop" role="presentation" onMouseDown={() => setInfoPanel(null)}><section className="confirm-dialog info-dialog" role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}><button className="ghost-button info-dialog__close" type="button" onClick={() => setInfoPanel(null)} aria-label="关闭">关闭</button>{infoPanel === "help" ? <><h3>使用帮助</h3><p>注册、登录或使用访客模式后，可以登记地块、记录农事并生成当天农活建议。</p><ul><li>地块档案登记面积、土壤和灌溉条件，每块地按茬次记录当季作物。</li><li>结束一茬后可以开始新茬，投入产出按茬次分开算，不混季。</li><li>农事台账按地块记录每次作业的日期、用量、费用，采收还能记产量和单价。</li><li>打药记录填了安全间隔期后，采收时会提醒是否已过安全期。</li><li>农事待办把接下来要做的事排好，逾期会在顶栏标红。</li><li>删除地块会连带删除它下面的全部农事台账记录。</li><li>今日农活可以直接选地块带出作物和土壤条件。</li><li>统计面板汇总地块数、作业次数和历史农活建议。</li><li>显示名称可以随时在个人设置里修改。</li></ul></> : <><h3>关于软件</h3><p>软件全称：{health.app_name}</p><p>软件简称：云寻</p><p>软件版本：{formatAppVersion(health.app_version)}</p><p>主要功能：地块与茬次档案、农事台账、农事待办、今日农活计划、投入产出核算与建议统计。</p></>}</section></div>}
    </div>
  );
}
