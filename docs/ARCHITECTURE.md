# 架构

云寻由 React/Vite 前端、FastAPI 后端和 SQLite 数据库组成。浏览器通过 `/api` 调用认证和今日农活接口；所有建议都在本机规则引擎里生成，不访问任何外部模型服务。

今日农活建议由 `backend/app/services/decision.py` 按降雨概率、土壤湿度和生长期推导，输入校验在 `backend/app/schemas.py`，落库在 `backend/app/repositories.py`。用户数据包括用户、Token、农活记录和审计日志。

数据库通过 `PRAGMA user_version` 迁移，当前为 Schema 6。Schema 3 清理历史用户模型凭据表及会话关联列，Schema 4 增加会话置顶状态和排序索引，Schema 5 新增 `tool_records` 表保存农活建议历史，Schema 6 删除 `chat_sessions`、`chat_messages`、`idempotency_requests` 三张表并移除 `users.preferred_model`。`tool_records.kind` 的 CHECK 约束仍保留历史取值 `'vision'`，但接口只接受 `decision`。

列表接口使用游标分页：把上一页最后一条记录的 `(created_at, id)` 编码成不透明 cursor，避免数据持续写入时出现重复或漏读。认证使用数据库保存的不透明 Token，浏览器同时携带 Cookie 与 Bearer Token，写请求额外校验 CSRF Token。
