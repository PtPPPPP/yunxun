// 只存退出意图和不可认证的会话引用，不存 Token、账号资料或密码。
const key = "yunxun.logout-pending";

export function readLogoutIntent(): string | null {
  return localStorage.getItem(key);
}

export function saveLogoutIntent(sessionId: string) {
  localStorage.setItem(key, sessionId);
}

export function clearLogoutIntent(sessionId: string) {
  // 迟到操作也不能清除另一次退出意图。
  if (readLogoutIntent() === sessionId) localStorage.removeItem(key);
}
