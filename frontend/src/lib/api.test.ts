import { AxiosError, AxiosHeaders } from "axios";
import { describe, expect, it } from "vitest";

import { getApiErrorInfo } from "./api";

function error(status: number, data: object = {}, requestId = "request-123") {
  return new AxiosError("failed", undefined, undefined, undefined, {
    status,
    statusText: "failed",
    data,
    headers: new AxiosHeaders({ "x-request-id": requestId }),
    config: { headers: new AxiosHeaders() },
  });
}

describe("getApiErrorInfo", () => {
  it.each([
    [401, "登录已失效", false],
    [403, "没有权限", false],
    [404, "不存在", false],
    [422, "格式不正确", false],
    [429, "太频繁", true],
    [500, "暂时不可用", true],
  ])("映射状态 %s", (status, text, retryable) => {
    const result = getApiErrorInfo(error(status as number));
    expect(result.message).toContain(text);
    expect(result.retryable).toBe(retryable);
    expect(result.requestId).toBe("request-123");
  });

  it("优先采用安全业务错误和错误码", () => {
    const result = getApiErrorInfo(error(409, { error: "幂等键冲突。", code: "IDEMPOTENCY_CONFLICT" }));
    expect(result).toMatchObject({ message: "幂等键冲突。", code: "IDEMPOTENCY_CONFLICT", status: 409, retryable: false });
  });

  it("网络中断可安全重试", () => {
    expect(getApiErrorInfo(new AxiosError("network")).retryable).toBe(true);
  });
});
