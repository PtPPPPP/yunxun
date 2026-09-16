# V1.0 范围

正式基线为 `v1.0.0` / `b952778`，机器版本 `1.0.0`，文案版本 `V1.0.0`。当前工作区数据库为 Schema 9。

正式能力：注册登录、访客、地块与茬次档案、农事台账（含用量、费用、采收产量与单价）、农事待办、用药安全间隔期提醒、今日农活建议、按茬次的投入产出核算与使用统计、SQLite 持久化、Bearer 认证和基础安全控制。所有计算与建议由本机规则引擎完成，不访问任何外部服务。

已从 V1.0 基线移除：智能问答与会话消息、图片初步诊断、系统模型接入（Key、Endpoint、聊天与视觉模型、演示模式）以及 AI 品牌文案。移除同时删除 `chat_sessions`、`chat_messages`、`idempotency_requests` 表和 `users.preferred_model` 字段。

明确排除：任意 Provider/Base URL 接入、用户个人 API Key、PostgreSQL、Redis、Docker、公网 SaaS、计费、多租户和管理员后台。
