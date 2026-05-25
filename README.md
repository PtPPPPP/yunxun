# 云寻 AI

云寻 AI 是一个面向农业场景的本地/内网 AI 工作台，提供农技问答、田间图片初步诊断和今日农活建议。当前版本定位为“本地/内网可试用的商业 MVP”：适合小团队、合作社、农场或基层农技人员在 Windows 电脑和局域网内小规模试用。

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
- 健康检查：通过 `/api/health` 查看服务状态和 AI 配置状态。
- 本地演示模式：未配置真实豆包 / Ark Key 时仍可打开前端、登录、创建会话并查看固定演示回复。

## 技术架构

- 后端：Python + FastAPI，本机可通过 `http://127.0.0.1:8001` 访问，接口文档默认位于 `/docs`。
- 前端：React + Vite，开发服务默认位于 `http://127.0.0.1:5173`。
- 数据库：SQLite，默认文件为 `backend/yunxun.db`，首次启动自动初始化。
- AI 服务：豆包 / Ark OpenAI 兼容接口；Key 为空或保持占位值时进入本地演示模式。

## 目录结构

```text
yunxun/
|-- backend/
|   |-- app/
|   |   |-- api/
|   |   |-- core/
|   |   |-- services/
|   |   |-- main.py
|   |   |-- repositories.py
|   |   `-- schemas.py
|   |-- tests/
|   |-- main.py
|   `-- requirements.txt
|-- frontend/
|   |-- src/
|   |-- .env.example
|   |-- package.json
|   `-- vite.config.ts
|-- .env.example
|-- AGENTS.md
`-- README.md
```

## 环境要求

- Windows 10/11。
- PowerShell 5+ 或 PowerShell 7+。
- Python 3.10+。
- Node.js `^20.19.0 || >=22.12.0` 和 npm。当前 Vite 版本不支持只安装 Node.js 18。
- 可选：真实豆包 / Ark API Key。

建议先进入项目目录。把 `<your-yunxun-path>` 替换为实际项目路径，例如 `D:\Projects\yunxun`：

```powershell
$ProjectPath = "<your-yunxun-path>"
Set-Location $ProjectPath
```

## Windows 本地启动

1. 复制环境变量模板：

```powershell
Copy-Item .env.example .env
Copy-Item frontend\.env.example frontend\.env
```

2. 安装后端依赖：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r backend\requirements.txt
```

3. 启动后端：

```powershell
python backend\main.py
```

后端本机默认地址：

- 健康检查：http://127.0.0.1:8001/api/health
- 接口文档：http://127.0.0.1:8001/docs

4. 新开一个 PowerShell 窗口，安装并启动前端：

```powershell
$ProjectPath = "<your-yunxun-path>"
Set-Location "$ProjectPath\frontend"
npm install
npm run dev
```

前端本机默认地址：

- http://127.0.0.1:5173

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

注意事项：

- 后端监听地址保持 `YUNXUN_HOST=0.0.0.0`，才能接受局域网其他设备访问。
- `YUNXUN_ALLOWED_ORIGINS` 必须包含实际打开前端页面的地址，否则浏览器会被 CORS 拦截。
- Windows 防火墙需要允许后端端口 `8001` 和前端端口 `5173` 入站访问。
- 其他设备要和后端电脑在同一局域网内，并使用 `http://192.168.1.10:5173` 或对应前端地址访问。
- 如果后端电脑 IP 变化，需要同步修改 `.env` 和 `frontend/.env`，然后重启后端和前端。

可用 PowerShell 查看本机 IP：

```powershell
ipconfig
```

如需开放防火墙端口，请在管理员 PowerShell 中执行：

```powershell
New-NetFirewallRule -DisplayName "Yunxun Backend 8001" -Direction Inbound -Protocol TCP -LocalPort 8001 -Action Allow
New-NetFirewallRule -DisplayName "Yunxun Frontend 5173" -Direction Inbound -Protocol TCP -LocalPort 5173 -Action Allow
```

## 环境变量说明

