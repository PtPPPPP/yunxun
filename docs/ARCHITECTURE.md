# 架构

云寻由 React/Vite 前端、FastAPI 后端和 SQLite 数据库组成。浏览器通过 `/api` 调用认证和今日农活接口；所有建议都在本机规则引擎里生成，不访问任何外部模型服务。

业务主体是**地块**：`plots` 表登记面积、土壤类型与灌溉条件，当季作物与起止日期由**茬次**表 `plot_seasons` 承载（一块地同时只有一茬进行中，用部分唯一索引约束）；**农事台账** `farm_records` 挂在地块下，记录每次作业的类型、日期、用量、投入品名称、费用，以及采收的产量与单价，删除地块会连带删除它的记录与待办。**农事待办** `farm_tasks` 可以不关联地块（杂事），到期日在顶栏提示。今日农活建议由 `backend/app/services/decision.py` 按降雨概率、土壤湿度和生长期推导，与地块解耦，但支持从地块带入作物。地块、茬次、台账与待办的业务逻辑在 `backend/app/services/farm.py`，数据访问在 `backend/app/repositories.py`。用户数据包括用户、Token、地块、台账记录、待办、农活建议快照和审计日志。

数据库通过 `PRAGMA user_version` 迁移，当前为 Schema 9。Schema 3 清理历史用户模型凭据表及会话关联列，Schema 4 增加会话置顶状态和排序索引，Schema 5 新增 `tool_records` 表保存农活建议历史，Schema 6 删除 `chat_sessions`、`chat_messages`、`idempotency_requests` 三张表并移除 `users.preferred_model`，Schema 7 新增 `plots` 与 `farm_records` 两张表，Schema 8 给台账补上投入品、安全间隔期与采收产量字段并新增 `farm_tasks`，Schema 9 新增 `plot_seasons` 并把地块上的作物搬进茬次、删掉那两列。`tool_records.kind` 的 CHECK 约束仍保留历史取值 `'vision'`，但接口只接受 `decision`；新表刻意不再使用 CHECK 约束，作业类型的允许值集中在路由层校验，扩展时不必整表重建。

列表接口使用游标分页：把上一页最后一条记录的 `(created_at, id)` 编码成不透明 cursor，避免数据持续写入时出现重复或漏读。认证使用数据库保存的不透明 Token，浏览器同时携带 Cookie 与 Bearer Token，写请求额外校验 CSRF Token。
