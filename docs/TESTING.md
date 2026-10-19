# 测试说明

最新职责整理与 F1—F6 回归见 [architecture-2026-10-19](acceptance/architecture-2026-10-19/README.md)。新增 `e2e/architecture-regression.spec.ts` 验证列表筛选不丢失保存失败后的表单/幂等标识、手机独立表单不查询列表且嵌套确认恢复焦点/滚动、删除当前编辑记录时共享互斥并复位表单且保留未提交前的数据。既有会话、建议、普通/快速/待办记账、统计追溯与导出用例继续完整执行。

本轮整体验收和实际数字见 [current-2026-10-19](acceptance/current-2026-10-19/README.md)。`test_current_acceptance.py` 从真正 Schema 9 结构和双用户业务数据验证 9→12 每个原有列、外键、唯一索引、来源默认值、历史身份、分页隔离、删除/关联恢复和收支还原，并注入第 12 步 DDL 失败验证回滚与重试。`current-acceptance.spec.ts` 在 1280px/390px 用 UI 完成注册、第一块地/第一茬、待办完成记账、编辑、结束/换茬、补录旧茬、缺失与零值核算、追溯、CSV、台账/地块恢复和退出重登；另覆盖加载、403、断网、保存状态，以及已显示/迟到的旧账号建议隔离；注册退出默认回登录的修复由完整链路重登断言验证。

手机记账：`e2e/mobile-ledger.spec.ts` 在 390×844 下验证首页首屏/地块入口、今天和历史日期的茬次切换、空值与零值、重复点击、已写入但响应丢失后的明确重试、编辑失败与类型切换、键盘保存、保存中锁定、取消/导航/刷新/退出保护、换账号无业务草稿及迟到旧地块响应隔离、单茬收支卡片和横向溢出。使用 Playwright 临时数据库。旧首页和台账测试补上放弃未保存的确认操作，引导测试展开选填说明，保留原有提醒、取消不写入、统计与费用断言。

访客升级：`backend/tests/test_guest_upgrade.py` 使用完整 `create_app` 和临时 SQLite，覆盖同一 ID 及全部业务行保留、退出重登、用户名规范化/冲突、无效或额外字段、匿名/正式/历史前缀身份拒绝、双认证身份冲突、CSRF 拒绝与换发、全部旧会话撤销、重复和并发升级、会话插入触发器故障后的完整回滚、升级后演示来源与清理。测试注入故障只作用于临时数据库。

`frontend/e2e/guest-upgrade.spec.ts` 覆盖访客建业务数据后保存账号、重复点击、退出再登录核对数据、冲突换名、取消及输入校验、服务失败重试、提交落库但响应丢失后的登录恢复、网络未恢复时保留凭据、正式账号清理演示资料、手机布局，以及会话已升级但页面身份滞后的核对处理。

首次使用：`backend/tests/test_onboarding.py` 覆盖真实进度、跳过/继续、既有账号与数据的 v9→v10 迁移、显式访客身份、重复及并发加载、加载失败回滚、跨用户隔离、演示来源不可伪造、清空后真实数据与关联祖先保留、重新加载使用新对象、收支来源与游标分页，以及清空与保存交错时的 409 拒绝。旧迁移测试补齐 v8 待办表夹具，并保持原有完整字段与迁移顺序断言。

`frontend/e2e/onboarding.spec.ts` 从注册后的真实空数据完成第一块地、第一茬与第一笔台账，确认没有额外创建茬次；另覆盖跳过/继续、删除数据后重新核对进度、缺茬直达补建、演示加载及来源标识、收支追溯、清空及真实关联保留、手机加载失败重试与重复点击。

首页与待办记账：`frontend/e2e/home.spec.ts` 覆盖默认入口、真实计数、空状态、完成后确认保存至统计、取消、杂事选地块、保存失败重试、重复点击、已落库但响应丢失后取消/刷新重试，以及手机导航、帮助、关于软件和登记提醒。原今日农活用例显式从首页切换模块，保留建议生成、历史统计等断言。

