const TOKEN_STORAGE_KEY = "yunxun.auth.token";

export function readStoredAuthToken(): string {
  try {
    return window.localStorage.getItem(TOKEN_STORAGE_KEY) ?? "";
  } catch {
    return "";
  }
}

export function persistAuthToken(token: string): void {
  try {
    if (!token) {
      window.localStorage.removeItem(TOKEN_STORAGE_KEY);
      return;
    }
    window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
  } catch {
    throw new Error("浏览器无法保存登录状态，请检查隐私模式或存储权限。");
  }
}

export function clearStoredAuthToken(): void {
  try {
    window.localStorage.removeItem(TOKEN_STORAGE_KEY);
  } catch {
    // localStorage 不可用时，内存态退出仍可继续完成。
  }
}
