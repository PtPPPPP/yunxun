import { MessageItem } from "../../types";

export const STREAM_PLACEHOLDER = "正在生成回复…";

export interface OptimisticMessagePair {
  requestId: string;
  messages: MessageItem[];
}

export function createOptimisticMessagePair(
  content: string,
  requestId: string,
  createdAt = new Date().toISOString(),
): OptimisticMessagePair {
  return {
    requestId,
    messages: [
      {
        id: `local-user-${requestId}`,
        role: "user",
        content,
        created_at: createdAt,
        delivery_status: "pending",
        client_request_id: requestId,
      },
      {
        id: `local-assistant-${requestId}`,
        role: "assistant",
        content: STREAM_PLACEHOLDER,
        created_at: createdAt,
        delivery_status: "pending",
        client_request_id: requestId,
      },
    ],
  };
}

export function commitOptimisticMessages(
  messages: MessageItem[],
  requestId: string,
  committedMessages: MessageItem[],
): MessageItem[] {
  const remaining = messages.filter((message) => message.client_request_id !== requestId);
  return [...remaining, ...committedMessages];
}

export function failOptimisticMessages(messages: MessageItem[], requestId: string): MessageItem[] {
  return messages.map((message) => {
    if (message.client_request_id !== requestId) {
      return message;
    }
    if (message.role === "assistant") {
      return {
        ...message,
        content: "回复失败，原问题已放回输入框，可以直接重试。",
        delivery_status: "failed",
      };
    }
    return { ...message, delivery_status: "failed" };
  });
}

export function removeOptimisticMessages(messages: MessageItem[], requestId: string): MessageItem[] {
  return messages.filter((message) => message.client_request_id !== requestId);
}

export function mergeOlderMessages(current: MessageItem[], older: MessageItem[]): MessageItem[] {
  const existing = new Set(current.map((message) => message.id));
  return [...older.filter((message) => !existing.has(message.id)), ...current];
}

export function restoreDraftAfterFailure(currentDraft: string, failedPrompt: string): string {
  return currentDraft || failedPrompt;
}

export function shouldApplySessionResponse(activeSessionId: string | null, responseSessionId: string): boolean {
  return activeSessionId === responseSessionId;
}

/** 把流式增量追加到当前请求的乐观 assistant 消息上；首个增量替换占位文案。 */
export function appendStreamingDelta(messages: MessageItem[], requestId: string, delta: string): MessageItem[] {
  return messages.map((message) => {
    if (message.client_request_id !== requestId || message.role !== "assistant") {
      return message;
    }
    const base = message.content === STREAM_PLACEHOLDER ? "" : message.content;
    return { ...message, content: base + delta };
  });
}

/** 重新生成的流式增量：替换最后一条 assistant 消息内容；若最后一条是用户消息则先补一个占位回复。 */
export function applyRegenerateDelta(
  messages: MessageItem[],
  requestId: string,
  delta: string,
  isFirstDelta: boolean,
): MessageItem[] {
  const last = messages[messages.length - 1];
  if (!last || last.role !== "assistant") {
    return [
      ...messages,
      {
        id: `local-assistant-${requestId}`,
        role: "assistant",
        content: delta,
        created_at: new Date().toISOString(),
        delivery_status: "pending",
        client_request_id: requestId,
      },
    ];
  }
  const next = [...messages];
  next[next.length - 1] = {
    ...last,
    content: isFirstDelta ? delta : last.content + delta,
  };
  return next;
}

/** 流式结束后用落库的 assistant 消息替换本地临时消息。 */
export function finalizeRegenerate(
  messages: MessageItem[],
  requestId: string,
  assistantMessage: MessageItem,
): MessageItem[] {
  const index = messages.findIndex(
    (message) => message.id === assistantMessage.id || message.client_request_id === requestId,
  );
  if (index < 0) return [...messages, assistantMessage];
  const next = [...messages];
  next[index] = assistantMessage;
  return next;
}
