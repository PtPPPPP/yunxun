# 开发说明

## 环境

- Windows 10/11，PowerShell 5+ 或 7+。
- Python 3.10+。
- Node.js `^20.19.0 || >=22.12.0`。

## 初始化

```powershell
Copy-Item .env.example .env
Copy-Item frontend\.env.example frontend\.env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
Set-Location frontend
npm install
```

## 启动

根目录启动后端：

```powershell
python backend\main.py
```

另开终端启动前端：

```powershell
Set-Location frontend
npm run dev
```

默认前端为 <http://127.0.0.1:5173>，后端为 <http://127.0.0.1:8001>。

## 配置权威来源

- 后端：根目录 `.env`，字段定义在 `backend/app/core/config.py`。
- 前端：`frontend/.env`，只使用 `VITE_YUNXUN_API_BASE_URL`。
- 测试：测试代码或 Playwright 配置显式传入临时数据库和测试 Secret。
- CI：`.github/workflows/`。

`YUNXUN_DATABASE_URL` 和 `YUNXUN_PORT` 是文档主入口。`YUNXUN_DB_PATH` 与 `PORT` 只作为历史或平台兼容变量，不应在本地模板中与主变量重复配置。

## 修改原则

- 保持 FastAPI + React/Vite 架构。
- 不在 V1.0 维护中加入 PostgreSQL、Redis、Docker、SaaS 或计费。
- 新能力只有在代码、测试、运行验证和文档一致后才能标记完成。
- 脚本用途见 `scripts/README.md`，不要未经引用检查移动脚本。
