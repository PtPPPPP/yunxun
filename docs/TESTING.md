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

- 后端：认证与 Token 摘要、今日农活规则、地块增删改与越权隔离、台账增删改与游标分页、删除地块的连带删除、农活建议落库与统计接口、Schema 迁移（含 v5→v6 删除 AI 表、v6→v7 新增地块与台账表）、备份恢复、配置解析、限流、错误载荷和 SQLite 并发写入。
- 前端：接口错误映射、版本号格式化，以及 17 条端到端流程——`e2e/decision.spec.ts` 覆盖访客登录、生成今日农活建议、统计面板记录与趋势、帮助与关于软件、移动端导航和不提供个人 API Key 入口；`e2e/farm.spec.ts` 覆盖地块新建与编辑、删除确认、台账记录与回看、按地块筛选、记录同步到地块卡片与统计面板、删除地块的连带删除提示、以及今日农活选地块带出作物。

`http_load_test.py` 目前对 `/health/live`、`/api/tool-records`、`/api/decision` 和 `/api/tool-records/stats` 并发压测，任何非 2xx 响应都会让脚本以非零码退出。
