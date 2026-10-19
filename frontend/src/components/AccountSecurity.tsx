import { FormEvent, useState } from "react";

import { useAsyncGuard } from "../hooks/useAsyncGuard";
import { api, getApiErrorInfo, getErrorMessage } from "../lib/api";

function passwordError(password: string, confirmation: string) {
  if (password.length < 8 || password.length > 64 || !password.trim()) return "新密码需为 8–64 位，不能全为空格。";
  if (password !== confirmation) return "两次输入的新密码不一致。";
  return "";
}

function NewPasswordFields({ password, confirmation, onPassword, onConfirmation }: {
  password: string; confirmation: string; onPassword: (value: string) => void; onConfirmation: (value: string) => void;
}) {
  return <>
    <label className="field"><span>新密码</span><input type="password" autoComplete="new-password" required minLength={8} maxLength={64} value={password} onChange={(event) => onPassword(event.target.value)} /></label>
    <label className="field"><span>再次输入新密码</span><input type="password" autoComplete="new-password" required maxLength={64} value={confirmation} onChange={(event) => onConfirmation(event.target.value)} /></label>
  </>;
}

export function AccountSecurity({ onReturnToLogin }: { onReturnToLogin: (message: string) => void }) {
  const [oldPassword, setOldPassword] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [proof, setProof] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [uncertain, setUncertain] = useState(false);
  const action = useAsyncGuard();

  async function change(event: FormEvent) {
    event.preventDefault();
    const validation = passwordError(password, confirmation);
    if (validation) { setError(validation); return; }
    await action.run(async () => {
      setError(""); setUncertain(false);
      try {
        const response = await api.post<{ message: string }>("/api/auth/change-password", { current_password: oldPassword, new_password: password });
        onReturnToLogin(response.data.message);
      } catch (requestError) {
        const info = getApiErrorInfo(requestError);
        const unknown = !info.status || info.status >= 500 || info.status === 401;
        setUncertain(unknown);
        setError(unknown ? "改密结果未确认或会话已失效。请返回登录尝试新密码；若原密码仍有效，可登录后重试。" : info.message);
      }
    });
  }

  async function generate(event: FormEvent) {
    event.preventDefault();
    await action.run(async () => {
      setError(""); setCode("");
      try {
        const response = await api.post<{ recovery_code: string }>("/api/auth/recovery-code", { current_password: proof });
        setCode(response.data.recovery_code); setProof("");
      } catch (requestError) {
        const info = getApiErrorInfo(requestError);
        setError(info.retryable ? "未能确认生成结果，旧码可能已失效。请重新生成并以最后收到的恢复码为准。" : info.message);
      }
    });
  }

  return <section className="panel account-security" aria-label="账号安全设置">
    <h3>修改密码</h3>
    <p>成功后全部设备都需重新登录，旧恢复码也会失效。原有地块和记录保留。</p>
    {error && <p role="alert">{error}</p>}
    {uncertain && <button type="button" className="secondary-button" onClick={() => onReturnToLogin("请使用新密码登录核对改密结果；若原密码仍有效，可登录后重试。")}>返回登录核对</button>}
    <form className="field-stack" onSubmit={change}>
      <label className="field"><span>原密码</span><input type="password" autoComplete="current-password" required maxLength={64} value={oldPassword} onChange={(event) => setOldPassword(event.target.value)} /></label>
      <NewPasswordFields password={password} confirmation={confirmation} onPassword={setPassword} onConfirmation={setConfirmation} />
      <button className="primary-button" disabled={action.busy} type="submit">修改密码并退出全部设备</button>
    </form>
    <h3>离线恢复码</h3>
    <p>由你本人离线保管，只展示一次、只能成功使用一次。重新生成会替换旧码。生成恢复码不会退出当前会话。</p>
    <p>恢复码和密码都丢失时，请联系部署者线下核验身份后辅助恢复；无法核验时不能恢复。访客须先保存为正式账号。</p>
    {code ? <div className="recovery-secret" role="status"><p>请现在离线保存，关闭后无法再次查看。</p><code aria-label="本次恢复码">{code}</code><button className="secondary-button" type="button" onClick={() => setCode("")}>我已离线保存，关闭</button></div>
      : <form className="field-stack" onSubmit={generate}>
        <label className="field"><span>生成恢复码用的当前密码</span><input type="password" autoComplete="current-password" required maxLength={64} value={proof} onChange={(event) => setProof(event.target.value)} /></label>
        <button type="submit" className="secondary-button" disabled={action.busy}>生成或更换恢复码</button>
      </form>}
  </section>;
}

export function PasswordRecovery({ onReturnToLogin }: { onReturnToLogin: (username: string, message?: string) => void }) {
  const [username, setUsername] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [error, setError] = useState("");
  const action = useAsyncGuard();

  async function submit(event: FormEvent) {
    event.preventDefault();
    const validation = passwordError(password, confirmation);
    if (validation) { setError(validation); return; }
    await action.run(async () => {
      setError("");
      try {
        const response = await api.post<{ message: string }>("/api/auth/recover-password", { username: username.trim(), recovery_code: code.trim(), new_password: password });
        onReturnToLogin(username.trim(), response.data.message);
      } catch (requestError) { setError(getErrorMessage(requestError)); }
    });
  }

  return <section className="panel account-security recovery-page" aria-label="用恢复码重置密码">
    <h2>用恢复码重置密码</h2>
    <p>需要你之前离线保存的恢复码。成功后恢复码失效，全部设备需重新登录，原有记录保留。</p>
    <p>没有恢复码或已经丢失，请联系部署者线下核验身份后辅助恢复。用户名和显示名称不能作为恢复凭据。</p>
    {error && <p role="alert">{error}</p>}
    <form className="field-stack" onSubmit={submit}>
      <label className="field"><span>账号用户名</span><input autoComplete="username" required maxLength={32} value={username} onChange={(event) => setUsername(event.target.value)} /></label>
      <label className="field"><span>离线恢复码</span><input type="password" autoComplete="off" required maxLength={128} value={code} onChange={(event) => setCode(event.target.value)} /></label>
      <NewPasswordFields password={password} confirmation={confirmation} onPassword={setPassword} onConfirmation={setConfirmation} />
      <button type="submit" className="primary-button" disabled={action.busy}>确认重置密码</button>
      <button type="button" className="ghost-button" disabled={action.busy} onClick={() => onReturnToLogin(username)}>返回登录</button>
    </form>
    <p>若上次提交中断，可返回登录尝试新密码，再决定是否重试。</p>
  </section>;
}
