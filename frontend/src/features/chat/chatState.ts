import { MessageItem } from "../../types";

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
        content: "正在生成回复…",
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
