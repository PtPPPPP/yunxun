# 有限架构整理与 F1—F6 回归验收

日期：2026-10-19。对象为当前未发布工作区；版本仍为 1.0.0，Schema 12。已阅读 AGENTS.md、现有架构及审计记录，修改前检查 Git 状态并保留已有未提交成果。本轮按职责和业务不变量整理，不以文件行数作为验收指标。

当前职责见 [ARCHITECTURE](../../ARCHITECTURE.md)；[results.json](results.json) 保存验证时 HEAD、关键源码 SHA-256、测试数字与 E2E 文件分布。HEAD 之外仍有工作区修改，不能仅凭提交号重现这次验收。

## 已实现的整理

1. [useAuthSession](../../../frontend/src/hooks/useAuthSession.ts) 接管启动身份核对、登录/注册/访客、退出确认与重试、姓名保存、密码操作后的返回登录和访客升级会话接纳。继续使用原有 SessionBoundary 的轮次、useAsyncGuard 及 logoutIntent，不新增另一套会话状态。App 只组装界面并在明确的边界回调中清理业务草稿/视图。
2. [FarmRecordForm](../../../frontend/src/components/FarmRecordForm.tsx) 统一保存字段、日期归茬提示、类型字段清理、幂等提交标识、失败后输入、未保存保护、保存与后续待办提示。[LedgerWorkspace](../../../frontend/src/components/LedgerWorkspace.tsx) 管理列表、筛选、分页、导出及删除；普通台账与统计追溯嵌入同一表单，首页/地块快速记账与待办转记账直接使用表单，不创建列表状态或请求。
3. 列表只向表单发送进入编辑、当前记录已删除时复位这两个具体命令，不读取字段或组装写请求。两者共用原有写操作互斥；独立弹窗使用同种本地互斥。保留现有 DOM/CSS、控件、错误文案和焦点管理，列表与表单也复用会话轮次保护响应。
4. UTC 时间函数移入 [core/time.py](../../../backend/app/core/time.py)。回收站、认证、账号和引导模块直接引用核心工具；repositories 保留原时间函数导入入口兼容已有调用。回收站不再为时间工具反向导入 repositories。秒/微秒精度均未改变。
5. 未拆改事务、SQL 或查询口径。列表、统计、导出继续复用 `_farm_record_conditions`，前端 CSV 仍使用列表当前筛选。与修改前工作区快照比较，除迁走的时间函数外，repository 业务函数的 AST 完全一致。未增加通用 CRUD、仓储框架或重复筛选实现。

## F1—F6 的本轮修复证据

下表对应原审计问题；实现来自此前修复，本轮整理保留并通过完整回归重新验证。原审计的旧行号保留历史含义，当前入口以这里的路径为准。

| 项目 | 当前行为及实现入口 | 本轮执行的证据 |
| --- | --- | --- |
| F1：退出失败与刷新恢复 | useAuthSession 隐藏资料、保存不可认证的退出意图，明确待确认与重试；启动和网络恢复继续确认。请求撤销成功或核对 401 才清除标记。保留 HttpOnly Cookie，Token 不进浏览器持久存储。 | [session.spec.ts](../../../frontend/e2e/session.spec.ts)：请求未送达、撤销后响应丢失、退出和核对均失败、刷新/重新打开、online 重试、正常退出；[test_logout_sessions.py](../../../backend/tests/test_logout_sessions.py)：幂等撤销、Cookie/Bearer、CSRF、会话引用不能认证。 |
| F2：旧响应覆盖新会话 | [SessionBoundary](../../../frontend/src/hooks/useSessionBoundary.tsx) 在认证/退出/失效/升级时推进轮次；姓名保存捕获轮次检查成功与失败响应。服务端只撤销请求对应的会话，迟到退出响应不下发删除 Cookie 指令，旧重试不得撤销新会话。 | session.spec.ts 的 A→退出、A→B、A→退出→A 迟到成功/错误、旧退出/重试、延迟期间重复认证；test_logout_sessions.py 的同账号/异账号新会话、原请求迟到及无删 Cookie 指令断言。 |
| F3：建议与输入混合 | App 继续绑定生成轮次、输入快照、地块 ID/名称及结果；改条件即失效，迟到成功/错误不得复活。保存取同一快照且有互斥。界面和帮助明确条件由用户填写，只按降雨概率和湿度分支。 | [decision-consistency.spec.ts](../../../frontend/e2e/decision-consistency.spec.ts)：玉米/番茄切换、取消地块、生成中改条件/改回、请求迟到、失败、重复生成/保存、保存失败重试、标题/内容/地块归属及手机说明；[test_decision_service.py](../../../backend/tests/test_decision_service.py)：规则和 API 输入输出。 |
| F4：地块与第一茬部分落库 | `create_plot_with_first_season` 继续在同连接、同写事务内完成两次 INSERT，失败整体回滚。 | [test_farm_transactions.py](../../../backend/tests/test_farm_transactions.py)：首次/第二次 INSERT 触发器故障、重试、同连接及提交前不可见；[test_service_concurrency.py](../../../backend/tests/test_service_concurrency.py)：真实服务等待写锁后第二次 INSERT 故障，验证不残留半块地。 |
| F5：改期破坏历史归属及并发 | 普通茬次和兼容地块编辑在写锁内复用日期校验，包括回收站台账；冲突返回 409 和影响条数。台账新增/编辑在事务内最终复核或选茬，不改写历史日期/归属或删除资料。 | test_farm_transactions.py：起止/组合冲突、正常/回收站条数、仅回收站阻断、合法边界/空日期、兼容入口、事务故障，以及记录先提交/改期先提交的新增与编辑交错；[test_farm_regressions.py](../../../backend/tests/test_farm_regressions.py)、[farm.spec.ts](../../../frontend/e2e/farm.spec.ts)、[economics.spec.ts](../../../frontend/e2e/economics.spec.ts) 验证日期、历史归茬、编辑和统计追溯。 |
| F6：同步 SQLite/密码阻塞事件循环 | 同步业务仍为普通 def 路由，完整业务在线程池内执行；连接同线程创建/使用/提交或回滚/关闭。live 不访问数据库；现有限流锁和 ContextVar 保持。 | test_service_concurrency.py 的 6 条真实单 worker Uvicorn/TCP 回归：BEGIN 信号确认写请求开始等锁，锁未释放且写请求未完成时 live 先完成；失败回滚与线程归属、密码工作、同名注册 200/409、精确并发限流、日志/请求 ID/CSRF/权限。当前两版完整后端测试都重新执行了这些用例。 |

