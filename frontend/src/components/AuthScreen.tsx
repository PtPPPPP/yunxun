import { Leaf, LockKeyhole, UserRound } from "lucide-react";
import { FormEvent } from "react";

interface AuthScreenProps {
  mode: "login" | "register";
  backendMode: string;
  backendUrl: string;
  modelStatus: string;
  environment: string;
  warnings: string[];
  loading: boolean;
  form: {
    username: string;
    password: string;
    displayName: string;
  };
  onModeChange: (mode: "login" | "register") => void;
  onChange: (field: "username" | "password" | "displayName", value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onGuestLogin: () => void;
}

export function AuthScreen(props: AuthScreenProps) {
  const {
    mode,
    backendMode,
    backendUrl,
    modelStatus,
    environment,
    warnings,
    loading,
    form,
    onModeChange,
    onChange,
    onSubmit,
    onGuestLogin,
  } = props;

  return (
    <div className="auth-layout">
      <section className="auth-hero">
        <div className="auth-hero__backdrop" />
        <div className="auth-hero__content">
          <div className="brand-lockup">
            <div className="brand-mark">
              <Leaf size={24} />
            </div>
            <div>
              <div className="brand-name">云寻 AI</div>
              <div className="brand-subname">Agronomy workspace</div>
            </div>
          </div>

          <div className="auth-hero__copy">
            <h1>把农技问答、识病和田间计划，放进一个能落地的工作台。</h1>
            <p>
              云寻 AI 面向农户、合作社和基层农技员，保留历史会话、模型偏好和诊断上下文，
              让每次回来都能从上次进度继续。
            </p>
          </div>

          <div className="auth-hero__meta">
            <span>运行模式：{backendMode}</span>
            <span>模型状态：{modelStatus}</span>
            <span>环境：{environment}</span>
            <span>后端地址：{backendUrl}</span>
          </div>

          {warnings.length > 0 && (
            <div className="mode-note" role="status">
              {warnings.map((warning) => (
                <div key={warning}>{warning}</div>
              ))}
            </div>
          )}
        </div>
      </section>

      <section className="auth-panel">
        <form className="auth-card" onSubmit={onSubmit}>
          <div className="auth-tabs" role="tablist" aria-label="认证模式">
            <button
              type="button"
              className={mode === "login" ? "auth-tab is-active" : "auth-tab"}
              onClick={() => onModeChange("login")}
            >
              登录
            </button>
            <button
              type="button"
              className={mode === "register" ? "auth-tab is-active" : "auth-tab"}
              onClick={() => onModeChange("register")}
            >
              注册
            </button>
          </div>

          <div className="field-stack">
            {mode === "register" && (
              <label className="field">
                <span>显示名称</span>
                <div className="field-control">
                  <UserRound size={18} />
                  <input
                    value={form.displayName}
                    onChange={(event) => onChange("displayName", event.target.value)}
                    placeholder="例如：老赵"
                    required
                  />
                </div>
              </label>
            )}

            <label className="field">
              <span>用户名</span>
              <div className="field-control">
                <UserRound size={18} />
                <input
                  value={form.username}
                  onChange={(event) => onChange("username", event.target.value)}
                  placeholder="英文字母、数字或下划线"
                  required
                />
              </div>
            </label>

            <label className="field">
              <span>密码</span>
              <div className="field-control">
                <LockKeyhole size={18} />
                <input
                  type="password"
                  value={form.password}
                  onChange={(event) => onChange("password", event.target.value)}
                  placeholder="至少 4 位"
                  required
                />
              </div>
            </label>
          </div>

          <button className="primary-button" type="submit" disabled={loading}>
            {loading ? "处理中..." : mode === "login" ? "登录并继续" : "注册并进入"}
          </button>

          <button className="secondary-button auth-guest-button" type="button" onClick={onGuestLogin} disabled={loading}>
            访客登录
          </button>

          <p className="auth-footnote">
            登录后会保留历史会话、模型偏好和诊断记录。访客登录也能直接进入，但更适合先体验功能。
          </p>
        </form>
      </section>
    </div>
  );
}
