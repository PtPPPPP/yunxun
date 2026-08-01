# 项目状态

审计日期：2026-08-01。事实来源为当前源码、Git、配置、测试和脚本；历史计划只作为背景。

## 当前结论

当前项目属于**工程化 MVP**。代码、SQLite 运维和单机发布演练已经通过，但软著 DOCX 尚未完成逐页视觉验收，因此本轮不提升为“单机生产可用版”。它不是公网 Beta 或商业 SaaS。

## Git 基线

- 分支：`main`
- HEAD：`b952778`，标签 `v1.0.0`
- 远端：与 `origin/main` 分叉 `0/0`
- 本轮开始时：28 个已跟踪文件有修改，14 个未跟踪文件；无删除文件，`git diff --check` 通过。
- 这些未提交内容属于用户现有工作区，本轮保留并在其上追加整理，不回滚、不自动提交。

## 功能状态矩阵

状态定义：已实现并验证、已实现未验证、部分实现、实验性、仅规划、已废弃、未实现。

### 核心业务

| 能力 | 状态 | 依据 |
| --- | --- | --- |
| 注册、登录、访客登录、退出 | 已实现并验证 | `routes/auth.py`、`services/auth.py`、认证测试与 E2E |
| 会话创建、列表、重命名、删除 | 已实现并验证 | 聊天路由、service、repository、后端测试与 E2E |
| 消息发送与演示回复 | 已实现并验证 | 聊天 service、幂等测试、失败恢复 E2E |
| 系统豆包/Ark真实 AI 回复 | 已实现未验证 | `services/assistant.py`；本轮未调用真实付费模型 |
| 乐观消息与失败恢复 | 已实现并验证 | `useChatController.ts`、状态测试与 E2E |
| 会话分页、消息游标分页、长会话滚动 | 已实现并验证 | pagination、chat service、前端控制器与 E2E |
| 图片初步诊断 | 已实现并验证 | tools/assistant、上传校验和故障测试；真实视觉模型未调用 |
| 今日农活建议 | 已实现并验证 | decision service 与单元测试 |
| 用户资料设置 | 已实现并验证 | profile 路由、前端页面和测试流程 |
| 用户模型设置 | 实验性 | 当前 BYOK 页面、API、Schema 2、单元与 E2E；默认关闭且不属于 V1.0 |

### 认证与安全

| 能力 | 状态 | 依据 |
| --- | --- | --- |
| 密码哈希 | 已实现并验证 | PBKDF2-HMAC-SHA256 与认证测试 |
| Token 生成、摘要存储、过期、撤销 | 已实现并验证 | security/auth/repository 与认证、迁移测试 |
| Bearer 认证与 localStorage Token | 已实现并验证 | `deps.py`、`tokenStorage.ts`、API/E2E |
| Cookie 认证与 CSRF | 已实现并验证 | 当前未提交 auth/csrf/API 代码与 E2E；V1.0 标签不包含 |
| CORS | 已实现并验证 | FastAPI 中间件与配置测试 |
| 安全响应头、请求体限制、输入长度 | 已实现并验证 | 主中间件、schemas/upload 与测试 |
| 限流 | 已实现并验证 | 进程内 limiter 与单元测试；不支持多实例共享 |
| 日志脱敏与 request ID | 已实现并验证 | audit/request_context 与测试 |
| JSON 日志 | 未实现 | 当前为文本 `key=value` 日志 |

### 模型调用

| 能力 | 状态 | 依据 |
| --- | --- | --- |
| 系统默认 API Key、演示模型 | 已实现并验证 | config/assistant/runtime status 与故障测试 |
| OpenAI、DeepSeek、OpenAI-compatible BYOK | 实验性 | 当前 Provider 代码和 Mock 测试；无真实 Provider 证据 |
| 用户 API Key 加密保存 | 实验性 | AES-GCM、HMAC 指纹、Schema 2 与安全测试 |
| 任意 Base URL | 未实现 | 只允许系统预设或管理员白名单，这是安全边界 |
| Provider Adapter | 部分实现 | 存在兼容调用模块，尚无稳定公开适配器接口和真实兼容矩阵 |
| 模型超时、响应限制、错误分类 | 已实现并验证 | assistant/byok provider 与故障测试 |
| Token 和成本统计 | 未实现 | 无用量持久化或计费统计 |

