# 更新日志

## 未发布

- 移除全部 AI 能力：删除「智能问答」（`/api/chat/*`、会话与消息服务、SSE 流式输出、幂等存储）和「田间诊断」（`/api/vision`、图片校验工具）两个模块，后端不再接入任何模型服务，`openai` 依赖已从 `requirements.txt` 移除。前端只保留「今日农活」与「统计面板」。
- 品牌改名：软著全称改为「云寻智慧农业工作台软件」，简称改为「云寻」，界面、页面标题、系统提示、发布脚本和测试同步更新。`docs/software-copyright/final-delivery/` 中的 V1.0 归档按历史快照保留，未被改写。
- 数据库 Schema 6：删除 `chat_sessions`、`chat_messages`、`idempotency_requests` 三张表，并移除 `users.preferred_model`。**该迁移会丢弃既有会话与消息数据**，升级前必须备份。
- 统计面板精简为只统计今日农活记录：去掉图片诊断卡片、类型筛选和 vision 徽章，新增覆盖作物与近 14 天记录数，`/api/tool-records/stats` 不再返回 `total_sessions` 与 `total_messages`。
- 用户画像只剩显示名称：`PATCH /api/me/profile` 与 `PATCH /api/auth/profile` 不再接受 `preferred_model`。
- 配置裁剪：移除 `DOUBAO_*`、`YUNXUN_AI_*`、`YUNXUN_MAX_MESSAGE_LENGTH`、`YUNXUN_UPLOAD_MAX_BYTES`、`YUNXUN_IDEMPOTENCY_WINDOW_SECONDS` 和 `YUNXUN_DEFAULT_PAGE_SIZE`/`YUNXUN_MAX_PAGE_SIZE`。
- 测试与门禁重写：E2E 改为 `frontend/e2e/decision.spec.ts`（访客登录、生成建议、统计面板、帮助与关于、移动端导航、无 API Key 入口），`scripts/release_rehearsal.py` 与 `scripts/http_load_test.py` 改为农活与统计流程，后者现在会对任何非 2xx 响应失败。

## 1.0.0 - 2026-07-12

- 完成聊天乐观状态、失败恢复、会话竞态保护和长会话游标分页。
- 认证 Token 改为带服务端 Secret 的 HMAC-SHA256 摘要存储。
- 幂等状态持久化到 SQLite，支持租约、冲突、回放和过期清理。
- 建立 Schema 版本迁移、WAL、复合索引、并发与故障恢复测试。
- 增加真实 Chromium 桌面端、移动端、失败恢复和长会话滚动 E2E。
- 增加生产配置校验、CI、数据库备份恢复工具、发布检查和回滚流程。

已知限制：SQLite 仅适合单机小规模部署。