`backend/tests/test_record_submission.py` 使用临时 SQLite 数据库，覆盖同次提交重试、并发、不同内容冲突、用户隔离、日期校验失败后重试及旧调用兼容。`frontend/src/lib/taskLedger.test.ts` 覆盖实际完成日、历史茬次、歧义、跨地块、杂事和字段长度；不把计划日期、标题中的计划动作或缺失费用当作真实作业数据。

后端测试使用临时数据库，端到端测试只请求本机测试服务；二者不操作现有业务数据库。依赖安装和漏洞审计会访问软件仓库/公告服务，不属于无网络测试。

```powershell
python -m pip install -r backend/requirements-test.txt
python -m pip check
python -m compileall backend
python -m unittest
Set-Location frontend
npm run test
npm run lint
npm run build
npm run test:e2e
npm audit --audit-level=moderate
```

发布和数据库演练：

```powershell
python scripts\check_release.py
python scripts\http_load_test.py
python scripts\release_rehearsal.py
python scripts\database_admin.py backup --dir <临时目录> --keep 2
```

`pip-audit` 在独立工具环境安装，避免把审计器及其依赖装进运行/测试环境。分别扫描运行清单、测试清单与新环境中实际安装的分发包；命令和版本维护方式见 [依赖与配置维护](DEPENDENCIES.md)。缺少工具或数据库访问失败时必须如实标记，不能写成扫描通过。

## 覆盖范围

F6：`backend/tests/test_service_concurrency.py` 启动单 worker Uvicorn，通过真实 TCP/HTTP 和临时 SQLite 验证。独立连接持有写锁，以 SQLite trace 的 BEGIN IMMEDIATE 信号确认写请求已开始等锁；健康检查必须在锁仍持有、写请求仍未完成时成功，然后才释放锁。另覆盖等待后的第二次 INSERT 故障回滚、连接创建/执行/提交或回滚/关闭的线程归属、密码计算期间存活检查、两次用户名预检均通过后的并发注册冲突、并发认证的精确限流次数、业务日志与响应的 request_id 隔离、Cookie/CSRF/CORS 和跨用户对象权限。同步使用 Event/Barrier 和秒级超时，不靠 sleep 或毫秒耗时阈值判断正确性；不是容量压测。

F4/F5：`backend/tests/test_farm_transactions.py` 使用临时 SQLite，覆盖第一/第二次 INSERT 触发器故障的完整回滚、同一连接及提交前不可见、起止日期与组合冲突、正常/回收站条数、合法边界和空日期、无关茬次及用户隔离、兼容地块编辑同改同回滚、台账写入前的最终日期和自动归茬校验。使用两个独立线程/连接及事件屏障，验证台账新增/编辑和茬次/兼容地块改期两种提交顺序，不依赖 sleep 猜测竞争窗口。每种交错后检查日期/归属不变量、foreign_key_check 与 integrity_check。

F3 与今日农活表述：`frontend/e2e/decision-consistency.spec.ts` 覆盖切换地块、修改全部输入、取消地块选择、输入改回原值、生成中的变更与新旧响应乱序、迟到成功/失败、最新请求失败、重复生成和保存、保存失败重试、手工作物与地块带入值不同时的标题一致性、原 API 字段、帮助和手机布局。`backend/tests/test_decision_service.py` 检查原有湿/干阈值与边界、作物/生长期/气温不影响水分分支，以及明确用户输入且不再声称综合风险的输出文字。

F1/F2 会话回归：`backend/tests/test_logout_sessions.py` 覆盖幂等撤销、失效 Cookie/Bearer、原会话引用匹配、同账号与异账号重登的旧退出拒绝、迟到响应没有 Cookie 删除指令、CSRF、非凭据引用不能登录及旧 Bearer 调用兼容。`frontend/e2e/session.spec.ts` 覆盖请求未送达、撤销后响应丢失、核对也失败、刷新和重新打开的待确认状态、在线恢复、退出响应延迟、旧重试保护新会话，以及姓名保存成功/错误迟到时的 A→退出、A→B、A→退出→A；检查 HttpOnly 和无 Token 的浏览器存储。

