import axios, { AxiosError } from "axios";

const configuredBaseURL = import.meta.env.VITE_YUNXUN_API_BASE_URL?.trim().replace(/\/+$/, "");
const baseURL = configuredBaseURL || "http://127.0.0.1:8001";
const REQUEST_TIMEOUT_MS = 45000;

export const api = axios.create({
  baseURL,
  timeout: REQUEST_TIMEOUT_MS,
});

export function setAuthToken(token: string | null): void {
  if (!token) {
    delete api.defaults.headers.common.Authorization;
    return;
  }

  api.defaults.headers.common.Authorization = `Bearer ${token}`;
}

interface ApiErrorPayload {
  success?: false;
  error?: string;
  code?: string;
  detail?: unknown;
}

export interface ApiErrorInfo {
  code?: string;
  message: string;
  status?: number;
  requestId?: string;
  retryable: boolean;
}

function isApiErrorPayload(value: unknown): value is ApiErrorPayload {
  return typeof value === "object" && value !== null;
}

function messageByStatus(status: number | undefined): string {
  if (status === 401) {
    return "登录已失效，请重新登录。";
  }
  if (status === 403) {
    return "你没有权限执行这个操作。";
  }
  if (status === 404) {
    return "要访问的内容不存在或已被删除。";
  }
  if (status === 413) {
    return "上传内容过大，请压缩后再试。";
  }
  if (status === 422) {
    return "提交内容格式不正确，请检查后再试。";
  }
  if (status === 429) {
    return "操作太频繁了，请稍后再试。";
  }
  if (status && status >= 500) {
    return "后端服务暂时不可用，请稍后重试。";
  }
  return "请求失败，请稍后重试。";
}

function axiosErrorMessage(error: AxiosError, fallback: string): string {
  if (error.code === "ECONNABORTED") {
    return "请求超时，请检查网络或稍后重试。";
  }
  if (!error.response) {
    return "无法连接后端服务，请确认后端已启动。";
  }

  const payload = error.response.data;
  if (isApiErrorPayload(payload) && typeof payload.error === "string" && payload.error.trim()) {
    return payload.error;
  }

  return messageByStatus(error.response.status) || fallback;
}

export function getErrorMessage(error: unknown, fallback = "请求失败，请稍后重试。"): string {
  return getApiErrorInfo(error, fallback).message;
}

export function getApiErrorInfo(error: unknown, fallback = "请求失败，请稍后重试。"): ApiErrorInfo {
  if (axios.isAxiosError(error)) {
    const status = error.response?.status;
    const payload = error.response?.data;
    return {
      code: isApiErrorPayload(payload) && typeof payload.code === "string" ? payload.code : undefined,
      message: axiosErrorMessage(error, fallback),
      status,
      requestId: error.response?.headers?.["x-request-id"],
      retryable: !status || status === 408 || status === 429 || status >= 500,
    };
  }

  if (error instanceof Error && error.message) {
    return { message: error.message, retryable: false };
  }

  return { message: fallback, retryable: false };
}
