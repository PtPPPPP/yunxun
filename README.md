# 云寻智慧农业工作台软件

云寻是面向田块管理的农业工作台：先登记地块档案，再按地块记录每次农事作业，并结合作物、生长期、降雨概率和土壤墒情生成当天可执行的浇水、追肥和巡田建议。全部计算在本地规则引擎完成，不依赖任何外部服务。

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

当前是 SQLite 单机版本，不包含 PostgreSQL、Redis、Docker、公网 SaaS、计费或多租户。详见 `docs/V1_SCOPE.md`、`docs/ARCHITECTURE.md`、`docs/SECURITY.md`、`docs/TESTING.md`、`docs/DEPLOYMENT.md` 和 `docs/RELEASE.md`。
