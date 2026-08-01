# 云寻智慧农业AI工作台软件

云寻智慧农业AI工作台软件（简称“云寻AI”）是一套面向农业场景的本地/内网 AI 工作台。正式 V1.0 以 Git 标签 `v1.0.0`（Commit `b952778`）为准，适合课程、答辩、软著、作品集和小规模受控试用。

当前工作区还包含尚未提交的 Cookie/CSRF 与 BYOK 工程增强。它们会被保留和审计，但不改变 V1.0 的正式范围；其中 BYOK 默认关闭，不属于 V1.0。

## 当前版本

- 软件全称：云寻智慧农业AI工作台软件
- 软件简称：云寻AI
- 机器版本：`1.0.0`
- 文档版本：`V1.0.0`
- V1.0 基线：`v1.0.0` / `b952778`
- 当前定位：本地或内网单机运行，不是公网商业 SaaS

## V1.0 核心功能

- 用户注册、登录、访客登录和退出。
- 农技问答、会话创建、查看、重命名、删除和历史消息保存。
- 田间图片初步诊断和今日农活建议。
- 无真实模型 Key 时使用本地演示模式。
- SQLite 本地存储、Schema 迁移、会话分页、消息幂等和失败恢复。
- 健康检查、请求限流、上传校验、请求 ID、日志和数据库备份恢复。

完整边界见 [V1.0 范围](docs/V1_SCOPE.md)，当前开发状态见 [项目状态](docs/PROJECT_STATUS.md)。

## 技术栈

| 层 | 技术 |
| --- | --- |
| 前端 | React、TypeScript、Vite、Axios |
| 后端 | Python、FastAPI、Uvicorn、HTTPX |
| 数据库 | SQLite |
| 系统模型 | 豆包/Ark OpenAI-compatible API；未配置时进入演示模式 |
| 测试 | unittest、Vitest、ESLint、Playwright、GitHub Actions |

## 快速启动

环境要求：Windows 10/11、Python 3.10+、Node.js `^20.19.0 || >=22.12.0`。

```powershell
Copy-Item .env.example .env
Copy-Item frontend\.env.example frontend\.env

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
python backend\main.py
```

新开一个 PowerShell 窗口：

```powershell
Set-Location frontend
npm install
npm run dev
```

浏览器访问 <http://127.0.0.1:5173>。配置和局域网说明见 [开发说明](docs/DEVELOPMENT.md) 与 [部署说明](docs/DEPLOYMENT.md)。

## 测试入口

日常快速检查：

```powershell
python -m compileall backend
python -m unittest
Set-Location frontend
npm run test
npm run lint
npm run build
```

完整验证还包括 E2E、依赖审计、备份恢复、负载测试和发布演练，见 [测试说明](docs/TESTING.md)。测试不会默认调用真实付费模型。

## 项目结构

```text
backend/                    FastAPI 应用、SQLite 数据层和后端测试
frontend/                   React/Vite 前端、Vitest 与 Playwright E2E
scripts/                    开发、测试、数据库、发布和演练脚本
docs/                       当前权威文档、历史设计记录和软著材料
.github/workflows/          CI、前端部署和发布候选工作流
graphify-out/               最终知识图、报告和保留的历史分析
```

脚本未强制搬迁，避免破坏现有调用；分类见 [scripts/README.md](scripts/README.md)。

## 当前限制

- V1.0 不包含 PostgreSQL、Redis、Docker、HTTPS 反向代理、多实例、多租户、套餐、计费、支付、RBAC 或完整管理员后台。
- V1.0 不包含用户自带 API Key；当前 BYOK 代码属于默认关闭、尚未完成真实 Provider 验证的后续能力。
- SQLite 仅适合单机和小规模受控使用，不能由多个后端实例共享。
- 演示模式不会真实分析图片，也不能替代专业农技判断。
- 未额外加固前，不应直接作为公网商业 SaaS 上线。

## 文档索引

- [项目状态](docs/PROJECT_STATUS.md)
- [V1.0 范围](docs/V1_SCOPE.md)
- [当前架构](docs/ARCHITECTURE.md)
- [开发说明](docs/DEVELOPMENT.md)
- [测试说明](docs/TESTING.md)
- [部署说明](docs/DEPLOYMENT.md)
- [发布与回滚](docs/RELEASE.md)
- [安全边界](docs/SECURITY.md)
- [路线图](docs/ROADMAP.md)
- [待人工清理候选](docs/cleanup-candidates.md)
- [软著材料](docs/software-copyright/)
