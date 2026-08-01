import { MessageSquareText, NotebookTabs, ScanSearch, Settings2, Sprout, Trash2, X } from "lucide-react";
import { memo } from "react";

import { FeatureKey, SessionItem, User } from "../types";

const featureLabels: Record<FeatureKey, string> = {
  chat: "智能问答",
  vision: "田间诊断",
  decision: "今日农活",
};

interface SidebarProps {
  user: User;
  activeFeature: FeatureKey;
  sessions: SessionItem[];
  activeSessionId: string | null;
  renameTitle: string;
  settingsName: string;
  selectedModel: string;
  models: string[];
  sessionQuery: string;
  mobileOpen: boolean;
  sessionBusy: boolean;
  settingsBusy: boolean;
  onClose: () => void;
  onFeatureChange: (feature: FeatureKey) => void;
  onCreateSession: () => void;
  onSelectSession: (sessionId: string) => void;
  onRenameTitleChange: (value: string) => void;
  onRenameSession: () => void;
  onDeleteSession: () => void;
  onSettingsNameChange: (value: string) => void;
  onModelChange: (value: string) => void;
  onSessionQueryChange: (value: string) => void;
  onPinSession: (sessionId: string, isPinned: boolean) => void;
  onOpenHelp: () => void;
  onOpenAbout: () => void;
  onSaveSettings: () => void;
  onLogout: () => void;
}

export const Sidebar = memo(function Sidebar({
  user, activeFeature, sessions, activeSessionId, renameTitle, settingsName, selectedModel, models,
  mobileOpen, sessionBusy, settingsBusy, onClose, onFeatureChange, onCreateSession, onSelectSession,
  onRenameTitleChange, onRenameSession, onDeleteSession, onSettingsNameChange, onModelChange, sessionQuery,
  onSessionQueryChange, onPinSession, onOpenHelp, onOpenAbout,
  onSaveSettings, onLogout,
}: SidebarProps) {
  return (
    <aside id="app-sidebar" className={mobileOpen ? "sidebar is-open" : "sidebar"} aria-label="主导航">
      <button className="sidebar__close" type="button" onClick={onClose} aria-label="关闭导航"><X size={20} /></button>
      <div className="sidebar__brand"><div className="brand-mark"><Sprout size={20} /></div><div><div className="brand-name">云寻AI</div><div className="brand-subname">Agronomy cockpit</div></div></div>
      <button className="primary-button sidebar__new" type="button" onClick={() => { onCreateSession(); onClose(); }} disabled={sessionBusy}><MessageSquareText size={16} />新建会话</button>
      <nav className="feature-nav" aria-label="功能菜单">
        {(["chat", "vision", "decision"] as FeatureKey[]).map((feature) => (
          <button key={feature} type="button" className={activeFeature === feature ? "feature-nav__item is-active" : "feature-nav__item"} onClick={() => { onFeatureChange(feature); onClose(); }}>
            {feature === "chat" && <MessageSquareText size={18} />}{feature === "vision" && <ScanSearch size={18} />}{feature === "decision" && <NotebookTabs size={18} />}<span>{featureLabels[feature]}</span>
          </button>
        ))}
      </nav>
      <section className="sidebar__section"><div className="sidebar__section-title">历史会话</div><label className="session-search"><span className="sr-only">搜索会话</span><input aria-label="搜索会话" value={sessionQuery} onChange={(event) => onSessionQueryChange(event.target.value)} placeholder="搜索会话标题" /></label><div className="session-list">
        {sessions.length === 0 && <p className="sidebar__empty">{sessionQuery.trim() ? "没有匹配的会话" : "发送第一条消息后，这里会保留会话记录。"}</p>}
        {sessions.map((session) => <div className="session-card-row" key={session.id}><button type="button" className={activeSessionId === session.id ? "session-card is-active" : "session-card"} onClick={() => { onSelectSession(session.id); onClose(); }} disabled={sessionBusy}><div className="session-card__title">{session.is_pinned ? "📌 " : ""}{session.title}</div><div className="session-card__meta">{session.model_name}</div><div className="session-card__preview">{session.last_message || "还没有消息"}</div></button><button className="ghost-button session-pin" type="button" aria-label={session.is_pinned ? "取消置顶会话" : "置顶会话"} onClick={() => onPinSession(session.id, !session.is_pinned)} disabled={sessionBusy}>{session.is_pinned ? "取消置顶" : "置顶"}</button></div>)}
      </div></section>
      {activeFeature === "chat" && activeSessionId && <section className="sidebar__section"><div className="sidebar__section-title">当前会话</div><label className="field"><span>会话标题</span><div className="field-control"><input value={renameTitle} onChange={(event) => onRenameTitleChange(event.target.value)} /></div></label><div className="inline-actions"><button className="secondary-button" type="button" onClick={onRenameSession} disabled={sessionBusy}>保存标题</button><button className="ghost-button danger" type="button" onClick={onDeleteSession} disabled={sessionBusy}><Trash2 size={16} />删除</button></div></section>}
      <section className="sidebar__section sidebar__section--footer"><div className="sidebar__section-title"><Settings2 size={16} />个人设置</div><label className="field"><span>显示名称</span><div className="field-control"><input value={settingsName} onChange={(event) => onSettingsNameChange(event.target.value)} /></div></label><label className="field"><span>默认模型</span><div className="field-control field-control--select"><select value={selectedModel} onChange={(event) => onModelChange(event.target.value)}>{models.map((model) => <option key={model} value={model}>{model}</option>)}</select></div></label><div className="profile-card"><div className="profile-card__name">{user.display_name}</div><div className="profile-card__meta">@{user.username}</div></div><div className="inline-actions"><button className="secondary-button" type="button" onClick={onSaveSettings} disabled={settingsBusy}>{settingsBusy ? "保存中…" : "保存设置"}</button><button className="ghost-button" type="button" onClick={onLogout}>退出登录</button></div><div className="inline-actions"><button className="ghost-button" type="button" onClick={onOpenHelp}>使用帮助</button><button className="ghost-button" type="button" onClick={onOpenAbout}>关于软件</button></div></section>
    </aside>
  );
});
