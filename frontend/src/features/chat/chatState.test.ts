import { describe, expect, it } from "vitest";

import { MessageItem } from "../../types";
import {
  commitOptimisticMessages,
  createOptimisticMessagePair,
  failOptimisticMessages,
  mergeOlderMessages,
  restoreDraftAfterFailure,
  shouldApplySessionResponse,
} from "./chatState";

const committedPair: MessageItem[] = [
  { id: "user-1", role: "user", content: "问题", created_at: "2026-07-10T00:00:00Z" },
  { id: "assistant-1", role: "assistant", content: "回答", created_at: "2026-07-10T00:00:01Z" },
];

describe("chat optimistic state", () => {
  it("creates an immediate user message and pending assistant message", () => {
    const pair = createOptimisticMessagePair("问题", "request-1", "2026-07-10T00:00:00Z");

    expect(pair.messages).toHaveLength(2);
    expect(pair.messages[0]).toMatchObject({ role: "user", content: "问题", delivery_status: "pending" });
    expect(pair.messages[1]).toMatchObject({ role: "assistant", delivery_status: "pending" });
  });

  it("replaces only the matching optimistic pair after success", () => {
    const previous: MessageItem = {
      id: "previous",
      role: "assistant",
      content: "上一条",
      created_at: "2026-07-09T00:00:00Z",
    };
    const optimistic = createOptimisticMessagePair("问题", "request-1").messages;

    const committed = commitOptimisticMessages([previous, ...optimistic], "request-1", committedPair);

    expect(committed).toEqual([previous, ...committedPair]);
  });

  it("marks a failed pair and keeps unrelated messages unchanged", () => {
    const previous = committedPair[0];
    const optimistic = createOptimisticMessagePair("问题", "request-1").messages;

    const failed = failOptimisticMessages([previous, ...optimistic], "request-1");

    expect(failed[0]).toBe(previous);
    expect(failed[1].delivery_status).toBe("failed");
    expect(failed[2]).toMatchObject({ delivery_status: "failed", role: "assistant" });
  });
});

describe("controller concurrency helpers", () => {
  it("旧会话响应不会应用到新会话", () => {
    expect(shouldApplySessionResponse("new-session", "old-session")).toBe(false);
    expect(shouldApplySessionResponse("new-session", "new-session")).toBe(true);
  });

  it("失败恢复不会覆盖用户新输入", () => {
    expect(restoreDraftAfterFailure("new draft", "failed prompt")).toBe("new draft");
    expect(restoreDraftAfterFailure("", "failed prompt")).toBe("failed prompt");
  });

  it("历史分页去重且保持顺序", () => {
    const current = [{ id: "2", role: "user" as const, content: "2", created_at: "2" }];
    const older = [
      { id: "1", role: "user" as const, content: "1", created_at: "1" },
      { id: "2", role: "user" as const, content: "duplicate", created_at: "2" },
    ];
    expect(mergeOlderMessages(current, older).map((message) => message.id)).toEqual(["1", "2"]);
  });
});
