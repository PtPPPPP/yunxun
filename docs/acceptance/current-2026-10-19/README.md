# 当前工作区整体验收

核对日期：2026-10-19（Asia/Shanghai）。这是 Windows 本机、临时数据库和本机 Chromium 验收，**不是生产部署验收、正式发布或软著申请通过**。

## 验收对象与事实来源

- 默认全称：云寻智慧农业工作台软件；简称：云寻；后端默认/前端包/材料脚本版本仍为 1.0.0，页面 V1.0.0；Schema 12。本轮没有擅自升版、改名或修改申请主体/开发完成日期/首次发表日期/权属。
- HEAD：4b02573280d95f9c11908920b0f6be4b486d0cec，包含前面各项未提交产品改动，不是只验收该提交。本轮未创建提交、push、部署、发布或 PR。
- 旧文档所述 v1.0.0 标签在本机无法解析，不能当作本次可复现依据。当前源码哈希和依赖/测试入口见 [source-inventory.json](source-inventory.json)。需保留实际工作区内容，哈希本身不是源码备份。
- 环境：Windows、Python 3.14.8、Node 24.19.0、npm 12.2.0、pip-audit 2.10.1。具体后端分发包版本见 [results.json](results.json)。CI 配置的 Linux/Python 3.11 本轮未执行。
- 执行前读了最新 README/AGENTS、相关代码/文档与各任务完成结果并检查 Git。现有改动保留；没有使用现有业务数据库作为测试夹具。

## 本轮执行结果

| 检查 | 实际结果 | 说明 |
| --- | --- | --- |
| 后端 unittest 全量 | 277 通过，0 失败 | 最终一轮 77.586 秒；含新增连续迁移/回滚 2 项 |
| 后端与脚本 compileall | 通过 | 不修改业务数据库 |
| 前端 Vitest | 15 通过，3 个文件 | 无跳过 |
| ESLint | 通过 | 保持原规则，没有关闭检查 |
| 显式类型检查 | 应用与 Vite 两套均通过 | tsconfig.app.json、tsconfig.node.json |
| 生产构建 | 通过 | Vite 产物仅本机生成，没有部署 |
| Chromium E2E 全量 | 91 通过，0 失败 | 最终一轮 2.5 分钟；桌面及 390px，临时数据库 |
| 前端依赖审计 | 0 已知告警 | moderate 门禁；原始 [npm-audit.json](npm-audit.json) |
| 后端 requirements 解析审计 | 27 个包，0 告警，0 跳过 | [pip-requirements.json](pip-requirements.json) |
| 后端已安装测试环境审计 | 28 个包，0 告警，0 跳过 | [pip-installed.json](pip-installed.json)，与声明解析分别核对 |
| 生产配置校验（临时库） | 通过，Schema 12 | 临时随机测试密钥/Secure 配置，仅结构校验，不是 HTTPS/生产验收 |
| 源码统计脚本 | 通过 | 筛选口径 65 个源码文件、8859 有效行、估算 178 页；不是正式源码 DOCX 页数 |

另外核对 72 项源码/配置/测试哈希、29 条本地文档链接，全部匹配且无断链，git diff --check 通过；历史归档、原申请表、运维备份工具和前端锁文件未变。

初轮为已有 275 项后端全量通过，补齐迁移验收后重跑 277 项。新增浏览器用例编写过程中纠正了待办按钮、作物选择器及异步登录等待等测试定位；没有删除业务断言。首轮全量 E2E 90/91，唯一失败为旧关于文案整段匹配，改为逐项当前能力和版本断言后重跑。更新断言后最终全量 91/91 通过，以本表和 results.json 的完成结果为准。

## 数据库验收

`backend/tests/test_current_acceptance.py` 构建真实 Schema 9 布局，再写入两个历史用户、已有摘要会话、各自地块/茬次/台账/已完成待办/规则建议，随后执行 9→10→11→12。

