import { describe, expect, it } from "vitest";

import { MessageItem } from "../../types";
import {
  appendStreamingDelta,
  applyRegenerateDelta,
  commitOptimisticMessages,
  createOptimisticMessagePair,
  failOptimisticMessages,
  finalizeRegenerate,
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

describe("streaming state helpers", () => {
  const optimistic = createOptimisticMessagePair("问题", "request-1", "2026-07-10T00:00:00Z").messages;

  it("首个流式增量替换占位文案，后续增量依次追加", () => {
    const first = appendStreamingDelta(optimistic, "request-1", "今天先");
    expect(first[1].content).toBe("今天先");

    const second = appendStreamingDelta(first, "request-1", "查虫口");
    expect(second[1].content).toBe("今天先查虫口");
    expect(second[0]).toBe(optimistic[0]);
  });

  it("流式增量不影响其他消息和别的请求", () => {
    const next = appendStreamingDelta(optimistic, "request-other", "无关增量");
    expect(next).toEqual(optimistic);
  });

  it("重新生成增量替换最后一条 assistant 消息内容", () => {
    const messages = [
      optimistic[0],
      { id: "a1", role: "assistant" as const, content: "旧回答", created_at: "1" },
    ];
    const first = applyRegenerateDelta(messages, "regen-1", "新", true);
    expect(first[1].content).toBe("新");
    const second = applyRegenerateDelta(first, "regen-1", "回答", false);
    expect(second[1].content).toBe("新回答");
  });

  it("最后一条是用户消息时，重新生成增量会补一个占位回复", () => {
    const next = applyRegenerateDelta([optimistic[0]], "regen-2", "新回答", true);
    expect(next).toHaveLength(2);
    expect(next[1]).toMatchObject({ role: "assistant", content: "新回答", client_request_id: "regen-2" });
  });

  it("finalizeRegenerate 用落库消息替换本地临时消息", () => {
    const streamed = applyRegenerateDelta([optimistic[0]], "regen-3", "草稿内容", true);
    const persisted: MessageItem = { id: "assistant-9", role: "assistant", content: "最终回答", created_at: "9" };
    const finalized = finalizeRegenerate(streamed, "regen-3", persisted);
    expect(finalized).toHaveLength(2);
    expect(finalized[1]).toEqual(persisted);
  });
});