- 后端：认证与 Token 摘要、今日农活规则、地块增删改与越权隔离、茬次开始/结束/重开与唯一约束竞争的 409 拒绝、台账增删改与游标分页、按日期唯一归茬与显式历史归茬及隔离校验、删除地块后的隐藏与关联恢复、采收投入产出按茬汇总及其除零边界、多次施药取最晚间隔期（跨茬次/作物、未归茬、未来记录与地块/用户隔离）、真实日历日期与闰年及茬次起止顺序、完整 create_app 下 Cookie/CSRF 拒绝的 403 JSON、请求 ID、安全头与请求日志，以及 Bearer 和正常 CSRF 写入、待办分组与完成重开、农活建议落库与统计接口、Schema 迁移（v5→v6 删 AI 表、v6→v7 新增地块与台账、v7→v8 补采收字段与待办表、v8→v9 把地块作物搬进茬次并删列）、备份恢复、配置解析、限流、错误载荷和 SQLite 并发写入。
- 前端：接口错误映射、版本号格式化，以及端到端流程（总数以当前验收记录为准）——`e2e/decision.spec.ts` 覆盖访客登录、生成今日农活建议、统计面板记录与趋势、帮助与关于软件、移动端导航和不提供个人 API Key 入口；`e2e/farm.spec.ts` 覆盖地块新建与编辑、删除确认、台账记录与回看、按地块筛选、记录同步到地块卡片与统计面板、删除地块的连带删除提示、采收产量到投入产出、手工按标签填写间隔期的提醒、以及今日农活选地块带出作物、结束一茬后换茬带出新作物、投入产出按茬次分行、历史采收补录使用历史作物与历史茬次、日期不明时要求明确选择、取消编辑与修改费用后的统计刷新、类型切换清除隐藏收入、跨地块/日期/茬次编辑后的计数刷新、日期/地块/类型组合筛选翻页与编辑后的重置、切换筛选时丢弃旧的加载更多响应；`e2e/tasks.spec.ts` 覆盖待办新增与分组、逾期提示、完成与重开、删除确认，以及从今日建议和台账两处生成待办。

`backend/tests/test_ledger_editing.py` 使用临时 SQLite 数据库验证：历史费用编辑后的核算、跨地块移动与计数、记录/地块/茬次越权和跨地块茬次拒绝、无效日期与闰年、显式茬次日期关系和边界、归茬歧义与显式未归茬、创建和编辑时清理不适用字段、历史非采收收入不参与统计、施药修改后的提醒、组合条件下同日记录的游标分页，以及记录/目标地块并发删除的 404/409 响应与原记录保留。

`backend/tests/test_economics_trace.py` 覆盖费用缺失与零值、产量/单价缺失与有效零收入、空茬次无虚假待补录计数、原有金额字段兼容性、汇总金额/数量与分页追溯逐项核对、历史及未归茬记录、跨年茬次在年度边界不漏算/不重复、作业日期范围与年度口径一致、地块/茬次权限与用户年度选项隔离、无效年份/明细类别及追溯补录后的重新核算。

`e2e/economics.spec.ts` 的 7 条浏览器流程覆盖历史茬次与年度筛选、缺失收入显示待补录而非零、从金额/缺失数量追溯到台账并直接补录、返回及切换功能后保留统计筛选、未归茬及零费用追溯、手机卡片完整字段与页面不横向溢出、接口失败不显示假零值、快速切换年份时忽略旧响应。

