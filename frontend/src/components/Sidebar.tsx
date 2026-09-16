import { BarChart3, CalendarCheck, ClipboardList, MapPin, NotebookTabs, Settings2, Sprout, X } from "lucide-react";
import { memo } from "react";

import { FeatureKey, User } from "../types";

const featureLabels: Record<FeatureKey, string> = {
  decision: "今日农活",
  plots: "地块档案",
  ledger: "农事台账",
  tasks: "农事待办",
  stats: "统计面板",
};

interface SidebarProps {
  user: User;
  activeFeature: FeatureKey;
  settingsName: string;
  mobileOpen: boolean;
  settingsBusy: boolean;
  onClose: () => void;
  onFeatureChange: (feature: FeatureKey) => void;
  onSettingsNameChange: (value: string) => void;
  onOpenHelp: () => void;
  onOpenAbout: () => void;
  onSaveSettings: () => void;
  onLogout: () => void;
}

export const Sidebar = memo(function Sidebar({
  user, activeFeature, settingsName, mobileOpen, settingsBusy, onClose, onFeatureChange,
  onSettingsNameChange, onOpenHelp, onOpenAbout, onSaveSettings, onLogout,
}: SidebarProps) {
  return (
    <aside id="app-sidebar" className={mobileOpen ? "sidebar is-open" : "sidebar"} aria-label="主导航">
      <button className="sidebar__close" type="button" onClick={onClose} aria-label="关闭导航"><X size={20} /></button>
      <div className="sidebar__brand"><div className="brand-mark"><Sprout size={20} /></div><div><div className="brand-name">云寻</div><div className="brand-subname">Agronomy cockpit</div></div></div>
      <nav className="feature-nav" aria-label="功能菜单">
        {(["decision", "plots", "ledger", "tasks", "stats"] as FeatureKey[]).map((feature) => (
          <button key={feature} type="button" className={activeFeature === feature ? "feature-nav__item is-active" : "feature-nav__item"} onClick={() => { onFeatureChange(feature); onClose(); }}>
            {feature === "decision" && <NotebookTabs size={18} />}{feature === "plots" && <MapPin size={18} />}{feature === "ledger" && <ClipboardList size={18} />}{feature === "tasks" && <CalendarCheck size={18} />}{feature === "stats" && <BarChart3 size={18} />}<span>{featureLabels[feature]}</span>
          </button>
        ))}
      </nav>
      <section className="sidebar__section sidebar__section--footer"><div className="sidebar__section-title"><Settings2 size={16} />个人设置</div><label className="field"><span>显示名称</span><div className="field-control"><input value={settingsName} onChange={(event) => onSettingsNameChange(event.target.value)} /></div></label><div className="profile-card"><div className="profile-card__name">{user.display_name}</div><div className="profile-card__meta">@{user.username}</div></div><div className="inline-actions"><button className="secondary-button" type="button" onClick={onSaveSettings} disabled={settingsBusy}>{settingsBusy ? "保存中…" : "保存设置"}</button><button className="ghost-button" type="button" onClick={onLogout}>退出登录</button></div><div className="inline-actions"><button className="ghost-button" type="button" onClick={onOpenHelp}>使用帮助</button><button className="ghost-button" type="button" onClick={onOpenAbout}>关于软件</button></div></section>
    </aside>
  );
});
