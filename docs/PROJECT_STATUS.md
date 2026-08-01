# 项目状态

审计基线：Git `v1.0.0` / `b952778`，机器版本 `1.0.0`，文案版本 `V1.0.0`。

当前工作区正在执行 BYOK 用户功能移除。系统管理员配置的服务端模型、演示模式、认证、会话、消息、审计、SQLite 数据库和现有前后端接口继续保留。用户不能填写、保存、测试或选择个人模型 API Key。

## 功能矩阵

| 能力 | 状态 | 依据 |
| --- | --- | --- |
| 注册、登录、访客、退出 | 已实现并验证 | `backend/app/api/routes/auth.py`、认证测试 |
| 会话、消息、历史与分页 | 已实现并验证 | `backend/app/services/chat.py`、`repositories.py`、前端测试 |
| 会话搜索、置顶、复制、导出、清空与重新生成 | 已实现并验证 | `frontend/src/components/Sidebar.tsx`、`ChatWorkspace.tsx`、`backend/app/api/routes/chat.py`、`backend/tests/test_chat_features.py` |
| 使用帮助与关于软件 | 已实现并验证 | `frontend/src/App.tsx`、`backend/app/services/system.py` |
| 系统模型聊天、超时、重试和错误处理 | 已实现并验证 | `backend/app/services/assistant.py`、聊天测试 |
| 图片初步诊断 | 已实现并验证 | `backend/app/api/routes/tools.py`、视觉测试 |
| 今日农活建议 | 已实现并验证 | `backend/app/services/decision.py` |
| 系统模型环境配置 | 已实现并验证 | `backend/app/core/config.py`、系统测试 |
| 用户手动接入模型 API Key | 已废弃 | 代码、路由、数据库表和前端入口已移除 |
| PostgreSQL、Redis、Docker、公网 SaaS、计费、多租户 | 未实现 | 不在本轮范围 |

## 数据与风险

- 迁移版本从 Schema 2 经过 Schema 3 前进到 Schema 4，移除旧凭据表和会话关联列，并增加会话置顶字段，保留用户、会话、消息、Token、幂等和审计数据。
- 当前正式数据库中的旧凭据行数为 0；审计不输出任何密钥内容。
- SQLite 适用于单机部署；公网和多实例能力不在 V1.0。

## 唯一下一方向

完成本轮迁移、测试和交付审计后停止，不继续扩展业务功能。
