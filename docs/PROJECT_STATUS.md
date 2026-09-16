# 项目状态

审计基线：Git `v1.0.0` / `b952778`，机器版本 `1.0.0`，文案版本 `V1.0.0`。

当前工作区已移除全部 AI 能力：智能问答、田间诊断、系统模型接入和相应品牌文案。保留认证、今日农活建议、统计面板、审计、备份发布链路和 SQLite 数据库。

## 功能矩阵

| 能力 | 状态 | 依据 |
| --- | --- | --- |
| 注册、登录、访客、退出 | 已实现并验证 | `backend/app/api/routes/auth.py`、`backend/tests/test_auth_tokens.py` |
| 今日农活建议 | 已实现并验证 | `backend/app/services/decision.py`、`backend/tests/test_decision_service.py` |
| 农活记录落库、列表与统计（tool_records） | 已实现并验证 | `backend/app/core/database.py`（Schema 5）、`backend/app/api/routes/tools.py`、`backend/tests/test_tool_records.py` |
| 统计面板（使用汇总、近 14 天趋势、作物分布、历史记录） | 已实现并验证 | `frontend/src/components/StatsWorkspace.tsx`、`frontend/e2e/decision.spec.ts` |
| 使用帮助与关于软件 | 已实现并验证 | `frontend/src/App.tsx`、`backend/app/services/system.py` |
| 数据库迁移、备份恢复与发布演练 | 已实现并验证 | `backend/app/core/database.py`、`backend/app/core/backup.py`、`scripts/release_rehearsal.py` |
| 智能问答、会话与消息、流式输出 | 已移除 | 路由、服务、数据库表和前端模块已删除（Schema 6） |
| 田间诊断（图片识别） | 已移除 | `/api/vision`、图片校验工具和前端模块已删除（Schema 6） |
| 系统模型接入（Key、Endpoint、演示模式） | 已移除 | `services/assistant.py`、模型配置项和 `openai` 依赖已删除 |
| 用户手动接入模型 API Key | 已废弃 | 代码、路由、数据库表和前端入口已移除 |
| PostgreSQL、Redis、Docker、公网 SaaS、计费、多租户 | 未实现 | 不在本轮范围 |

## 数据与风险

- 迁移版本从 Schema 1 前进到 Schema 6：Schema 3 移除旧凭据表和会话关联列，Schema 4 增加会话置顶字段，Schema 5 新增 `tool_records` 表保存农活建议历史，Schema 6 删除 `chat_sessions`、`chat_messages`、`idempotency_requests` 并移除 `users.preferred_model`。
- **Schema 6 迁移会丢弃既有会话与消息数据。**升级前必须用 `scripts/database_admin.py backup` 生成备份；升级后旧代码无法打开该数据库（`migrate_schema` 会拒绝过高的 `user_version`）。
- 审计不输出任何密钥内容。
- SQLite 适用于单机部署；公网和多实例能力不在 V1.0。

## 唯一下一方向

AI 能力移除已完成迁移、测试与回归。继续扩展业务功能需新的需求与安全评审；`docs/software-copyright/final-delivery/` 中的 V1.0 归档仍记录移除前的能力，对外申报前需重新生成。