2026-10-19 依赖修复：直接依赖 axios 的最低版本提高到 1.20.0，传递依赖 brace-expansion 和 source-map-js 在原有兼容范围内分别锁定到 5.0.12、1.2.2，无需新增依赖或 overrides。修复依据见 [Axios 官方公告](https://github.com/axios/axios/security/advisories/GHSA-c29m-xwm3-cm6r)、[brace-expansion 官方公告](https://github.com/juliangruber/brace-expansion/security/advisories/GHSA-q2hr-2g5m-vwhr)及 [source-map-js 发行说明](https://github.com/7rulnik/source-map-js/releases/tag/v1.2.2)。更新后执行依赖重装与 `npm audit --audit-level=moderate`，结果为 0 告警。此结果仅对应当次锁文件与审计数据库。

`http_load_test.py` 目前对 `/health/live`、`/api/tool-records`、`/api/decision` 和 `/api/tool-records/stats` 并发压测，任何非 2xx 响应都会让脚本以非零码退出。

`backend/tests/test_password_management.py` 使用临时数据库覆盖正式用户改密、错误原密码、输入和越权拒绝、恢复码摘要/换码/单次消费、并发消费、账号与 IP 限流及过期、CSRF、Cookie/Bearer 全会话撤销、旧密码登录与改密竞争、事务故障回滚、日志不含凭据、Schema 10→11 数据保留，以及本机命令的交互限制、取消与失败回滚。`e2e/password.spec.ts` 覆盖改密及另一设备失效、恢复码单次展示/换码/恢复、取消与输入校验、重复点击、响应中断核对、移动端导航和帮助。实际运行结果以本次执行报告为准。

`backend/tests/test_csv_exports.py` 使用临时数据库覆盖 137 条跨页记录及多条件筛选、中文/逗号/引号/换行、适用字段与缺失/零值、ASCII/全角/前导空白及控制字符公式防护、负数值、历史跨年汇总与明细核对、未归茬和账目来源/完整度筛选、空结果、未登录/越权/跨地块茬次、异常历史关联、字段白名单、文件名与 CORS 下载头。`e2e/exports.spec.ts` 验证真实浏览器下载内容与文件名、导出中和重复点击、错误 Blob 反馈与重试、非 CSV 响应拒绝、空结果、历史单茬年度范围、手机及演示来源区分。

`backend/tests/test_trash.py` 使用临时库覆盖影响范围（包括完成待办）、陈旧确认版本、删除后的列表/统计/采收提醒/导出/年度/引导一致性、关联恢复及单独删除保留、跨用户/CSRF、重复与并发操作、旧快照写入拒绝、恢复茬次及日期冲突、事务回滚、最终清理、演示清理保护、Schema 11→12 数据保留、幂等提交不复活及旧删除周期确认拒绝。旧迁移与删除测试保留可见性断言并增加软删除保留/恢复验证。`e2e/trash.spec.ts` 验证真实页面删除/恢复/清理、影响数量与取消、统计还原、数量变化拒绝、失败重试及手机入口。

## 安装、类型检查和审计口径

停止占用该工作区 esbuild 的开发服务后执行 `npm ci`。本轮 Node 24.19.0 / npm 12.2.0 对锁文件镜像 tarball 默认拒绝远程获取，使用 `npm ci --replace-registry-host=always` 映射到配置的官方 registry，保留 lock integrity，不打开 allow-remote。npm 12 默认拦截了 esbuild postinstall；本轮原生可选包、类型检查、构建和 E2E 的实际结果作为是否可用的证据。未修改依赖版本和锁文件。

显式类型检查：在 frontend 执行 `node node_modules/typescript/bin/tsc --noEmit -p tsconfig.app.json` 及对应 `tsconfig.node.json`；生产构建还会重复这两项检查。后端审计检查清单在 constraints 下的解析和新环境已安装分发包，这两者不能互相替代。审计结果只代表当时数据库与版本，不是永久安全保证。

本轮没有运行生产部署、真实手机、跨机 HTTPS、容量压力或发布包/灾难恢复演练。不要把 test_backup 的临时库测试写成生产备份验收。
