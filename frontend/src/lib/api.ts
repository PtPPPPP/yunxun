import axios from "axios";

const configuredBaseURL = import.meta.env.VITE_YUNXUN_API_BASE_URL?.trim().replace(/\/+$/, "");
const baseURL = configuredBaseURL || "http://127.0.0.1:8001";

export const api = axios.create({
  baseURL,
  timeout: 45000,
});

export function setAuthToken(token: string | null): void {
  if (!token) {
    delete api.defaults.headers.common.Authorization;
    return;
  }

  api.defaults.headers.common.Authorization = `Bearer ${token}`;
}

export function getErrorMessage(error: unknown, fallback = "请求失败，请稍后重试。"): string {
  if (axios.isAxiosError(error)) {
    const payload = error.response?.data as { error?: string } | undefined;
    if (payload?.error) {
      return payload.error;
    }
  }

  if (error instanceof Error && error.message) {
    return error.message;
  }

  return fallback;
}
