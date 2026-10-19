# 测试说明

默认测试使用临时数据库，不访问网络，也不修改正式用户数据库。

```powershell
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

`pip-audit` 在隔离环境中可单独安装运行；缺少工具时必须在最终报告中如实标记。

## 覆盖范围

- 后端：认证与 Token 摘要、今日农活规则、地块增删改与越权隔离、茬次开始/结束/重开与唯一约束竞争的 409 拒绝、台账增删改与游标分页、按日期唯一归茬与显式历史归茬及隔离校验、删除地块的连带删除、采收投入产出按茬汇总及其除零边界、多次施药取最晚间隔期（跨茬次/作物、未归茬、未来记录与地块/用户隔离）、真实日历日期与闰年及茬次起止顺序、完整 create_app 下 Cookie/CSRF 拒绝的 403 JSON、请求 ID、安全头与请求日志，以及 Bearer 和正常 CSRF 写入、待办分组与完成重开、农活建议落库与统计接口、Schema 迁移（v5→v6 删 AI 表、v6→v7 新增地块与台账、v7→v8 补采收字段与待办表、v8→v9 把地块作物搬进茬次并删列）、备份恢复、配置解析、限流、错误载荷和 SQLite 并发写入。
- 前端：接口错误映射、版本号格式化，以及 30 条端到端流程——`e2e/decision.spec.ts` 覆盖访客登录、生成今日农活建议、统计面板记录与趋势、帮助与关于软件、移动端导航和不提供个人 API Key 入口；`e2e/farm.spec.ts` 覆盖地块新建与编辑、删除确认、台账记录与回看、按地块筛选、记录同步到地块卡片与统计面板、删除地块的连带删除提示、采收产量到投入产出、手工按标签填写间隔期的提醒、以及今日农活选地块带出作物、结束一茬后换茬带出新作物、投入产出按茬次分行、历史采收补录使用历史作物与历史茬次、日期不明时未归茬与显式选茬；`e2e/tasks.spec.ts` 覆盖待办新增与分组、逾期提示、完成与重开、删除确认，以及从今日建议和台账两处生成待办。

2026-10-19 依赖修复：直接依赖 axios 的最低版本提高到 1.20.0，传递依赖 brace-expansion 和 source-map-js 在原有兼容范围内分别锁定到 5.0.12、1.2.2，无需新增依赖或 overrides。修复依据见 [Axios 官方公告](https://github.com/axios/axios/security/advisories/GHSA-c29m-xwm3-cm6r)、[brace-expansion 官方公告](https://github.com/juliangruber/brace-expansion/security/advisories/GHSA-q2hr-2g5m-vwhr)及 [source-map-js 发行说明](https://github.com/7rulnik/source-map-js/releases/tag/v1.2.2)。更新后执行依赖重装与 `npm audit --audit-level=moderate`，结果为 0 告警。此结果仅对应当次锁文件与审计数据库。

`http_load_test.py` 目前对 `/health/live`、`/api/tool-records`、`/api/decision` 和 `/api/tool-records/stats` 并发压测，任何非 2xx 响应都会让脚本以非零码退出。
