import { api, readCookie } from "./api";
import { readStoredAuthToken } from "./tokenStorage";

interface StreamRequestOptions {
  body?: unknown;
  idempotencyKey?: string;
  signal?: AbortSignal;
  onDelta?: (text: string) => void;
}

export class StreamRequestError extends Error {
  status?: number;
  retryable: boolean;

  constructor(message: string, status?: number) {
    super(message);
    this.name = "StreamRequestError";
    this.status = status;
    this.retryable = !status || status === 408 || status === 429 || status >= 500;
  }
}

function statusFallbackMessage(status: number): string {
  if (status === 401) return "登录已失效，请重新登录。";
  if (status === 403) return "你没有权限执行这个操作。";
  if (status === 404) return "要访问的内容不存在或已被删除。";
  if (status === 413) return "上传内容过大，请压缩后再试。";
  if (status === 422) return "提交内容格式不正确，请检查后再试。";
  if (status === 429) return "操作太频繁了，请稍后再试。";
  if (status >= 500) return "后端服务暂时不可用，请稍后重试。";
  return "请求失败，请稍后重试。";
}

/**
 * 基于 fetch + ReadableStream 的 SSE 客户端。
 * 后端事件格式：event: delta|done|error + data: JSON。
 * 返回 done 事件的负载；delta 通过 onDelta 回调逐步产出；error 事件抛出 StreamRequestError。
 */
export async function streamChatRequest<T>(path: string, options: StreamRequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = readStoredAuthToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const csrfToken = readCookie("yunxun_csrf");
  if (csrfToken) headers["X-CSRF-Token"] = csrfToken;
  if (options.idempotencyKey) headers["X-Idempotency-Key"] = options.idempotencyKey;

  const baseURL = api.defaults.baseURL ?? "";
  let response: Response;
  try {
    response = await fetch(`${baseURL}${path}`, {
      method: "POST",
      headers,
      credentials: "include",
      body: JSON.stringify(options.body ?? {}),
      signal: options.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new StreamRequestError("无法连接后端服务，请确认后端已启动。");
  }

  if (!response.ok) {
    let detail = "";
    try {
      const payload = (await response.json()) as { error?: unknown };
      if (payload && typeof payload.error === "string" && payload.error.trim()) detail = payload.error;
    } catch {
      // 非 JSON 错误体时退回状态码文案。
    }
    throw new StreamRequestError(detail || statusFallbackMessage(response.status), response.status);
  }
  if (!response.body) {
    throw new StreamRequestError("当前浏览器不支持流式响应，请刷新页面后重试。");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const result: { payload: T | null } = { payload: null };
  let buffer = "";

  const dispatchBlock = (block: string) => {
    let event = "message";
    let data = "";
    for (const line of block.split("\n")) {
      if (line.startsWith("event: ")) event = line.slice("event: ".length);
      else if (line.startsWith("data: ")) data = line.slice("data: ".length);
    }
    if (!data) return;
    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(data) as Record<string, unknown>;
    } catch {
      return;
    }
    if (event === "delta") {
      if (typeof parsed.text === "string" && parsed.text) options.onDelta?.(parsed.text);
      return;
    }
    if (event === "done") {
      result.payload = parsed as T;
      return;
    }
    if (event === "error") {
      const message = typeof parsed.error === "string" && parsed.error ? parsed.error : "回复生成失败，请稍后重试。";
      const status = typeof parsed.status === "number" ? parsed.status : undefined;
      throw new StreamRequestError(message, status);
    }
  };

  while (true) {
    const { value, done } = await reader.read();
    if (value) {
      buffer += decoder.decode(value, { stream: true });
      let boundary = buffer.indexOf("\n\n");
      while (boundary >= 0) {
        const block = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        if (block.trim()) dispatchBlock(block);
        boundary = buffer.indexOf("\n\n");
      }
    }
    if (done) break;
  }
  if (buffer.trim()) dispatchBlock(buffer);

  if (result.payload === null) {
    throw new StreamRequestError("回复流意外中断，请重试。");
  }
  return result.payload;
}
