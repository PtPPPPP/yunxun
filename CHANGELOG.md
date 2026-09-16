# 更新日志

## 未发布

- 新增「采收产量与投入产出核算」：台账的采收记录可填产量（公斤）与单价（元/公斤），`GET /api/farm-records/economics` 按地块汇总投入、产量、收入、净收益与四项亩均指标；统计面板新增「累计投入 / 累计收入 / 净收益」三张卡和按地块的投入产出表。亩均用 Python 计算，面积异常时返回 null 而不是让查询报除零。
- 新增「用药安全间隔期」：打药记录填农药名称与安全间隔期天数后，由施药日推导最早安全采收日；安全期状态并入 `GET /api/plots`（每块地最近一次带间隔期的打药，用窗口函数取），记采收时若仍在安全期内给出提醒但不阻断提交。应用不内置标准答案，只提供常见参考值预填并标注以产品标签为准。
- 新增「农事待办」模块（Schema 8 的 `farm_tasks` 表）：地块可空，按已逾期/今天/本周内/更远分组，逾期标红，顶栏常驻计数；两个便捷入口可按需把今日农活建议或台账的续办建议转成待办，不自动塞清单。
- 修复发布演练里的管道死锁：脚本用 `stdout=PIPE` 启动后端却从不读该管道，日志写满几 KB 的缓冲后后端会阻塞在写日志上、后续请求全部超时。改为把后端输出写进 `dist/rehearsal-backend.log`（不再阻塞），并在演练失败时自动打印该日志最后 30 行。
- 认证限流改为可配置（`YUNXUN_AUTH_REQUESTS_PER_MINUTE` / `YUNXUN_AUTH_WINDOW_SECONDS`，默认仍是 20 次/60 秒）。原先写死的 20/60 让端到端测试互相影响。
- 新增「农事地块」模块（Schema 7 的 `plots` 表）：登记名称、面积（亩）、土壤类型、灌溉条件、当季作物、定植日期和备注；列表附带各自作业记录条数。地块是应用第一个业务主体，后续记录都挂靠它。
- 新增「农事台账」模块（Schema 7 的 `farm_records` 表）：按地块记录每次作业的类型（播种/施肥/打药/灌溉/除草/采收/其他）、日期、用量、可选费用和说明；台账按作业日期倒序游标分页，支持按地块筛选。
- 删除地块会连带删除它的全部台账记录，前端确认弹窗先说明将删除的条数；地块不存在与越权访问统一返回 404 加稳定 `code=NOT_FOUND`，不泄漏他人地块是否存在。
- 打通现有功能：今日农活新增地块选择器，选中后带入该地块的当季作物；统计面板新增「地块数」与「作业记录」两张卡。
- 新表刻意不使用 `CHECK` 约束限定作业类型，允许值集中在路由层常量集合校验——`tool_records.kind` 的 CHECK 曾导致新增取值只能整表重建。
- 地块与台账的新接口不做限流，只写审计日志；限流仍保留给计算密集的 `/api/decision` 和防爆破的 `/api/auth/*`。
- 顺带修掉 `styles.css` 两处引用未定义 `var(--shadow)` 的无效声明，并删除无人引用的 `--sidebar-surface`。
- 移除全部 AI 能力：删除「智能问答」（`/api/chat/*`、会话与消息服务、SSE 流式输出、幂等存储）和「田间诊断」（`/api/vision`、图片校验工具）两个模块，后端不再接入任何模型服务，`openai` 依赖已从 `requirements.txt` 移除。前端只保留「今日农活」与「统计面板」。
- 品牌改名：软著全称改为「云寻智慧农业工作台软件」，简称改为「云寻」，界面、页面标题、系统提示、发布脚本和测试同步更新。`docs/software-copyright/final-delivery/` 中的 V1.0 归档按历史快照保留，未被改写。
- 数据库 Schema 6：删除 `chat_sessions`、`chat_messages`、`idempotency_requests` 三张表，并移除 `users.preferred_model`。**该迁移会丢弃既有会话与消息数据**，升级前必须备份。
- 统计面板精简为只统计今日农活记录：去掉图片诊断卡片、类型筛选和 vision 徽章，新增覆盖作物与近 14 天记录数，`/api/tool-records/stats` 不再返回 `total_sessions` 与 `total_messages`。
- 用户画像只剩显示名称：`PATCH /api/me/profile` 与 `PATCH /api/auth/profile` 不再接受 `preferred_model`。
- 配置裁剪：移除 `DOUBAO_*`、`YUNXUN_AI_*`、`YUNXUN_MAX_MESSAGE_LENGTH`、`YUNXUN_UPLOAD_MAX_BYTES`、`YUNXUN_IDEMPOTENCY_WINDOW_SECONDS` 和 `YUNXUN_DEFAULT_PAGE_SIZE`/`YUNXUN_MAX_PAGE_SIZE`。
- 测试与门禁重写：E2E 改为 `frontend/e2e/decision.spec.ts`（访客登录、生成建议、统计面板、帮助与关于、移动端导航、无 API Key 入口），`scripts/release_rehearsal.py` 与 `scripts/http_load_test.py` 改为农活与统计流程，后者现在会对任何非 2xx 响应失败。
- 前端依赖升级：vitest `3.2.7` → `5.0.1`，修复 `@vitest/mocker` 的路径穿越公告；同时更新 `browserslist`、`nanoid`、`baseline-browser-mapping` 的传递依赖，`npm audit --audit-level=moderate` 归零（此前 CI 的 `Audit frontend dependencies` 步骤为红）。vitest 5 要求 Node ≥ 22.12，因此 CI 各工作流与 `docs/DEVELOPMENT.md` 的 Node 版本从 20 提升到 24，`frontend/package.json` 增加 `engines` 字段声明该下限。

## 1.0.0 - 2026-07-12

- 完成聊天乐观状态、失败恢复、会话竞态保护和长会话游标分页。
- 认证 Token 改为带服务端 Secret 的 HMAC-SHA256 摘要存储。
- 幂等状态持久化到 SQLite，支持租约、冲突、回放和过期清理。
- 建立 Schema 版本迁移、WAL、复合索引、并发与故障恢复测试。
- 增加真实 Chromium 桌面端、移动端、失败恢复和长会话滚动 E2E。
- 增加生产配置校验、CI、数据库备份恢复工具、发布检查和回滚流程。

已知限制：SQLite 仅适合单机小规模部署。
