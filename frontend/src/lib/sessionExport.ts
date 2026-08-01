import { MessageItem, SessionItem } from "../types";

// eslint-disable-next-line no-control-regex
const ILLEGAL_FILENAME_CHARS = /[<>:"/\\|?*\u0000-\u001f]/g;

export function safeExportFilename(title: string, extension: "txt" | "md"): string {
  const normalized = title.trim().replace(ILLEGAL_FILENAME_CHARS, "_").replace(/\s+/g, " ").slice(0, 60);
  return `${normalized || "云寻会话"}.${extension}`;
}

function roleLabel(role: MessageItem["role"]): string {
  return role === "user" ? "用户" : "云寻AI";
}

export function buildSessionExport(
  session: SessionItem,
  messages: MessageItem[],
  format: "txt" | "md",
  exportedAt = new Date(),
): { filename: string; content: string; mimeType: string } {
  const exportTime = exportedAt.toLocaleString("zh-CN");
  if (format === "md") {
    const lines = [
      "# 云寻智慧农业AI工作台软件",
      "",
      `- 会话标题：${session.title}`,
      `- 导出时间：${exportTime}`,
      "",
      ...messages.flatMap((message) => [
        `## ${roleLabel(message.role)} · ${message.created_at}`,
        "",
        message.content,
        "",
      ]),
    ];
    return { filename: safeExportFilename(session.title, "md"), content: lines.join("\n"), mimeType: "text/markdown;charset=utf-8" };
  }

  const lines = [
    "云寻智慧农业AI工作台软件",
    `会话标题：${session.title}`,
    `导出时间：${exportTime}`,
    "",
    ...messages.flatMap((message) => [`${roleLabel(message.role)}（${message.created_at}）`, message.content, ""]),
  ];
  return { filename: safeExportFilename(session.title, "txt"), content: lines.join("\n"), mimeType: "text/plain;charset=utf-8" };
}

export function downloadTextFile(filename: string, content: string, mimeType: string): void {
  const blob = new Blob(["\ufeff", content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}
