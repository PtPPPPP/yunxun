# 云寻智慧农业AI工作台软件

[![CI](https://github.com/PtPPPPP/yunxun/actions/workflows/ci.yml/badge.svg)](https://github.com/PtPPPPP/yunxun/actions/workflows/ci.yml)
[![FastAPI](https://img.shields.io/badge/backend-FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/frontend-React-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![Vite](https://img.shields.io/badge/build-Vite-646CFF?logo=vite&logoColor=white)](https://vitejs.dev/)
[![Python](https://img.shields.io/badge/python-3.10+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![SQLite](https://img.shields.io/badge/db-SQLite-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![Doubao Ark](https://img.shields.io/badge/AI-Doubao%20Ark-5b4cff)](https://www.volcengine.com/product/doubao)

> 云寻智慧农业AI工作台软件（简称“云寻AI”）是一款面向农业场景的本地 / 内网 AI 工作台，集成农技问答、田间图片初步诊断和今日农活建议，适合小团队快速试用和演示。

云寻智慧农业AI工作台软件定位为「本地 / 内网可试用的农业 AI 工作台」。它适合合作社、农场、农业服务队或基层农技人员在 Windows 电脑和局域网内小规模试用。未配置真实豆包 / Ark Key 时，系统会自动进入**本地演示模式**，无需外部 AI 服务也能跑通登录、会话、图片诊断和农活建议等核心流程。

## ✨ 核心特性

- 🌾 **农技问答**：按会话保存问题和回复，支持历史会话查看。
- 📷 **田间图片初步诊断**：上传作物图片并填写描述，返回初步观察和建议。
- 📅 **今日农活建议**：综合天气、地块情况和作物阶段，生成当天作业建议。
- 🔐 **开箱即用的登录体系**：用户注册、登录、访客登录、退出。
- 🛡️ **安全会话存储**：前端持有原始登录 token，数据库只保存不可直接复用的 token 哈希。
- 🧪 **本地演示模式**：无 Key 也能完整跑通前端流程，零成本预演。
- 🩺 **健康检查**：支持 `/api/health`、`/health/live`、`/health/ready`，便于本地调试和部署探活。
- ✅ **工程校验**：CI 覆盖后端编译、单元测试、前端 lint、构建、依赖审计和源码行数统计。

## 目录

- [适用场景](#适用场景)
- [功能清单](#功能清单)
- [技术架构](#技术架构)
- [目录结构](#目录结构)
- [环境要求](#环境要求)
- [快速开始](#快速开始)
- [Windows 本地启动（详细）](#windows-本地启动详细)
- [局域网访问](#局域网访问)
- [环境变量说明](#环境变量说明)
- [SQLite 数据库](#sqlite-数据库)
- [安全与会话](#安全与会话)
- [豆包 / Ark 配置](#豆包--ark-配置)
- [演示模式说明](#演示模式说明)
- [线上部署（GitHub Pages + Render）](#线上部署github-pages--render)
- [最小验证流程](#最小验证流程)
- [代码行统计](#代码行统计)
- [常见问题](#常见问题)
- [商用 MVP 边界](#商用-mvp-边界)
- [后续升级建议](#后续升级建议)

## 适用场景

- 合作社、农场、农业服务队在一台 Windows 电脑上本地试用。
- 同一局域网内多台电脑或手机访问后端电脑上的服务。
- 农技人员演示农技问答、图片初步诊断、今日农活建议等流程。
- 商务沟通或试点前期，用低成本方式验证使用流程和内容边界。

## 功能清单

- 用户注册、登录、访客登录和退出。
- 农技问答：按会话保存问题和回复，支持历史会话查看。
- 田间图片初步诊断：上传作物图片并填写描述，返回初步观察和建议。
- 今日农活建议：根据天气、地块情况和作物阶段生成当天作业建议。
- 健康检查：通过 `/api/health`、`/health/live`、`/health/ready` 查看服务状态、存活状态和就绪状态。
- 本地演示模式：未配置真实豆包 / Ark Key 时，仍可打开前端、登录、创建会话并查看固定演示回复。
- 图片上传校验：前后端同时检查图片大小、MIME 类型和 Base64 数据，减少无效请求。
- 依赖安全检查：前端依赖通过 `npm audit` 检查，CI 会阻止中高风险问题进入主分支。

## 技术架构

| 层 | 技术栈 | 说明 |
| --- | --- | --- |
| 后端 | Python + FastAPI | 本机访问 `http://127.0.0.1:8001`，接口文档位于 `/docs` |
| 前端 | React + Vite | 开发服务位于 `http://127.0.0.1:5173` |
| 数据库 | SQLite | 默认文件 `backend/yunxun.db`，首次启动自动初始化 |
| AI 服务 | 豆包 / Ark（OpenAI 兼容接口） | Key 为空或为占位值时自动进入本地演示模式 |

## 目录结构

```text
yunxun/
├── backend/
│   ├── app/
│   │   ├── api/                 # 路由与接口定义
│   │   ├── core/                # 配置、限流、安全、上传校验等核心模块
│   │   ├── services/            # 业务与 AI 服务
│   │   ├── main.py              # FastAPI 应用入口
│   │   ├── repositories.py      # 数据访问层
│   │   └── schemas.py           # 数据模型 / 校验
│   ├── tests/                   # 单元测试
│   ├── main.py                  # 后端启动入口
│   └── requirements.txt
├── frontend/
│   ├── src/                     # 前端源码
│   ├── .env.example
│   ├── package.json
│   └── vite.config.ts           # 构建配置（base: /yunxun/）
├── .github/workflows/
│   ├── ci.yml                   # 后端检查、单元测试、前端构建
│   └── deploy-frontend.yml      # GitHub Pages 自动部署工作流
├── docs/                        # 项目文档
├── scripts/                     # 工程辅助脚本
├── .env.example                 # 后端环境变量模板
├── AGENTS.md
└── README.md
```

## 环境要求

- **系统**：Windows 10/11。
- **终端**：PowerShell 5+ 或 PowerShell 7+。
- **Python**：3.10+。
- **Node.js**：`^20.19.0 || >=22.12.0` 及配套 npm（当前 Vite 版本不支持只安装 Node.js 18）。
- **可选**：真实豆包 / Ark API Key（不配置也能以演示模式运行）。

> 建议先进入项目目录。把下面的 `<your-yunxun-path>` 替换为实际项目路径（例如 `D:\Projects\yunxun`）：
>
> ```powershell
> $ProjectPath = "<your-yunxun-path>"
> Set-Location $ProjectPath
> ```

## 快速开始

最快在本机跑起来，只需四步（默认进入演示模式，无需 Key）：

```powershell
# 1. 准备环境变量
Copy-Item .env.example .env
Copy-Item frontend\.env.example frontend\.env

# 2. 安装并启动后端
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
python backend\main.py

# 3. 新开一个 PowerShell 窗口，安装并启动前端
Set-Location <your-yunxun-path>\frontend
npm install
npm run dev
```

4. 浏览器打开 **http://127.0.0.1:5173**，注册或访客登录即可体验。

如需启用真实 AI 能力，请参考 [豆包 / Ark 配置](#豆包--ark-配置)。

## Windows 本地启动（详细）

### 1. 复制环境变量模板

```powershell
Copy-Item .env.example .env
Copy-Item frontend\.env.example frontend\.env
```

### 2. 安装后端依赖

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r backend\requirements.txt
```

### 3. 启动后端

```powershell
python backend\main.py
```

后端本机默认地址：

- 健康检查：<http://127.0.0.1:8001/api/health>
- 接口文档：<http://127.0.0.1:8001/docs>

### 4. 安装并启动前端

新开一个 PowerShell 窗口：

```powershell
$ProjectPath = "<your-yunxun-path>"
Set-Location "$ProjectPath\frontend"
npm install
npm run dev
```

前端本机默认地址：<http://127.0.0.1:5173>

## 局域网访问

假设后端电脑的局域网 IP 是 `192.168.1.10`。

后端电脑根目录 `.env` 建议设置：

```env
YUNXUN_HOST=0.0.0.0
YUNXUN_PORT=8001
PORT=8001
YUNXUN_BACKEND_URL=http://192.168.1.10:8001
YUNXUN_ALLOWED_ORIGINS=http://192.168.1.10:5173,http://192.168.1.20:5173,http://localhost:5173,http://127.0.0.1:5173
```

前端 `frontend/.env` 设置：

```env
VITE_YUNXUN_API_BASE_URL=http://192.168.1.10:8001
```

**注意事项：**

- 后端监听地址保持 `YUNXUN_HOST=0.0.0.0`，才能接受局域网其他设备访问。
- `YUNXUN_ALLOWED_ORIGINS` 必须包含实际打开前端页面的地址，否则浏览器会被 CORS 拦截。
- Windows 防火墙需要允许后端端口 `8001` 和前端端口 `5173` 入站访问。
- 其他设备要和后端电脑在同一局域网内，并使用 `http://192.168.1.10:5173` 或对应前端地址访问。
- 如果后端电脑 IP 变化，需要同步修改 `.env` 和 `frontend/.env`，然后重启后端和前端。

可用 PowerShell 查看本机 IP：

```powershell
ipconfig
```

如需开放防火墙端口，请在**管理员 PowerShell** 中执行：

```powershell
New-NetFirewallRule -DisplayName "Yunxun Backend 8001" -Direction Inbound -Protocol TCP -LocalPort 8001 -Action Allow
New-NetFirewallRule -DisplayName "Yunxun Frontend 5173" -Direction Inbound -Protocol TCP -LocalPort 5173 -Action Allow
```

## 环境变量说明

### 后端 `.env`

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `YUNXUN_APP_NAME` | `云寻智慧农业AI工作台软件` | 正式软件名称。 |
| `YUNXUN_APP_VERSION` | `1.0.0` | 对外展示版本。 |
| `YUNXUN_ENV` | `development` | 运行环境；本地试用保持默认即可。 |
| `YUNXUN_DEBUG` | `false` | 是否开启调试模式。 |
| `YUNXUN_HOST` | `0.0.0.0` | 后端监听地址；本机和局域网试用都可保持默认。 |
| `YUNXUN_PORT` | `8001` | 后端服务端口。 |
| `PORT` | `8001` | 兼容平台端口变量，建议和 `YUNXUN_PORT` 保持一致。 |
| `YUNXUN_BACKEND_URL` | `http://127.0.0.1:8001` | 后端对外访问地址；局域网时改成后端电脑 IP。 |
| `YUNXUN_JWT_SECRET` | `change-me-in-production` | 当前项目使用数据库保存的 opaque token，不是 JWT；内网试用前建议改成长随机字符串。 |
| `YUNXUN_TOKEN_EXPIRE_HOURS` | `168` | 登录 token 有效小时数。 |
| `YUNXUN_DATABASE_URL` | `sqlite:///./backend/yunxun.db` | SQLite 数据库连接地址；仅在未设置 `YUNXUN_DB_PATH` 时用于推导实际数据库文件路径。 |
| `YUNXUN_DB_PATH` | `./backend/yunxun.db` | SQLite 文件路径兼容变量；如果设置了它，后端实际优先使用这个路径。 |
| `YUNXUN_ALLOWED_ORIGINS` | 本机 Vite 地址集合 | 允许访问后端的前端来源，局域网访问必须补充实际 IP 地址。 |
| `YUNXUN_CORS_METHODS` | `GET,POST,PATCH,DELETE,OPTIONS` | 允许的 CORS 方法。 |
| `YUNXUN_CORS_HEADERS` | `Authorization,Content-Type,X-Idempotency-Key` | 允许的 CORS 请求头。 |
| `YUNXUN_MAX_MESSAGE_LENGTH` | `3000` | 单条消息最大长度。 |
| `YUNXUN_REQUESTS_PER_MINUTE` | `20` | 简单请求频率限制。 |
| `YUNXUN_UPLOAD_MAX_BYTES` | `5242880` | 单张图片最大上传字节数。 |
| `YUNXUN_REQUEST_TIMEOUT_SECONDS` | `45` | 普通请求超时时间。 |
| `YUNXUN_AI_TIMEOUT_SECONDS` | `45` | AI 上游请求超时时间。 |
| `YUNXUN_AI_MAX_RETRIES` | `1` | AI 上游请求失败后的有限重试次数。 |
| `YUNXUN_LOG_LEVEL` | `INFO` | 后端日志等级。 |
| `YUNXUN_DEFAULT_PAGE_SIZE` | `20` | 默认分页大小。 |
| `YUNXUN_MAX_PAGE_SIZE` | `100` | 最大分页大小。 |
| `YUNXUN_IDEMPOTENCY_WINDOW_SECONDS` | `10` | 聊天请求的防重复窗口；设为 `0` 可关闭。 |
| `DOUBAO_API_KEY` | `your-doubao-api-key` | 豆包 / Ark API Key；为空或占位值时进入演示模式。 |
| `DOUBAO_BASE_URL` | `https://ark.cn-beijing.volces.com/api/v3` | 豆包 / Ark OpenAI 兼容 API 地址。 |
| `DOUBAO_CHAT_ENDPOINT` | `doubao-seed-1-6-250615` | 聊天模型 Endpoint。 |
| `DOUBAO_VISION_ENDPOINT` | `doubao-seed-1-6-250615` | 图片理解模型 Endpoint。 |
| `DOUBAO_AVAILABLE_MODELS` | `doubao-seed-1-6-250615` | 可展示或可用的模型列表。 |

### 前端 `frontend/.env`

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `VITE_YUNXUN_API_BASE_URL` | `http://127.0.0.1:8001` | 前端请求后端的基础地址；局域网时改成后端电脑 IP，例如 `http://192.168.1.10:8001`。 |

## SQLite 数据库

默认数据库文件是 `backend/yunxun.db`。首次启动后端时，系统会自动创建数据库文件和所需表结构。

当前模板同时设置了 `YUNXUN_DATABASE_URL` 和 `YUNXUN_DB_PATH`。后端实际访问数据库文件时，`YUNXUN_DB_PATH` 优先级更高；如果只修改 `YUNXUN_DATABASE_URL` 而保留旧的 `YUNXUN_DB_PATH`，数据库位置不会改变。移动数据库时请同步修改两项，或删除 `YUNXUN_DB_PATH` 让 `YUNXUN_DATABASE_URL` 生效。

> ⚠️ 不要把真实 `.db` 文件提交到 Git。数据库里会包含用户、会话和消息等本地试用数据。

SQLite 文件操作建议**离线执行**：备份、恢复、删除和重新初始化前，都先停止后端服务，避免复制到正在写入的数据库文件。

**备份数据库：**

```powershell
# 先停止后端服务，再执行备份。
New-Item -ItemType Directory -Force backups
Copy-Item backend\yunxun.db backups\yunxun-$(Get-Date -Format yyyyMMdd-HHmmss).db
```

**恢复数据库：**

```powershell
# 先停止后端服务，再执行恢复。
Copy-Item backups\yunxun-20260524-120000.db backend\yunxun.db -Force
```

**删除并重新初始化：**

```powershell
# 先停止后端服务。再次启动后端会自动创建新的 SQLite 数据库。
Remove-Item backend\yunxun.db
python backend\main.py
```

## 安全与会话

登录、注册和访客登录成功后，后端会生成一个原始 token 返回给前端。前端继续按原有方式在请求头中携带：

```http
Authorization: Bearer <token>
```

数据库不会保存这个原始 token，只保存基于 `YUNXUN_JWT_SECRET` 计算出的 HMAC-SHA256 哈希。后端收到请求后，会对前端传来的 token 重新计算哈希，再查询数据库。这样即使数据库文件被误复制，里面的 token 也不能直接拿来登录。

如果项目从旧版本升级，后端启动初始化数据库时会识别旧的明文 token 表，并重建为哈希 token 表。旧登录态会失效，用户重新登录即可。

过期 token 的清理不会在每次接口鉴权时全表执行。当前策略是在签发新 token 时顺带清理过期记录，普通接口请求只检查当前 token 是否存在且未过期。

聊天发送接口支持 `X-Idempotency-Key` 请求头。前端每次主动发送会生成新标识；网络重试复用同一标识时，后端会回放已完成结果或拒绝仍在进行中的重复请求，避免重复调用模型和重复落库。

## 豆包 / Ark 配置

根目录 `.env` 示例：

```env
DOUBAO_API_KEY=你的真实Ark API Key
DOUBAO_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
DOUBAO_CHAT_ENDPOINT=doubao-seed-1-6-250615
DOUBAO_VISION_ENDPOINT=doubao-seed-1-6-250615
DOUBAO_AVAILABLE_MODELS=doubao-seed-1-6-250615
```

配置真实 Key 后**必须重启后端**，然后访问健康检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8001/api/health
```

返回内容中应看到 `ai_configured=true`。如果仍然是 `false`，通常说明：`.env` 未被后端读取、Key 仍是占位值、变量名写错，或后端尚未重启。

## 演示模式说明

如果 `DOUBAO_API_KEY` 为空，或仍保持 `your-doubao-api-key` 这类占位值，系统会进入**本地演示模式**。

演示模式可以：

- 打开前端页面。
- 登录、访客登录和创建会话。
- 发送农技问题并看到固定演示回复。
- 上传图片并看到固定诊断建议。
- 查看今日农活建议的演示结果。

> ⚠️ 演示模式**不是**实时 AI 识别，不会真正分析图片内容，也不能替代真实农技判断。需要验证真实问答和图片理解能力时，请配置有效豆包 / Ark Key，并用 `/api/health` 确认 `ai_configured=true`。

## 线上部署（GitHub Pages + Render）

当前仓库已包含前端部署到 GitHub Pages 的工作流 `.github/workflows/deploy-frontend.yml`。GitHub Pages 只能托管静态前端，因此后端需要单独托管（以下以 Render 免费层为例）。

### 前端（GitHub Pages）

1. 仓库 → **Settings** → **Pages** → **Build and deployment** → Source 设为 **GitHub Actions**。
2. 推送到 `main`（或改动 `frontend/**`）会自动触发构建与部署。
3. 站点地址：<https://PtPPPPP.github.io/yunxun/>。
4. 在仓库 **Settings → Secrets and variables → Actions → Variables** 添加 `VITE_YUNXUN_API_BASE_URL`，值为后端公网地址（**无尾斜杠**），让前端指向真实后端。未配置时前端会 fallback 到本地演示地址。

`frontend/vite.config.ts` 已在构建时设置 `base: "/yunxun/"` 以匹配项目站点路径；本地 `npm run dev` 仍使用根路径 `/`。

### 后端（Render，示例）

1. render.com → **New** → **Web Service** → 选本仓库，Root Directory 留空。
2. **Build Command**：`pip install -r backend/requirements.txt`
3. **Start Command**：`uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT`
4. 环境变量至少配置：
   - `DOUBAO_API_KEY`：真实 Ark Key。
   - `YUNXUN_ALLOWED_ORIGINS`：`https://PtPPPPP.github.io`。
   - `YUNXUN_ENV=production`、`YUNXUN_DEBUG=false`、`YUNXUN_JWT_SECRET=<随机串>`。
5. 部署成功后获得公网地址，回填到上面前端的 `VITE_YUNXUN_API_BASE_URL` 变量，并重新触发前端工作流。

> ⚠️ **注意**：Render 免费层文件系统不持久，SQLite 数据会在重启或重新部署后重置；免费层 15 分钟无访问会休眠，冷启动约 30s。需要持久化数据请升级数据库或换用带持久磁盘的平台（如 Fly.io 的 volume）。

## 最小验证流程

**代码级验证：**

```powershell
python -m compileall backend
python -m unittest
Set-Location frontend
npm ci
npm run lint
npm run build
npm run test:e2e
npm audit
Set-Location ..
python scripts\count_source_lines.py
```

`npm run test:e2e` 会启动真实 Chromium、独立后端和临时 SQLite 数据库；结束后自动清理数据。失败用例的截图和 trace 保存在 `frontend/test-results/`，生产环境不会启用测试数据库。

首次运行 Playwright 前执行 `npx playwright install chromium`。E2E 使用本地演示模型，不读取真实 API Key，也不会连接开发或生产数据库。

## 数据库迁移

当前 SQLite Schema 版本为 `1`，记录在 `PRAGMA user_version`。后端启动时会在单个事务内按顺序升级；迁移失败会回滚且不会推进版本。版本高于当前代码支持范围时会拒绝启动。升级前请停止后端并备份 `backend/yunxun.db`；当前不支持自动降级。

SQLite 适合当前单机或小规模部署，不支持多个服务实例共享同一个数据库文件。生产环境必须设置至少 32 字符的随机 `YUNXUN_JWT_SECRET`、明确的 CORS 来源并关闭 debug。缺少模型 Key 只会进入本地演示模式，不影响基础会话功能。

## 生产运维

发布前检查并启动后端：

```powershell
python scripts\check_release.py
powershell -File scripts\start_backend.ps1
```

构建前端执行 `powershell -File scripts\build_frontend.ps1`。CI 位于 `.github/workflows/ci.yml`，push 和 Pull Request 会运行后端、Vitest、lint、build、依赖审计及真实 Chromium E2E；失败的 Playwright 截图、trace 和报告会作为短期构建产物保存。

数据库使用 SQLite Backup API 创建一致性备份，不要在服务写入时复制 `.db`、`-wal` 文件：

```powershell
python scripts\database_admin.py backup --dir backups --keep 10
python scripts\database_admin.py verify backups\yunxun-时间戳.db
# 恢复前必须停止后端
python scripts\database_admin.py restore backups\yunxun-时间戳.db --dir backups
```

恢复前会自动备份当前数据库，并通过临时文件原子替换；失败时保留原数据库。探针为 `/health/live` 和 `/health/ready`，readiness 会检查连接、Schema 版本和核心表，但不会调用付费模型。发布步骤和回滚要求见 `docs/release-checklist.md`，版本变更见 `CHANGELOG.md`。

Windows每日备份计划只生成脚本，不会自动注册：

```powershell
scripts\backup_task.ps1 -Action Install -BackupDirectory D:\yunxun-backups -Keep 10 -DailyAt 02:00
scripts\backup_task.ps1 -Action Show
scripts\backup_task.ps1 -Action Run
scripts\backup_task.ps1 -Action Disable
scripts\backup_task.ps1 -Action Delete
```

发布封板可执行 `python scripts\release_rehearsal.py`，它会在临时目录中重新创建Python虚拟环境、执行`npm ci`、构建、启动、重启和备份恢复。执行 `python scripts\package_release.py` 会在`dist/release/`生成V1.0 ZIP、Manifest和SHA-256；该目录不进入Git。

GitHub Actions 会在推送和 Pull Request 时执行同等的后端、前端和安全检查。

**本地冒烟流程：**

1. 复制 `.env.example` 和 `frontend\.env.example`。
2. 启动后端：`python backend\main.py`。
3. 打开 <http://127.0.0.1:8001/api/health>，确认服务返回正常。
4. 打开 <http://127.0.0.1:8001/docs>，确认接口文档可访问。
5. 启动前端：`Set-Location frontend` 后执行 `npm run dev`。
6. 打开 <http://127.0.0.1:5173>，注册或访客登录。
7. 创建一个会话，发送一条农技问题，确认有回复。
8. 进入图片诊断或今日农活建议流程，确认页面可提交并返回结果。

## 软著源码材料

项目内置源码材料脚本。默认命令仅统计正式源码并显示固定文件顺序：

```powershell
python scripts\count_source_lines.py
```

需要生成软著源码文本和清单时执行：

```powershell
python scripts\count_source_lines.py --generate
```

输出目录为 `docs/software-copyright/`，包含：

- `source-code.txt`：使用统一产品名称和发布版本页眉，每页50行源码正文。
- `source-code-manifest.txt`：记录生成时间、统计结果、排除规则、固定排序和实际文件清单。

筛选口径：

我- 纳入后端正式 `.py` 源码，以及 `frontend/src` 下的核心 `.ts`、`.tsx`、`.js`、`.jsx` 和 `.css` 源码。
- 自动排除测试、依赖、锁文件、构建产物、缓存、虚拟环境、声明文件和重复生成文件。
- 按后端入口、API、业务逻辑、数据层、核心工具、前端入口、页面组件、服务工具和样式的顺序稳定输出。
- 统计并导出有效源码行，不使用“前后端分别超过1750行”作为硬编码判断。

生成文本为 UTF-8 编码，页眉不计入每页50行源码正文。

## 常见问题

### 前端提示 `Network Error`

- 确认后端正在运行，并能打开 <http://127.0.0.1:8001/api/health>。
- 确认 `frontend/.env` 的 `VITE_YUNXUN_API_BASE_URL` 和后端端口一致。
- 修改 `frontend/.env` 后需要重启 `npm run dev`。
- 局域网访问时，确认 `YUNXUN_ALLOWED_ORIGINS` 包含当前前端页面地址。

### 后端端口被占用

先查看占用进程：

```powershell
netstat -ano | findstr :8001
```

可以停止占用进程，或改用新端口：

```env
YUNXUN_PORT=8011
PORT=8011
YUNXUN_BACKEND_URL=http://127.0.0.1:8011
```

同时修改前端：

```env
VITE_YUNXUN_API_BASE_URL=http://127.0.0.1:8011
```

然后重启后端和前端。

### 登录后仍提示“请先登录”

- 确认浏览器请求头里带有 `Authorization: Bearer <token>`。
- 确认前端连接的是当前正在运行的后端地址，而不是旧端口或旧服务。
- 如果刚从旧版本升级，旧登录态会因为 token 表安全迁移而失效，重新登录或使用访客登录即可。

### 局域网无法访问

- 在后端电脑执行 `ipconfig`，确认实际 IP 是否仍是 `192.168.1.10`。
- 确认后端 `.env` 中 `YUNXUN_HOST=0.0.0.0`。
- 确认其他设备能访问 <http://192.168.1.10:8001/api/health>。
- 检查 Windows 防火墙是否放行 `8001` 和 `5173`。
- 检查 `YUNXUN_ALLOWED_ORIGINS` 是否包含实际前端地址。
- 确认前端 `VITE_YUNXUN_API_BASE_URL` 使用的是后端电脑 IP，不是访问设备自己的 `127.0.0.1`。

### Key 已配置但仍然是演示模式

- 确认根目录 `.env` 里 `DOUBAO_API_KEY` 不是空值，也不是 `your-doubao-api-key`。
- 确认变量名是 `DOUBAO_API_KEY`，不是其他拼写。
- 修改 `.env` 后必须重启后端。
- 打开 `/api/health`，确认 `ai_configured=true`。
- 确认 `DOUBAO_BASE_URL`、`DOUBAO_CHAT_ENDPOINT`、`DOUBAO_VISION_ENDPOINT` 与 Ark 控制台配置一致。

## 商用 MVP 边界

当前版本适合本地 / 内网小规模试用和商业 MVP 演示，**不适合**不经加固就作为公开互联网 SaaS 直接上线。

> ⚠️ AI 诊断只提供初步建议，**不能**作为病虫害定性、处方用药或安全生产的唯一依据。涉及农药、肥料、剂量、安全间隔期和采收要求时，必须以当地农技站、产品标签、监管要求和专业人员意见为准。

当前版本**不包含**：

- 多租户隔离。
- 在线支付和套餐计费。
- 完整后台管理系统。
- 公开 HTTPS 部署方案。
- PostgreSQL 生产数据库和迁移体系。
- 企业级审计、权限和用量统计。

## 后续升级建议

- 增加 Docker Compose，一键启动后端、前端和数据库。
- 从 SQLite 升级到 PostgreSQL，并引入数据库迁移。
- 增加后台管理系统，用于用户、会话、配置和内容审核。
- 增加用量统计、调用成本统计和错误监控。
- 增加角色权限，例如管理员、农技员、普通用户。
- 增加公网 HTTPS 部署方案和反向代理配置。
- 增加 SaaS 计费、套餐、组织空间和多租户隔离。