### 后端 `.env`

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `YUNXUN_APP_NAME` | `云寻 AI` | 应用名称。 |
| `YUNXUN_APP_VERSION` | `4.0.0` | 应用版本。 |
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
| `YUNXUN_CORS_HEADERS` | `Authorization,Content-Type` | 允许的 CORS 请求头。 |
| `YUNXUN_MAX_MESSAGE_LENGTH` | `3000` | 单条消息最大长度。 |
| `YUNXUN_REQUESTS_PER_MINUTE` | `20` | 简单请求频率限制。 |
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

不要把真实 `.db` 文件提交到 Git。数据库里会包含用户、会话和消息等本地试用数据。

SQLite 文件操作建议离线执行：备份、恢复、删除和重新初始化前，都先停止后端服务，避免复制到正在写入的数据库文件。

备份数据库：

```powershell
# 先停止后端服务，再执行备份。
New-Item -ItemType Directory -Force backups
Copy-Item backend\yunxun.db backups\yunxun-$(Get-Date -Format yyyyMMdd-HHmmss).db
```

恢复数据库：

```powershell
# 先停止后端服务，再执行恢复。
Copy-Item backups\yunxun-20260524-120000.db backend\yunxun.db -Force
```

删除并重新初始化：

```powershell
# 先停止后端服务。再次启动后端会自动创建新的 SQLite 数据库。
Remove-Item backend\yunxun.db
python backend\main.py
```

## 豆包 / Ark 配置

根目录 `.env` 示例：

```env
DOUBAO_API_KEY=你的真实Ark API Key
DOUBAO_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
DOUBAO_CHAT_ENDPOINT=doubao-seed-1-6-250615
DOUBAO_VISION_ENDPOINT=doubao-seed-1-6-250615
DOUBAO_AVAILABLE_MODELS=doubao-seed-1-6-250615
```

配置真实 Key 后必须重启后端。然后访问健康检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8001/api/health
```

返回内容中应看到 `ai_configured=true`。如果仍然是 `false`，通常说明 `.env` 未被后端读取、Key 仍是占位值、变量名写错，或后端尚未重启。

## 演示模式说明

如果 `DOUBAO_API_KEY` 为空，或仍保持 `your-doubao-api-key` 这类占位值，系统会进入本地演示模式。

演示模式可以：

- 打开前端页面。
- 登录、访客登录和创建会话。
- 发送农技问题并看到固定演示回复。
- 上传图片并看到固定诊断建议。
- 查看今日农活建议的演示结果。

演示模式不是实时 AI 识别，不会真正分析图片内容，也不能替代真实农技判断。需要验证真实问答和图片理解能力时，请配置有效豆包 / Ark Key，并用 `/api/health` 确认 `ai_configured=true`。

## 最小验证流程

代码级验证命令：

```powershell
python -m compileall backend
python -m unittest backend.tests.test_audit backend.tests.test_config_runtime backend.tests.test_system_service backend.tests.test_decision_service
Set-Location frontend
npm run build
Set-Location ..
```

本地冒烟流程：

1. 复制 `.env.example` 和 `frontend\.env.example`。
2. 启动后端：`python backend\main.py`。
3. 打开 `http://127.0.0.1:8001/api/health`，确认服务返回正常。
4. 打开 `http://127.0.0.1:8001/docs`，确认接口文档可访问。
5. 启动前端：`Set-Location frontend` 后执行 `npm run dev`。
6. 打开 `http://127.0.0.1:5173`，注册或访客登录。
7. 创建一个会话，发送一条农技问题，确认有回复。
8. 进入图片诊断或今日农活建议流程，确认页面可提交并返回结果。

## 常见问题

### 前端提示 `Network Error`

- 确认后端正在运行，并能打开 `http://127.0.0.1:8001/api/health`。
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

### 局域网无法访问

- 在后端电脑执行 `ipconfig`，确认实际 IP 是否仍是 `192.168.1.10`。
- 确认后端 `.env` 中 `YUNXUN_HOST=0.0.0.0`。
- 确认其他设备能访问 `http://192.168.1.10:8001/api/health`。
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

当前版本适合本地/内网小规模试用和商业 MVP 演示，不适合作为公开互联网 SaaS 直接上线。

AI 诊断只提供初步建议，不能作为病虫害定性、处方用药或安全生产的唯一依据。涉及农药、肥料、剂量、安全间隔期和采收要求时，必须以当地农技站、产品标签、监管要求和专业人员意见为准。

当前版本不包含：

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
