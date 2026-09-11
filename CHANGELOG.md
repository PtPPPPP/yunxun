# 更新日志

## 未发布（V1.1 候选）

- 新增诊断历史统计面板：图片诊断与今日农活建议结果落库（Schema 5 新增 tool_records 表），提供 /api/tool-records 与 /api/tool-records/stats 接口，前端新增"统计面板"入口，展示使用汇总、近 14 天趋势、作物分布和历史记录。
- 聊天流式输出：发送消息与重新生成改用 SSE 增量输出（/api/chat/sessions/{id}/messages/stream、/regenerate/stream），前端基于 fetch + ReadableStream 实现打字机效果与光标指示；原非流式接口保留，幂等与限流行为不变。

## 1.0.0 - 2026-07-12

- 完成聊天乐观状态、失败恢复、会话竞态保护和长会话游标分页。
- 认证 Token 改为带服务端 Secret 的 HMAC-SHA256 摘要存储。
- 幂等状态持久化到 SQLite，支持租约、冲突、回放和过期清理。
- 建立 Schema 版本迁移、WAL、复合索引、并发与故障恢复测试。
- 增加真实 Chromium 桌面端、移动端、失败恢复和长会话滚动 E2E。
- 增加生产配置校验、CI、数据库备份恢复工具、发布检查和回滚流程。

已知限制：SQLite 仅适合单机小规模部署；浏览器取消不能真正中止第三方模型请求。
