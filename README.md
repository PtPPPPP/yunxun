# 云寻智慧农业AI工作台软件

云寻 AI 是面向农业问答、田间诊断和每日农活安排的前后端分离工作台。

## V1.0

正式基线：`v1.0.0` / `b952778`。机器版本 `1.0.0`，文案版本 `V1.0.0`。系统模型由服务器环境变量配置；用户不能填写或保存个人模型 API Key。

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
```

## 目录

`backend/` 后端，`frontend/` 前端，`scripts/` 运维与发布脚本，`docs/` 工程文档和软著材料。

## 限制与文档

当前是 SQLite 单机版本，不包含 PostgreSQL、Redis、Docker、公网 SaaS、计费或多租户。详见 `docs/V1_SCOPE.md`、`docs/ARCHITECTURE.md`、`docs/SECURITY.md`、`docs/TESTING.md`、`docs/DEPLOYMENT.md` 和 `docs/RELEASE.md`。