### 数据库

| 能力 | 状态 | 依据 |
| --- | --- | --- |
| SQLite、WAL、事务、索引 | 已实现并验证 | database/repository 与并发测试 |
| PRAGMA user_version 与顺序迁移 | 已实现并验证 | 标签 Schema 1；当前工作区 Schema 2；迁移测试 |
| 幂等持久化与消息事务 | 已实现并验证 | idempotency/chat 与故障测试 |
| 备份、验证、恢复演练 | 已实现并验证 | backup 模块、脚本与测试；本轮再次演练 |
| PostgreSQL、Alembic、Redis | 未实现 | 源码和依赖均无正式实现 |
| SQLite 到 PostgreSQL 工具 | 未实现 | 无迁移脚本 |

### 部署与运维

| 能力 | 状态 | 依据 |
| --- | --- | --- |
| Windows 原生启动与 PowerShell | 已实现并验证 | 后端入口和 scripts |
| liveness、readiness | 已实现并验证 | system service/routes 与测试 |
| CI 与 Release Workflow | 已实现未验证 | `.github/workflows/` 存在；本轮只验证本地等价命令 |
| 发布包、发布演练、负载测试 | 已实现并验证 | 发布包 138 个条目且无禁入文件；完整发布演练与 120 请求负载测试通过 |
| 备份计划任务 | 已实现未验证 | `backup_task.ps1`；不自动注册系统任务 |
| Docker、Compose、Nginx、HTTPS | 未实现 | 无对应正式配置 |
| metrics | 未实现 | 无指标端点或采集器 |

### 权限与商业能力

| 能力 | 状态 | 依据 |
| --- | --- | --- |
| 普通用户数据归属校验 | 已实现并验证 | 路由依赖、service 和测试 |
| 管理员、RBAC、用户禁用、审计后台 | 未实现 | 无角色模型和管理路由 |
| 多租户、套餐、计费、支付 | 仅规划 | 仅在路线图中出现 |

## V1.0 与当前工作区

- V1.0 正式范围只认 `v1.0.0` / `b952778`，数据库 Schema 为 1。
- 当前工作区增加 Cookie/CSRF 和默认关闭的 BYOK，数据库 Schema 为 2。
- BYOK 已通过本地 Mock、单元和无真实 Key 的 E2E，但未完成真实 OpenAI/DeepSeek 验证，因此归入 V1.2，不写入 V1.0 软著功能说明。

## 当前测试结果

- 后端：114 个通过，0 个失败。
- 前端：17 个通过，0 个失败。
- E2E：5 个通过，0 个失败。
- compileall、lint、build：通过。
- npm audit：0 个漏洞。
- pip-audit：0 个已知漏洞。
- 负载测试：120 个请求通过，0 个失败；平均 189.78ms，P95 345.64ms。
- 发布演练：1 次通过，0 次失败；覆盖干净安装、构建、启动、重启、持久化、备份恢复和停止。
- 数据库临时演练：初始化、Schema 2 检查、备份验证、恢复演练均通过，正式数据库未改动。
- 软著 DOCX：结构检查 2 份通过，0 份失败；自动逐页视觉验收未完成。

## 已知风险

- 当前工作区包含大量未提交增强，不能把 Git 标签和工作区状态混为同一发布版本。
- BYOK 未经过真实 Provider 验证，主密钥轮换也没有正式工具。
- SQLite、进程内限流和本地日志限制了多实例与公网运行。
- `.env` 和本地数据库存在但已忽略；必须继续按敏感数据处理。
- 软著申请中的首次发表日期和城市需要权利人最终人工确认。
- 当前机器没有 LibreOffice，Word 自动导出 PDF 持续无响应；软著 DOCX 仍需人工逐页检查版式。

## 下一步唯一方向

完成 V1.0 软著截图和材料人工确认。在此之前不推进 BYOK 正式化或公网 Beta。
