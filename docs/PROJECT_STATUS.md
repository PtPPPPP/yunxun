# 当前工作区状态

核对日期：2026-10-19。对象是未发布工作区，不是生产部署验收。代码默认全称「云寻智慧农业工作台软件」、简称「云寻」，后端默认值、前端 package 和材料脚本仍使用 `1.0.0` / `V1.0.0`。本次不更改名称或版本。工作树包含未提交改动；最新验收时的 HEAD 与关键文件 SHA-256 见 [results.json](acceptance/architecture-2026-10-19/results.json)，不能仅用 HEAD 复现当前成果。

`v1.0.0` / `b952778` 为历史基线，依赖清理时已从配置远端取回真实标签完成打包演练。最新职责整理、F1—F6 修复证据与验证边界见 [架构整理验收记录](acceptance/architecture-2026-10-19/README.md)；此前[整体验收记录](acceptance/current-2026-10-19/README.md)保留原轮次结果。

## 已实现与验证依据

下列能力已实现，具体本轮测试数字、失败修正记录、审计与验证边界统一记录在整体验收记录，不沿用历史测试总数。

| 能力 | 实现与验证依据 | 实际边界 |
| --- | --- | --- |
| 注册、登录、访客、退出、用户隔离 | auth 路由、test_auth_tokens、test_guest_upgrade | 无短信、邮箱、角色管理和外部登录 |
| 访客原 ID 保存正式账号 | repositories_account、guest-upgrade.spec.ts | 仅服务端 is_guest；历史前缀账号不猜测转换，旧会话撤销 |
| 改密、一次性恢复码、本机辅助恢复 | test_password_management、password.spec.ts | 恢复码本人离线保管，仅展示一次；两种凭据丢失需部署者核验；改密/重置撤销全部会话 |
| 首次引导与可选演示 | test_onboarding、onboarding.spec.ts | 真实数据判断进度；地块创建复用第一茬；演示与真实数据区分并保护真实关联 |
| 默认首页、真实待办和快速记账 | home.spec.ts、mobile-ledger.spec.ts | 完成待办不自动创建台账；取消/失败不改变已完成状态 |
| 地块、历史茬次、日期与单活跃约束 | test_seasons、test_farm_regressions、farm.spec.ts | 作物属于茬次；真实日期；新建和重开冲突为 409 |
| 台账新增、编辑、历史补录和分页筛选 | test_ledger_editing、farm.spec.ts | 自动归茬必须日期唯一且起始日已知；歧义须选择或未归茬，显式选择须符合日期 |
| 类型字段清理、失败重试与防重复 | test_record_submission、mobile-ledger.spec.ts | 新增幂等字段可选，旧客户端不传仍可分别新增；同次已保存内容不能静默覆盖 |
| 390px 快速表单、未保存保护 | mobile-ledger.spec.ts、useUnsavedChanges | 草稿仅页面内存，无持久保存、后台离线队列和自动重试；真机另验 |
| 每茬已记录收支、完整度和追溯 | test_economics_trace、economics.spec.ts | 收入仅完整产量×单价；费用 NULL 与 0 区分；不含未知人工/地租；年度按作业日期 |
| CSV 汇总与全部筛选明细 | test_csv_exports、exports.spec.ts | UTF-8 BOM、缺失留空、文本公式防护；不是整库恢复备份 |
| 采收登记间隔期计算 | test_farm_regressions、test_ledger_editing | 同一地块相关登记记录取最晚日期，换茬不解除；只验证输入算术，不确认标签或合规 |
| 地块和台账回收站 | test_trash、trash.spec.ts | 保留至主动最终删除，无自动清理；单独删除台账单独恢复；冲突不覆盖 |
| 今日农活建议与建议历史 | test_decision_service、decision.spec.ts、current-acceptance.spec.ts | 现场条件由用户输入，本机规则计算，无实时天气服务或自动诊断 |
| Schema 迁移及运维备份恢复 | test_database_migrations、test_backup、test_current_acceptance | 当前 12；9→12 保留业务数据；Schema 6 删除已移除 AI 会话；不自动降级 |
| 桌面和手机完整业务链路 | current-acceptance.spec.ts | 临时 SQLite + 本机 Chromium；UI 403 与断网为注入，真实权限另由后端验证 |

## 未实现、未验证和限制

- 未实现：跨页面持久草稿、常用单位记忆、后台离线同步、待办推送、回收站自动到期清理、复杂历史版本恢复、农资库存、短信/邮件找回、独立管理员网页。
- 已移除且不提供：AI 问答、会话消息、图片诊断、模型服务和用户模型 API Key。当前农事演示不等于旧版模型演示模式。
- 未验证：真实手机及 iOS/Android 软键盘、浏览器强制杀进程保留、大容量回收站压力、生产部署、HTTPS/代理/备份计划实际配置、Linux/Python 3.11 CI 本轮执行。
- 限流保存在单进程内，重启会重置；SQLite 和当前配置面向单机，不是已验收的公网多实例 SaaS。
- 只为地块和台账提供回收站。单独删除待办是永久删除；茬次删除接口不提供回收站，有回收站台账关联时拒绝删除。
- 历史硬删除、最终删除或丢失数据库不能凭空恢复。运维整库备份单独负责灾难恢复。
- 后端运行/测试依赖已分开，并共用精确版本 constraints；确认闲置的 SQLAlchemy、Alembic、psycopg、redis 已移除。支持范围、配置兼容与实际验证见 [依赖维护记录](audits/2026-10-19/依赖与配置清理验证.md)；未据此扩展 PostgreSQL/Redis 能力。

## 当前版软著材料

新草稿在 [current-draft-2026-10-19](software-copyright/current-draft-2026-10-19/README.md)，包含当前功能说明、截图计划和确认事项。历史 final-delivery、原申请表和 docs/superpowers 不改写。

名称、申报版本以及是否沿用历史材料须申请人确认。申请主体、开发完成日期、首次发表日期、权属与签章信息本轮不作推定。技术验收通过后可准备新草稿，不等于已完成正式申报交付。
