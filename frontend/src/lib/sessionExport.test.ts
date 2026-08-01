import { describe, expect, it } from "vitest";

import { buildSessionExport, safeExportFilename } from "./sessionExport";

const session = {
  id: "database-id",
  title: "  春季/玉米:巡查  ",
  feature: "chat",
  model_name: "demo",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  last_message: "",
  is_pinned: false,
  pinned_at: null,
};

const messages = [
  { id: "message-1", role: "user" as const, content: "查看叶片", created_at: "2026-01-01T01:00:00Z" },
  { id: "message-2", role: "assistant" as const, content: "建议补水", created_at: "2026-01-01T01:00:01Z" },
];

describe("session export", () => {
  it("cleans filename characters and keeps a bounded title", () => {
    expect(safeExportFilename(session.title, "txt")).toBe("春季_玉米_巡查.txt");
    expect(safeExportFilename("", "md")).toBe("云寻会话.md");
  });

  it("exports only visible conversation fields", () => {
    const exported = buildSessionExport(session, messages, "md", new Date("2026-01-02T03:04:05Z"));
    expect(exported.content).toContain("春季/玉米:巡查");
    expect(exported.content).toContain("查看叶片");
    expect(exported.content).toContain("建议补水");
    expect(exported.content).not.toContain("database-id");
    expect(exported.content).not.toContain("message-1");
    expect(exported.content).not.toContain("api_key");
  });
});
