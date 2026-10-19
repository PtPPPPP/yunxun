# 云寻智慧农业工作台软件

云寻是面向田块管理的农业工作台：登记地块档案并按**茬次**记录每季作物，按地块记录每次农事作业（含用量、费用、采收产量与单价），用待办排好接下来的活，并结合作物、生长期、降雨概率和土壤墒情生成当天可执行的建议。打药记录会按安全间隔期给出最早采收日，统计面板按茬次算出投入产出，便于跨年对比。全部计算在本地规则引擎完成，不依赖任何外部服务。

## V1.0

正式基线：`v1.0.0` / `b952778`。机器版本 `1.0.0`，文案版本 `V1.0.0`。

> 该基线包含智能问答与图片诊断能力，已封存在 `docs/software-copyright/final-delivery/`。当前工作区按要求移除了这两项能力、全部模型接入和 AI 品牌文案，因此那份归档只是历史快照，与当前代码不一致；对外申报前需重新生成材料。

## 快速启动

```powershell
Copy-Item .env.example .env
python backend/main.py
Set-Location frontend
npm install
npm run dev
```

## 测试

```powershell
python -m unittest
Set-Location frontend
npm run test
npm run lint
npm run build
npm run test:e2e
```

## 目录

`backend/` 后端，`frontend/` 前端，`scripts/` 运维与发布脚本，`docs/` 工程文档和软著材料。

## 限制与文档

台账归茬按作业日期匹配，只有起始日已知且唯一命中的茬次才自动归属；日期重叠、日期未知或季间空档保留为「未归茬」，也可在台账选择历史茬次。API `POST /api/farm-records` 的 `season_id` 省略时自动匹配，传具体 ID 时校验本人地块与日期范围，显式传 `null` 时保留未归茬。已有记录不会自动重新归茬。

采收提醒按同一地块全部茬次和作物的已登记施药记录，取「施药日 + 用户填写间隔天数」最晚的一天；查询日之后的施药记录不参与。换茬不会解除未结束的提醒。间隔期须按具体产品标签手工填写，软件仅核对输入的日期算术，不确认实际用药或采收合规性。

当前是 SQLite 单机版本，不包含 PostgreSQL、Redis、Docker、公网 SaaS、计费或多租户。详见 `docs/V1_SCOPE.md`、`docs/ARCHITECTURE.md`、`docs/SECURITY.md`、`docs/TESTING.md`、`docs/DEPLOYMENT.md` 和 `docs/RELEASE.md`。
