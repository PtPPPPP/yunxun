import { CloudSun, Gauge, LineChart, Menu, ShieldCheck } from "lucide-react";
import { memo } from "react";

import { FeatureKey, HealthPayload } from "../types";
import { formatAppVersion } from "../lib/appVersion";

const featureTitles: Record<FeatureKey, { title: string; subtitle: string }> = {
  decision: { title: "今日农活计划", subtitle: "结合天气、墒情和生长期生成今天可执行的安排。" },
  plots: { title: "农事地块", subtitle: "登记地块的面积、土壤、灌溉条件和当季作物。" },
  stats: { title: "统计面板", subtitle: "回顾历史农活建议的使用情况。" },
};

interface TopBarProps {
  health: HealthPayload;
  activeFeature: FeatureKey;
  onOpenNavigation: () => void;
}

export const TopBar = memo(function TopBar({ health, activeFeature, onOpenNavigation }: TopBarProps) {
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
        <div className="status-chip"><LineChart size={16} /><span>{health.backend_url}</span></div>
        <div className="status-chip"><Gauge size={16} /><span>{health.requests_per_minute}/分钟</span></div>
      </div>
    </header>
  );
});