- 按原列逐值对照全部七类表，保留 ID、归属、费用的 NULL/0、产量/单价、历史文本、时间与完成状态，不靠删除数据库或空库迁移声称保留。
- 原地块无作物列，作物保留在茬次；来源默认真实，历史 guest_ 前缀保持正式身份，恢复码默认 NULL，删除标记默认 NULL。重复启动无重迁移。
- foreign_key_check 为空、integrity_check 为 ok；单活跃茬次唯一索引保留。不同用户分页/汇总分离，越权编辑/恢复返回 404，历史普通账号升级访客接口返回 403。
- 删除台账、删除父地块、恢复父地块、再恢复独立台账，分别核对可见性、已完成待办和收支还原，其他用户不受影响。
- 第 12 步 ALTER 故障注入后，该步全部回滚，保持已提交的 Schema 11 和全部原值；重试升至 12，数据不丢。迁移按步骤提交，不误称整条升级在单个事务。
- 既有 test_trash、test_password_management、test_onboarding 和旧迁移测试同轮执行，覆盖单步迁移、竞争/恢复冲突、最终清理、事务失败、真实演示混合资料保护和更早历史行为。历史 Schema 6 移除 AI 会话等仍为受控删除，不能宣称这些内容自动保留。

## 用户流程和界面验收

`frontend/e2e/current-acceptance.spec.ts` 在 1280×900、390×900 通过用户界面执行：

注册空账号 → 建第一块 2 亩样例田和唯一第一茬 → 安排今日待办 → 首页完成并确认记账 → 修改费用和作业日期 → 结束 4–5 月旧茬 → 开始 10 月新茬 → 从该地块补录旧茬采收 → 核对单茬收支/缺失 → 点击收入追溯并返回 → 下载汇总及明细 CSV → 删除/恢复独立台账 → 删除/恢复地块完整关联 → 退出并以原凭据重登。

样例第一茬：已记录支出 80，完整采收 100 公斤×3=300 收入；另有 10 公斤且单价/费用未填，已知产量 110，已记录差额 220，费用未填/采收待补录各 1（同笔不可相加）。页面、追溯、CSV 和恢复后数值一致，3 条旧茬记录不落入新茬；最后核对所有业务对象及用户 ID 不变。数值是人工构造验收资料，不是真实经营成果。

状态用例在两个宽度检查：真实空数据、加载阻塞提示、403 权限提示、断网错误、失败保留输入、保存中禁用及成功反馈；保存前两次失败不落库，第三次明确重试只产生一笔，无页面横向溢出。这里的 403/断网由测试注入以验前端反馈，真实 CSRF/越权及会话撤销另由完整后端与既有 E2E 验证，不能混称实际攻击或生产故障。

其余套件同时覆盖访客原 ID 升级、冲突/重复/失败回滚、退出新凭据登录；改密原密码错误/双设备撤销、一次性恢复码换码/重复消费、限流、本机命令及归属保留；跨年作业年度、分页筛选/跨页 CSV、未归茬、演示清理、恢复与最终清理、未保存取消/刷新和草稿账号隔离。

## 本轮发现与修正

1. UI 注册后的退出仍停注册模式：现在退出回到登录模式并清空认证表单，由两条全链路的直接重登断言验证。
2. 旧账号已显示建议与迟到建议响应可残留到新账号：清理建议输入/结果/地块选择，响应按发起账号复核；桌面/手机分别检查新账号为空，再释放旧响应仍为空。此前地块/茬次/待办的账号范围保护保持。
3. 登录介绍只提建议、声称完全不联网，以及帮助/关于的历史功能描述不完整：改为实际记账/收支范围，说明登记提醒算术、缺失值/年度口径、演示、恢复和草稿边界。没有重新引入 AI 或外部服务。
4. 文档修正：PROJECT_STATUS 的硬删除、重复矛盾“未实现”、过期 Schema/固定测试数字；架构的浏览器必须同时发 Bearer 说法；部署排查误用 /api/health 的 schema_version。远端部署段只作历史排查，本轮未核验。

## 依赖审计与安装

