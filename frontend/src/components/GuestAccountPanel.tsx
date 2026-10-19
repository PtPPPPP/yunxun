import { FormEvent, useState } from "react";

import { useAsyncGuard } from "../hooks/useAsyncGuard";
import { api, getApiErrorInfo, getErrorMessage } from "../lib/api";
import { User } from "../types";

interface GuestAccountPanelProps {
  user: User;
  onSaved: (user: User) => void;
  onReturnToLogin: (username: string) => void;
}

export function GuestAccountPanel({ user, onSaved, onReturnToLogin }: GuestAccountPanelProps) {
  const [expanded, setExpanded] = useState(false);
  const [form, setForm] = useState({ username: "", password: "", confirmation: "", display_name: user.display_name });
  const [error, setError] = useState("");
  const [needsCheck, setNeedsCheck] = useState(false);
  const [needsLogin, setNeedsLogin] = useState(false);
  const action = useAsyncGuard();

  async function checkResult(fallback: string) {
    try {
      const response = await api.get<{ user: User }>("/api/me");
      if (response.data.user.id === user.id && !response.data.user.is_guest) {
        onSaved(response.data.user);
        return;
      }
      if (response.data.user.id !== user.id) {
        setError("当前登录账号已变化，请返回登录后确认账号。");
        setNeedsLogin(true);
        return;
      }
      setNeedsCheck(false);
      setNeedsLogin(false);
      setError(fallback);
    } catch (requestError) {
      if (getApiErrorInfo(requestError).status === 401) {
        setNeedsLogin(true);
        setError("会话已失效，账号可能已经保存。请使用刚设置的用户名和密码登录确认，原有数据仍归原账号。");
      } else {
        setNeedsCheck(true);
        setError("暂时无法核对保存结果。请保留已填写的凭据，不要退出当前访客会话，网络恢复后再核对。");
      }
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const payload = { username: form.username.trim(), password: form.password, display_name: form.display_name.trim() };
    if (!/^[A-Za-z0-9_]{3,32}$/.test(payload.username)) { setError("用户名需为 3–32 位英文字母、数字或下划线。"); return; }
    if (payload.password.length < 4 || payload.password.length > 64 || !payload.password.trim()) { setError("密码需为 4–64 位，不能全为空格。"); return; }
    if (payload.password !== form.confirmation) { setError("两次输入的密码不一致。"); return; }
    if (!payload.display_name || payload.display_name.length > 32) { setError("显示名称需为 1–32 个字符。"); return; }
    await action.run(async () => {
      setError("");
      try {
        const response = await api.post<{ user: User }>("/api/auth/upgrade-guest", payload);
        onSaved(response.data.user);
      } catch (requestError) {
        const info = getApiErrorInfo(requestError);
        const failureMessage = info.status === 403 ? "账号或安全校验未通过，请刷新页面后重试。" : getErrorMessage(requestError);
        setError(failureMessage);
        if (info.retryable || info.status === 401 || info.status === 403 || info.code === "GUEST_ALREADY_UPGRADED") {
          setNeedsCheck(true);
          await checkResult(info.status === 403 ? failureMessage : "当前仍是访客，尚未保存账号，可以重试。");
        }
      }
    });
  }

  function close() {
    setExpanded(false);
    setForm({ username: "", password: "", confirmation: "", display_name: user.display_name });
    setError("");
    setNeedsCheck(false);
    setNeedsLogin(false);
  }

  return <section className="panel guest-account-panel" aria-label="保存访客账号">
    {!expanded ? <div className="home-actions"><div><h3>保存账号，下次接着用</h3><p>你正在使用访客。设置账号后，原有地块和记录全部保留。</p></div>
      <button className="primary-button" type="button" onClick={() => { setForm((current) => ({ ...current, display_name: user.display_name })); setExpanded(true); }}>保存账号</button></div>
      : <form onSubmit={(event) => void submit(event)} noValidate>
        <h3>保存为正式账号</h3><p>已有地块与记录全部保留，下次使用新用户名和密码登录。</p>
        <fieldset disabled={action.busy} className="guest-account-fields">
          <div className="field-grid">
            <label className="field"><span>正式用户名</span><div className="field-control"><input disabled={needsLogin} autoComplete="username" maxLength={32} value={form.username} onChange={(event) => setForm((current) => ({ ...current, username: event.target.value }))} /></div></label>
            <label className="field"><span>账号显示名称</span><div className="field-control"><input disabled={needsLogin} maxLength={32} value={form.display_name} onChange={(event) => setForm((current) => ({ ...current, display_name: event.target.value }))} /></div></label>
            <label className="field"><span>登录密码</span><div className="field-control"><input disabled={needsLogin} type="password" autoComplete="new-password" maxLength={64} value={form.password} onChange={(event) => setForm((current) => ({ ...current, password: event.target.value }))} /></div></label>
            <label className="field"><span>再次输入密码</span><div className="field-control"><input disabled={needsLogin} type="password" autoComplete="new-password" maxLength={64} value={form.confirmation} onChange={(event) => setForm((current) => ({ ...current, confirmation: event.target.value }))} /></div></label>
          </div>
          <div className="inline-actions"><button className="primary-button" type="submit" disabled={needsLogin || needsCheck}>{action.busy ? "保存中…" : "确认保存账号"}</button>
            {!needsLogin && !needsCheck && <button className="ghost-button" type="button" onClick={close}>取消</button>}
            {needsCheck && !needsLogin && <button className="ghost-button" type="button" onClick={() => void action.run(() => checkResult("当前仍是访客，可以重试保存。"))}>核对保存结果</button>}
            {needsLogin && <button className="secondary-button" type="button" onClick={() => onReturnToLogin(form.username.trim())}>返回登录</button>}
          </div>
        </fieldset>
        {error && <p className="form-warning" role="alert">{error}</p>}
      </form>}
  </section>;
}
