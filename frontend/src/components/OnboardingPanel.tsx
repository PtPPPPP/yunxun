import { useCallback, useEffect, useRef, useState } from "react";

import { useAsyncGuard } from "../hooks/useAsyncGuard";
import { useRequestLeave } from "../hooks/useUnsavedChanges";
import { api, getErrorMessage } from "../lib/api";
import { FeatureKey, OnboardingStatus, Plot, PlotSeason, User } from "../types";

interface OnboardingPanelProps {
  user: User;
  plots: Plot[];
  seasons: PlotSeason[];
  onStep: (step: "plot" | "season" | "record", plotId: string | null) => void;
  onNavigate: (feature: FeatureKey) => void;
  onDemoChanged: (loaded: boolean) => Promise<void>;
  onDemoStats: () => void;
}

export function OnboardingPanel({ user, plots, seasons, onStep, onNavigate, onDemoChanged, onDemoStats }: OnboardingPanelProps) {
  const [state, setState] = useState<OnboardingStatus | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [showCompleted, setShowCompleted] = useState(false);
  const action = useAsyncGuard();
  const requestLeave = useRequestLeave();
  const requestVersion = useRef(0);
  const reload = useCallback(async () => {
    const version = ++requestVersion.current;
    try {
      const response = await api.get<{ onboarding: OnboardingStatus }>("/api/onboarding");
      if (version !== requestVersion.current) return;
      setState(response.data.onboarding);
      setError("");
    } catch (requestError) { if (version === requestVersion.current) setError(getErrorMessage(requestError)); }
  }, []);

  useEffect(() => { void reload(); }, [reload, plots, seasons]);

  async function skip(skipped: boolean) {
    await action.run(async () => {
      requestVersion.current++;
      try {
        const response = await api.patch<{ onboarding: OnboardingStatus }>("/api/onboarding", { skipped });
        setState(response.data.onboarding);
        setError("");
      } catch (requestError) { setError(getErrorMessage(requestError)); }
    });
  }

  async function changeDemo(load: boolean) {
    await action.run(async () => {
      requestVersion.current++;
      try {
        const response = await api.request<{ onboarding: OnboardingStatus; retained?: { plots: number; plot_seasons: number } }>({ url: "/api/demo-data", method: load ? "POST" : "DELETE" });
        setState(response.data.onboarding);
        const retained = response.data.retained;
        setMessage(load ? "演示已加载，可查看地块、台账和收支。" : retained && retained.plots + retained.plot_seasons > 0
          ? `演示记录已清空。为保留你新增的数据，${retained.plots} 个地块、${retained.plot_seasons} 个茬次已转为普通资料。`
          : "演示数据已清空，自己新增的数据已保留。");
        setError("");
        await onDemoChanged(load);
      } catch (requestError) { setError(getErrorMessage(requestError)); }
    });
  }

  if (!state) return <section className="panel onboarding-panel" aria-label="首次使用引导">
    {error ? <><p role="alert">{error}</p><button type="button" className="ghost-button" onClick={() => void reload()}>重试引导</button></> : <p>正在核对首次使用进度…</p>}
  </section>;
  const count = Number(state.plot_done) + Number(state.season_done) + Number(state.record_done);
  const complete = count === 3;
  const expanded = !state.skipped && (!complete || showCompleted);
  const steps = [
    { key: "plot" as const, title: "登记第一块地", done: state.plot_done, hint: "保存地块时会同时建立第一茬。", label: "去登记地块" },
    { key: "season" as const, title: "建立第一茬", done: state.season_done, hint: state.season_done ? "第一茬已建立，无需重复创建。" : "已有地块无茬次时再补建。", label: "去建立第一茬" },
    { key: "record" as const, title: "记第一笔农活", done: state.record_done, hint: "填写实际日期、作业和费用。", label: "去记第一笔农活" },
  ];

  return <section className="panel onboarding-panel" aria-label="首次使用引导">
    <div className="home-actions"><h3>{complete ? "已完成第一条真实业务流程" : `首次使用 · ${count}/3 步已完成`}</h3>
      <div className="inline-actions">{expanded ? <button type="button" className="ghost-button" disabled={action.busy} onClick={() => void skip(true)}>暂时跳过</button>
        : <button type="button" className="ghost-button" disabled={action.busy} onClick={() => { if (complete) setShowCompleted(true); void skip(false); }}>{complete ? "查看步骤" : "继续引导"}</button>}
        {complete && <button type="button" className="ghost-button" onClick={() => onNavigate("stats")}>查看收支</button>}</div>
    </div>
    {expanded && <><p>按真实数据核对进度，可跳过后继续。</p><ol className="onboarding-steps">{steps.map((step) => <li key={step.key}>
      <strong>{step.done ? "✓ 已完成：" : "待完成："}{step.title}</strong><p>{step.hint}</p>
      <button className="secondary-button" type="button" disabled={action.busy || (step.key !== "plot" && !state.plot_done)}
        onClick={() => step.done ? onNavigate(step.key === "record" ? "ledger" : "plots") : onStep(step.key, state.first_plot_id)}>
        {step.done ? step.key === "record" ? "查看台账" : "查看地块与茬次" : step.label}
      </button>
    </li>)}</ol></>}
    {state.demo_count > 0 && <p className="demo-notice" role="status">含演示资料，示例金额不代表真实经营成果，不计入引导进度。</p>}
    {(user.is_guest || state.demo_loaded || state.demo_count > 0) && <div className="onboarding-demo">
      <strong>{user.is_guest ? "先看看示例（可选）" : "已保留的演示资料"}</strong><p>了解地块、茬次、台账、待办与收支如何相连。</p>
      <div className="inline-actions">{state.demo_loaded ? <><button className="secondary-button" type="button" disabled={action.busy} onClick={onDemoStats}>查看演示收支</button><button className="ghost-button" type="button" disabled={action.busy} onClick={() => requestLeave(() => { void changeDemo(false); })}>只清空演示数据</button></>
        : user.is_guest ? <button className="secondary-button" type="button" disabled={action.busy} onClick={() => requestLeave(() => { void changeDemo(true); })}>{action.busy ? "处理中…" : "加载演示数据"}</button> : null}</div>
      {state.demo_loaded && <p>演示记录修改后仍属演示；清空会保留自行新增数据及必要关联。</p>}
    </div>}
    {message && <p role="status">{message}</p>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