安装和审计会访问软件仓库/公告服务；业务运行不因此接入外部服务。本轮三份审计 JSON 全部无告警，没有 ignore-vuln、关闭门禁或弱化规则。历史问题的实际路径由 npm ls 核对并保存在 [dependency-paths.json](dependency-paths.json)：

| 路径 | 实际版本 |
| --- | --- |
| 应用 → axios | 1.20.0 |
| eslint 10.6.0 → minimatch 10.2.5 → brace-expansion | 5.0.12 |
| vite 7.3.6 → postcss 8.5.25 → source-map-js | 1.2.2 |

Windows 干净重装先因已运行 Vite 占用 esbuild 失败，识别并停止本次启动的前端体验进程后重试。npm 12 又拒绝锁文件中镜像 tarball 作为远程来源，使用 `npm ci --replace-registry-host=always` 将下载映射到已配置的官方 registry，保持锁文件及 integrity，没有放开 allow-remote。npm 12 对 esbuild postinstall 给出阻止提示，原生平台依赖仍在，本轮类型、构建及浏览器实际执行通过；没有批准未知安装脚本或修改依赖版本。前端体验服务在检查结束后恢复。

requirements 仍有范围版本和未接入的 ORM/PostgreSQL/Redis 依赖，部署时解析可能变化，应重审；本轮无已知告警不是永久安全保证。测试中 Starlette/TestClient 对 httpx 的兼容弃用提示未屏蔽，当前不阻断测试，后续版本维护需关注。

## 文档与材料

更新 README、PROJECT_STATUS、V1_SCOPE、ARCHITECTURE、TESTING、SECURITY、DEPLOYMENT、DEVELOPMENT、RELEASE、CHANGELOG 和页面帮助。专门规则继续参考 ACCOUNT_RECOVERY、DATA_EXPORT、RECYCLE_BIN、MOBILE_LEDGER。

新的 [软著技术草稿目录](../../software-copyright/current-draft-2026-10-19/README.md) 包含功能说明、25 项正式截图计划和申请人待确认信息。计划不等于已采集；本轮 QA 截图在测试输出，不宣称已完成正式截图/说明书/源码 DOCX/申请表/ZIP。历史 final-delivery、原申请表与 superpowers 未覆盖，数据库备份工具职责和代码未改变。

## 未验证与交付判断

- 本轮不验生产部署、HTTPS/代理、真实运行密钥/权限、实际备份计划和灾难恢复、容量压测、Linux/Python 3.11 CI、真实 iOS/Android 软键盘。
- 无持久草稿、后台离线同步、推送、自动清理或历史硬删恢复。回收站只覆盖地块和台账；CSV 只是分析留档；已记录差额不是完整利润。单进程限流重启重置，SQLite 单机边界保持。
- 软件默认名称/版本有代码事实，正式申报采用何名称/版本仍由申请人确认；主体、开发完成日、首次发表日和权属本轮既未核实也未更改。旧标签本机缺失，当前工作区未冻结为发布快照。

**技术层面：验收通过后具备据当前工作区继续生成当前版软著技术材料草稿的基础。正式提交层面：名称/版本和申请信息确认、冻结源码、正式截图及说明书/源码一致性核对尚未完成，不能称已可直接提交最终软著包。**

## 复核命令

实际使用临时测试 Python 与独立审计工具环境执行，路径因机器而异；下列为对应命令：

```powershell
python -m compileall -q backend scripts
python -m unittest
# frontend
npm ci --replace-registry-host=always
npm run test
npm run lint
node node_modules/typescript/bin/tsc --noEmit -p tsconfig.app.json
node node_modules/typescript/bin/tsc --noEmit -p tsconfig.node.json
npm run build
npm audit --audit-level=moderate --json
npm ls axios brace-expansion source-map-js --all --json
npm run test:e2e
# root; audit tool environment
python -m pip_audit -r backend/requirements.txt --format json
python -m pip_audit --path <测试环境site-packages> --format json
git diff --check
```

`check_release.main()` 另在 TemporaryDirectory、独立测试配置和随机测试密钥中调用，不用普通默认库运行示例命令来冒充临时验收。
