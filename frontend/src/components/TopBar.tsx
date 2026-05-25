import { CloudSun, Gauge, LineChart, ShieldCheck } from "lucide-react";
import { memo } from "react";

import { FeatureKey, HealthPayload } from "../types";

const featureTitles: Record<FeatureKey, { title: string; subtitle: string }> = {
  chat: {
    title: "智能问答工作台",
    subtitle: "保留上下文的农技问答区，适合持续沟通、方案整理和知识解释。",
  },
  vision: {
    title: "田间诊断台",
    subtitle: "把作物照片和现场描述一起提交，统一由后端代理模型做识别与建议。",
  },
  decision: {
    title: "今日农活计划",
    subtitle: "结合天气、墒情和生长期，快速生成今天能执行的田间安排。",
  },
};

interface TopBarProps {
  health: HealthPayload;
  activeFeature: FeatureKey;
}

export const TopBar = memo(function TopBar({ health, activeFeature }: TopBarProps) {
  const today = new Intl.DateTimeFormat("zh-CN", {
    month: "long",
    day: "numeric",
    weekday: "short",
  }).format(new Date());
  const copy = featureTitles[activeFeature];

  return (
    <header className="topbar">
      <div>
        <div className="eyebrow">云寻 AI</div>
        <h2>{copy.title}</h2>
        <p>{copy.subtitle}</p>
      </div>

      <div className="topbar__chips">
        {health.warnings.length > 0 && (
          <details className="runtime-warning">
            <summary className="status-chip status-chip--warning status-chip--wide">
              <ShieldCheck size={16} />
              <span>{health.warnings.length} 条运行提醒</span>
            </summary>
            <div className="runtime-warning__panel" role="status">
              {health.warnings.map((warning) => (
                <div key={warning}>{warning}</div>
              ))}
            </div>
          </details>
        )}
        <div className="status-chip">
          <CloudSun size={16} />
          <span>{today}</span>
        </div>
        <div className={health.ai_configured ? "status-chip" : "status-chip status-chip--warning"}>
          <ShieldCheck size={16} />
          <span>{health.model_status}</span>
        </div>
        <div className="status-chip">
          <LineChart size={16} />
          <span>{health.available_models.length} 个可用模型</span>
        </div>
        <div className="status-chip">
          <LineChart size={16} />
          <span>{health.backend_url}</span>
        </div>
        <div className="status-chip">
          <Gauge size={16} />
          <span>{health.requests_per_minute}/分钟</span>
        </div>
      </div>
    </header>
  );
});
