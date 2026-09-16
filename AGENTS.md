# AGENTS.md

本文件记录 `yunxun` 项目的默认协作规则，供 Codex 或其他自动化助手在本仓库内工作时参考。

## 1. 项目目标

`yunxun` 是一个前后端分离项目，当前优先目标是：

- 保证项目稳定可运行
- 保证后端 FastAPI 服务可启动
- 保证前端 React/Vite 页面可开发和构建
- 保持现有 FastAPI + React/Vite 架构
- 小步修改、明确验证、避免无关重构
- 在不破坏现有接口的前提下逐步提升工程质量

除非用户明确要求，不要为了“看起来更规范”而大规模重写业务逻辑或整体目录结构。本仓库已经过用户明确要求做过一次例外改动：移除全部 AI 能力（智能问答、田间诊断、模型接入和 AI 品牌文案，数据库前进到 Schema 6）。那是一次受控删除，不构成后续继续大范围重构的先例。

## 2. 当前范围

保留并维护的能力：认证（注册/登录/访客/退出）、地块档案、农事台账、今日农活建议、统计面板、数据库迁移与备份、发布脚本与 CI 门禁。

业务主体是 `plots`（地块）与挂在它下面的 `farm_records`（农事台账），Schema 7 引入。新增业务功能应优先挂靠地块，不要另起一个与地块平行的孤立实体。

已移除且不应重新引入（除非用户明确要求）：任何外部模型服务接入、用户或服务端模型 API Key、会话与消息存储、图片诊断。`chat_sessions`、`chat_messages`、`idempotency_requests` 表和 `users.preferred_model` 字段已在 Schema 6 删除。

新表不要使用 `CHECK` 约束限定取值集合（`tool_records.kind` 的 CHECK 曾导致新增取值只能整表重建），把允许值放在路由层的常量集合里校验。

`docs/software-copyright/final-delivery/` 是 V1.0 的历史快照，记录的是 AI 能力移除前的能力，不要据此推断当前实现，也不要在无关改动中改写它。`docs/superpowers/` 下的设计与计划稿同理，属于历史资料。

## 3. 项目入口

### 后端

- 后端启动入口：`backend/main.py`
- FastAPI app：`backend/app/main.py`
- 推荐启动命令：

```bash
python backend/main.py