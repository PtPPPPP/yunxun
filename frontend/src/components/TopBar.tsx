import { CalendarCheck, CloudSun, Menu, ShieldCheck } from "lucide-react";
import { memo } from "react";

import { FeatureKey, HealthPayload } from "../types";
import { formatAppVersion } from "../lib/appVersion";

// 标题与侧边栏的功能名保持一致：同一个模块在导航和页面标题上必须是同一个词。
const featureTitles: Record<FeatureKey, { title: string; subtitle: string }> = {
  decision: { title: "今日农活", subtitle: "按你判断的天气、墒情和生长期生成今天可执行的安排。" },
  plots: { title: "地块档案", subtitle: "登记地块的面积、土壤与灌溉条件，按茬次记录当季作物。" },
  ledger: { title: "农事台账", subtitle: "按地块记录每次作业的日期、用量、费用与采收产量。" },
  tasks: { title: "农事待办", subtitle: "把接下来要做的事排好，逾期会标红。" },
  stats: { title: "统计面板", subtitle: "汇总地块、台账、待办与投入产出。" },
};

export interface TaskSummary {
  open: number;
  dueToday: number;
  overdue: number;
}

interface TopBarProps {
  health: HealthPayload;
  activeFeature: FeatureKey;
  taskSummary: TaskSummary;
  onOpenNavigation: () => void;
}

export const TopBar = memo(function TopBar({ health, activeFeature, taskSummary, onOpenNavigation }: TopBarProps) {
  const today = new Intl.DateTimeFormat("zh-CN", {
    month: "long",
    day: "numeric",
    weekday: "short",
  }).format(new Date());
  const copy = featureTitles[activeFeature];

  return (
    <header className="topbar">
      <div className="topbar__title">
        <button
          className="mobile-menu-button"
          type="button"
          onClick={onOpenNavigation}
          aria-label="打开导航"
          aria-controls="app-sidebar"
        >
          <Menu size={20} />
        </button>
        <div>
          <div className="eyebrow">
            <span>云寻</span>
            <span className="app-version">{formatAppVersion(health.app_version)}</span>
          </div>
          <h2>{copy.title}</h2>
          <p>{copy.subtitle}</p>
        </div>
      </div>
      <div className="topbar__chips">
        {health.warnings.length > 0 && (
          <details className="runtime-warning">
            <summary className="status-chip status-chip--warning status-chip--wide">
              <ShieldCheck size={16} />
              <span>{health.warnings.length} 条运行提醒</span>
            </summary>
            <div className="runtime-warning__panel" role="status">
              {health.warnings.map((warning) => <div key={warning}>{warning}</div>)}
            </div>
          </details>
        )}
        <div className="status-chip"><CloudSun size={16} /><span>{today}</span></div>
        {taskSummary.open > 0 && (
          <div className={taskSummary.overdue > 0 ? "status-chip status-chip--warning" : "status-chip"}>
            <CalendarCheck size={16} />
            <span>
              待办 {taskSummary.open} 项
              {taskSummary.overdue > 0 ? `，${taskSummary.overdue} 项逾期` : taskSummary.dueToday > 0 ? `，今天 ${taskSummary.dueToday} 项` : ""}
            </span>
          </div>
        )}
      </div>
    </header>
  );
});