上述故障注入均作用于临时数据库/本机测试服务。F6 的旧异步阻塞写法反向验证来自此前 [F6 修复记录](../../audits/2026-10-19/F6-修复验证.md)，本轮未重复反向改写入口；不能把该历史探针算成此次新执行的测试。

## 本轮新增浏览器回归

[architecture-regression.spec.ts](../../../frontend/e2e/architecture-regression.spec.ts) 的 3 条流程在完整 E2E 中再次通过：

- 普通台账已落库但响应丢失，保留费用/日期；修改列表筛选后表单不重建，明确重试沿用同一 submission_id，最终只有一笔记录。
- 390px 独立记账表单不查询台账列表；嵌套放弃确认的取消保留输入并恢复输入焦点，确认离开恢复入口焦点和页面滚动，无横向溢出。
- 删除当前编辑记录期间，表单与筛选共同禁用；删除后退出编辑状态并清空未保存字段，恢复台账后仍为修改前费用。

既有 mobile-ledger、home、tasks、economics、exports、guest-upgrade、password、trash 和 current-acceptance 浏览器流程均执行，没有为了拆分组件删除或放宽旧断言。普通/快速/待办/统计追溯共用表单的日期归茬、幂等、失败输入、未保存导航和手机布局由这组既有流程与新增用例共同验证。

## 实际执行结果

平台：Windows x64；使用此前按 constraints 创建的隔离环境，CPython 3.11.17 / 3.14.8；Node 24.19.0、npm 12.2.0，Chromium。数据库全部为测试临时库，E2E 的后端仅安装运行依赖。本轮没有重新联网安装依赖。

| 命令/检查 | 实际结果 |
| --- | --- |
| `python -m unittest`，3.11.17 | 309/309，87.879 秒 |
| `python -m unittest`，3.14.8 | 309/309，91.563 秒 |
| `npm run test` | 15/15，通过 |
| `npm run lint` | 通过 |
| `npm run build` | 两套 TypeScript 检查和 Vite 构建通过 |
| `npm run test:e2e -- architecture-regression.spec.ts` | 3/3，9.6 秒 |
| `npm run test:e2e`，后端 3.11.17 | 125/125，3.0 分钟，无失败重试；已包含新增 3 条 |
| `python -m compileall -q backend scripts`，两版 | 通过 |
| 独立导入回收站、时间工具与旧入口函数身份核对 | 通过，导入回收站不会加载 repositories |
| repository 业务函数与整理前快照 AST 比较 | 一致，包括共享查询条件 |
| `git diff --check` | 通过；已有 LF/CRLF 提示不影响退出码 |

首次构建命令误在仓库根目录执行，因该目录没有 package.json 而退出；纠正为 frontend 后构建通过。没有降低检查要求、隐藏测试错误或扩大权限。

## 未验证事项与交付边界

- Ubuntu/GitHub Actions 本轮未执行；3.14 的浏览器 E2E 本轮未重跑，125 条 E2E 使用的是 3.11 后端。
- 只验证 Chromium 桌面及手机视口，没有真实 iOS/Android 设备、软键盘、跨机网络、真实多设备共享浏览器或生产 HTTPS/反向代理验收。
- 并发用例为同步信号控制的功能回归，不是容量、长期负载、多 worker 或多实例测试；SQLite 写串行和有限线程池的边界不变。
- 本轮未重跑依赖扫描、全新依赖安装或完整发布演练，也未生成新发布包。前一轮[依赖与配置验证](../../audits/2026-10-19/依赖与配置清理验证.md)只对应其当时源码；dist/release 中较早的候选包不能当作本次架构整理的交付包。
- 未部署、提交、推送或改动真实业务数据库；未验证生产备份计划/灾难恢复、农艺有效性或真实农户可用性。帮助和产品边界继续以实际规则及用户填写条件为准。
