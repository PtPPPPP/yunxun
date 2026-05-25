import { MessageSquareText, NotebookTabs, ScanSearch, Settings2, Sprout, Trash2 } from "lucide-react";
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
  onFeatureChange: (feature: FeatureKey) => void;
  onCreateSession: () => void;
  onSelectSession: (sessionId: string) => void;
  onRenameTitleChange: (value: string) => void;
  onRenameSession: () => void;
  onDeleteSession: () => void;
  onSettingsNameChange: (value: string) => void;
  onModelChange: (value: string) => void;
  onSaveSettings: () => void;
  onLogout: () => void;
}

export const Sidebar = memo(function Sidebar(props: SidebarProps) {
  const {
    user,
    activeFeature,
    sessions,
    activeSessionId,
    renameTitle,
    settingsName,
    selectedModel,
    models,
    onFeatureChange,
    onCreateSession,
    onSelectSession,
    onRenameTitleChange,
    onRenameSession,
    onDeleteSession,
    onSettingsNameChange,
    onModelChange,
    onSaveSettings,
    onLogout,
  } = props;

  return (
    <aside className="sidebar">
      <div className="sidebar__brand">
        <div className="brand-mark">
          <Sprout size={20} />
        </div>
        <div>
          <div className="brand-name">云寻 AI</div>
          <div className="brand-subname">Agronomy cockpit</div>
        </div>
      </div>

      <button className="primary-button sidebar__new" type="button" onClick={onCreateSession}>
        <MessageSquareText size={16} />
        新建会话
      </button>

      <nav className="feature-nav" aria-label="功能菜单">
        {(["chat", "vision", "decision"] as FeatureKey[]).map((feature) => (
          <button
            key={feature}
            type="button"
            className={activeFeature === feature ? "feature-nav__item is-active" : "feature-nav__item"}
            onClick={() => onFeatureChange(feature)}
          >
            {feature === "chat" && <MessageSquareText size={18} />}
            {feature === "vision" && <ScanSearch size={18} />}
            {feature === "decision" && <NotebookTabs size={18} />}
            <span>{featureLabels[feature]}</span>
          </button>
        ))}
      </nav>

      <section className="sidebar__section">
        <div className="sidebar__section-title">历史会话</div>
        <div className="session-list">
          {sessions.length === 0 && <p className="sidebar__empty">发出第一条消息后，这里会保留会话记录。</p>}
          {sessions.map((session) => (
            <button
              key={session.id}
              type="button"
              className={activeSessionId === session.id ? "session-card is-active" : "session-card"}
              onClick={() => onSelectSession(session.id)}
            >
              <div className="session-card__title">{session.title}</div>
              <div className="session-card__meta">{session.model_name}</div>
              <div className="session-card__preview">{session.last_message || "还没有消息"}</div>
            </button>
          ))}
        </div>
      </section>

      {activeFeature === "chat" && activeSessionId && (
        <section className="sidebar__section">
          <div className="sidebar__section-title">当前会话</div>
          <label className="field">
            <span>会话标题</span>
            <div className="field-control">
              <input value={renameTitle} onChange={(event) => onRenameTitleChange(event.target.value)} />
            </div>
          </label>
          <div className="inline-actions">
            <button className="secondary-button" type="button" onClick={onRenameSession}>
              保存标题
            </button>
            <button className="ghost-button danger" type="button" onClick={onDeleteSession}>
              <Trash2 size={16} />
              删除
            </button>
          </div>
        </section>
      )}

      <section className="sidebar__section sidebar__section--footer">
        <div className="sidebar__section-title">
          <Settings2 size={16} />
          个人设置
        </div>
        <label className="field">
          <span>显示名称</span>
          <div className="field-control">
            <input value={settingsName} onChange={(event) => onSettingsNameChange(event.target.value)} />
          </div>
        </label>
        <label className="field">
          <span>默认模型</span>
          <div className="field-control field-control--select">
            <select value={selectedModel} onChange={(event) => onModelChange(event.target.value)}>
              {models.map((model) => (
                <option key={model} value={model}>
                  {model}
                </option>
              ))}
            </select>
          </div>
        </label>
        <div className="profile-card">
          <div className="profile-card__name">{user.display_name}</div>
          <div className="profile-card__meta">@{user.username}</div>
        </div>
        <div className="inline-actions">
          <button className="secondary-button" type="button" onClick={onSaveSettings}>
            保存设置
          </button>
          <button className="ghost-button" type="button" onClick={onLogout}>
            退出登录
          </button>
        </div>
      </section>
    </aside>
  );
});
