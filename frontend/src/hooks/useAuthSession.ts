import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

import { useAsyncGuard } from "./useAsyncGuard";
import { useSessionBoundary, useSessionGuard } from "./useSessionBoundary";
import { api, getApiErrorInfo, getErrorMessage } from "../lib/api";
import { clearLogoutIntent, readLogoutIntent, saveLogoutIntent } from "../lib/logoutIntent";
import { HealthPayload, User } from "../types";

export type SessionResetReason = "login" | "logout" | "expired";
interface AuthSessionOptions {
  onError: (message: string) => void;
  onNotice: (message: string) => void;
  onSessionReset: (reason: SessionResetReason) => void;
}

/** 认证与会话状态的唯一入口；业务草稿由 App 在边界回调中清理。 */
export function useAuthSession({ onError, onNotice, onSessionReset }: AuthSessionOptions) {
  const { advance, capture, isCurrent } = useSessionBoundary();
  const sessionCurrent = useSessionGuard();
  const sessionId = useRef("");
  const [logoutPending, setLogoutPending] = useState(readLogoutIntent);
  const { run: runLogout, busy: logoutBusy } = useAsyncGuard();
  const [health, setHealth] = useState<HealthPayload | null>(null);
  const [bootLoading, setBootLoading] = useState(true);
  const [user, setUser] = useState<User | null>(null);
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [recovering, setRecovering] = useState(false);
  const [authForm, setAuthForm] = useState({ username: "", password: "", displayName: "" });
  const [settingsName, setSettingsName] = useState("");
  const authAction = useAsyncGuard();
  const settingsAction = useAsyncGuard();

  const confirmLogout = useCallback(async (intent: string, ticket: number) => {
    await runLogout(async () => {
      if (!isCurrent(ticket) || readLogoutIntent() !== intent) return;
      let confirmed = false;
      let failureMessage = "退出尚未确认，当前资料已隐藏。请检查网络后重试；确认前请勿将设备交给他人。";
      try {
        await api.post("/api/auth/logout", { session_id: intent });
        confirmed = true;
      } catch (requestError) {
        const status = getApiErrorInfo(requestError).status;
        if (status === 409) failureMessage = "退出尚未确认：当前会话已变化，已停止旧退出请求以保护新登录账号，资料继续隐藏。";
        if (status === 403) failureMessage = "退出尚未确认：安全校验未通过，请刷新页面后重试。当前资料已隐藏。";
        // 未送达与响应丢失都先核对；只有 401 能确认服务端会话失效。
        if (!isCurrent(ticket)) return;
        try { await api.get("/api/me"); }
        catch (requestError) { confirmed = getApiErrorInfo(requestError).status === 401; }
      }
      if (!isCurrent(ticket) || readLogoutIntent() !== intent) return;
      if (confirmed) {
        clearLogoutIntent(intent);
        setLogoutPending(null);
        onError("");
        onNotice("已确认退出登录。");
      } else {
        onError(failureMessage);
      }
    });
  }, [runLogout, isCurrent, onError, onNotice]);

  useEffect(() => {
    let cancelled = false;
    const ticket = capture();
    const current = () => !cancelled && isCurrent(ticket);
    async function bootstrap() {
      try {
        const response = await api.get<HealthPayload>("/api/health");
        if (!current()) return;
        setHealth(response.data);
        await api.get("/api/auth/csrf");
        if (!current()) return;
        const pending = readLogoutIntent();
        if (pending) {
          await confirmLogout(pending, ticket);
          return;
        }
        try {
          const me = await api.get<{ user: User; session_id: string }>("/api/me");
          if (!current() || readLogoutIntent()) return;
          sessionId.current = me.data.session_id;
          setUser(me.data.user);
          setSettingsName(me.data.user.display_name);
        } catch {
          // 未登录时保留认证界面。
        }
      } catch (requestError) {
        if (current()) onError(getErrorMessage(requestError, "后端未连接，请先启动服务。"));
      } finally {
        if (current()) setBootLoading(false);
      }
    }
    void bootstrap();
    return () => { cancelled = true; };
  }, [capture, isCurrent, confirmLogout, onError]);

  useEffect(() => {
    const retry = () => {
      const pending = readLogoutIntent();
      if (pending) void confirmLogout(pending, capture());
    };
    window.addEventListener("online", retry);
    return () => window.removeEventListener("online", retry);
  }, [capture, confirmLogout]);

  function applyAuthenticatedUser(nextUser: User, nextSessionId: string, ticket: number) {
    if (!isCurrent(ticket)) return;
    sessionId.current = nextSessionId;
    onSessionReset("login");
    onError("");
    onNotice("");
    setUser(nextUser);
    setSettingsName(nextUser.display_name);
    setAuthForm({ username: "", password: "", displayName: "" });
  }

  async function handleAuthSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (readLogoutIntent() || logoutBusy) return;
    await authAction.run(async () => {
      const ticket = advance();
      onError("");
      try {
        const endpoint = authMode === "login" ? "/api/auth/login" : "/api/auth/register";
        const payload = authMode === "login"
          ? { username: authForm.username, password: authForm.password }
          : { username: authForm.username, password: authForm.password, display_name: authForm.displayName };
        const response = await api.post<{ user: User; session_id: string }>(endpoint, payload);
        applyAuthenticatedUser(response.data.user, response.data.session_id, ticket);
      } catch (requestError) {
        if (isCurrent(ticket)) onError(getErrorMessage(requestError));
      }
    });
  }

  async function handleGuestLogin() {
    if (readLogoutIntent() || logoutBusy) return;
    await authAction.run(async () => {
      const ticket = advance();
      onError("");
      try {
        const response = await api.post<{ user: User; session_id: string }>("/api/auth/guest");
        applyAuthenticatedUser(response.data.user, response.data.session_id, ticket);
      } catch (requestError) {
        if (isCurrent(ticket)) onError(getErrorMessage(requestError));
      }
    });
  }

  async function handleSaveSettings() {
    if (!sessionCurrent()) return;
    await settingsAction.run(async () => {
      const ticket = capture();
      if (!settingsName.trim()) { onError("显示名称不能为空。"); return; }
      try {
        const response = await api.patch<{ user: User }>("/api/me/profile", { display_name: settingsName });
        if (!isCurrent(ticket)) return;
        setUser(response.data.user);
        setSettingsName(response.data.user.display_name);
        onError("");
      } catch (requestError) {
        if (isCurrent(ticket)) onError(getErrorMessage(requestError));
      }
    });
  }

  async function handleLogout(username = "") {
    if (!sessionCurrent() || logoutBusy) return;
    const intent = sessionId.current;
    try { saveLogoutIntent(intent); }
    catch { onError("无法保存退出状态，请允许浏览器保存本站数据后重试退出。"); return; }
    const ticket = advance();
    setLogoutPending(intent);
    onSessionReset("logout");
    setUser(null);
    setSettingsName("");
    setAuthMode("login");
    setAuthForm({ username, password: "", displayName: "" });
    onNotice("");
    onError("");
    await confirmLogout(intent, ticket);
  }

  function returnToLogin(username: string, message = "") {
    if (!sessionCurrent()) return;
    advance();
    onSessionReset("expired");
    setUser(null);
    setRecovering(false);
    onError("");
    onNotice(message);
    setAuthMode("login");
    setAuthForm({ username, password: "", displayName: "" });
  }

  function acceptGuestUpgrade(saved: User, nextSessionId: string) {
    if (!sessionCurrent()) return;
    advance();
    sessionId.current = nextSessionId;
    setUser(saved);
    setSettingsName(saved.display_name);
    onError("");
    onNotice(`账号已保存为 ${saved.username}，原有数据全部保留。`);
  }

  function startRecovery() {
    setRecovering(true);
    onError("");
    onNotice("");
    setAuthForm({ username: "", password: "", displayName: "" });
  }

  return {
    health, bootLoading, user, logoutPending, logoutBusy,
    retryLogout: () => { if (logoutPending) void confirmLogout(logoutPending, capture()); },
    authMode, setAuthMode, authForm, setAuthForm, authBusy: authAction.busy,
    handleAuthSubmit, handleGuestLogin, handleLogout,
    settingsName, setSettingsName, settingsBusy: settingsAction.busy, handleSaveSettings,
    recovering, startRecovery, returnToLogin, acceptGuestUpgrade,
  };
}
