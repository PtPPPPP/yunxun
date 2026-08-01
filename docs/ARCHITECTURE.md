# 当前架构

本文描述当前工作区的真实实现。正式 V1.0 边界另见 [V1_SCOPE.md](V1_SCOPE.md)。

## 前端

React、TypeScript 和 Vite 组成单页应用。`frontend/src/App.tsx` 负责顶层认证、功能切换和状态编排；聊天状态由 `features/chat/useChatController.ts` 管理，页面组件位于 `components/`。Axios 客户端统一处理 API 地址、Cookie、CSRF 和错误信息。

浏览器当前同时保留 Bearer Token 兼容路径和 Cookie 会话。BYOK 模型设置页面已存在，但默认由后端配置关闭。

## 后端

`backend/main.py` 是 Windows 启动入口，`backend/app/main.py` 创建 FastAPI 应用。路由分为认证、聊天、工具、系统状态和当前实验性模型配置；service 层处理业务，repository 层直接访问 SQLite。

## 数据库

当前工作区只支持 SQLite。启动时通过 `PRAGMA user_version` 顺序迁移，当前 Schema 为 2：

- Schema 1：用户、认证 Token、会话、消息和幂等请求。
- Schema 2：默认关闭的用户模型凭据和会话模型绑定。

连接启用外键、busy timeout 和 WAL。没有 PostgreSQL、Redis 或 Alembic。

## 认证与安全

密码使用 PBKDF2-HMAC-SHA256 加盐哈希。原始登录 Token 只返回客户端，数据库保存基于服务端 Secret 的 HMAC 摘要。当前工作区接受 HttpOnly Cookie 和 Bearer，两者同时存在且身份不一致时拒绝请求；Cookie 写操作要求双提交 CSRF Token。

中间件加入请求 ID、请求体限制、安全响应头和访问日志。CORS 来源、方法和请求头来自后端配置。

## 模型调用

正式 V1.0 使用系统豆包/Ark配置；未配置真实 Key 时使用演示回复。当前工作区额外实现 OpenAI、DeepSeek 和白名单 OpenAI-compatible BYOK，API Key 以 AES-GCM 密文保存，但功能默认关闭且未完成真实 Provider 验证，因此不属于 V1.0。

## 请求流程

```text
浏览器组件 → Axios/认证与CSRF → FastAPI中间件 → 路由鉴权
→ service业务与限流/幂等 → repository/SQLite 或模型Provider
→ 统一成功/错误载荷 → 前端状态更新
```

## 测试

- 后端：`backend/tests/`，使用 unittest 和临时 SQLite。
- 前端：Vitest 测试状态、API 和模型设置载荷。
- E2E：Playwright 启动临时后端、临时数据库和 Vite，不调用真实模型。
- CI：编译、测试、lint、build、依赖审计和发布候选打包。

## 部署

当前正式定位是 Windows 本机或局域网单机运行。仓库包含 PowerShell 启动、构建、备份和发布脚本，也包含 GitHub Pages 前端部署示例；没有完整公网后端、HTTPS 反向代理或容器部署方案。
