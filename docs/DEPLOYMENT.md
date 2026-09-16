# 部署说明

## 正式适用方式

V1.0 面向 Windows 本机或同一局域网内的单机部署。后端默认监听 `0.0.0.0:8001`，前端开发服务默认使用 `5173`。

## 本机启动

```powershell
powershell -File scripts\start_backend.ps1
powershell -File scripts\build_frontend.ps1
```

也可直接运行 `python backend\main.py` 和 `npm run dev`。

## 局域网

- `YUNXUN_HOST=0.0.0.0`。
- `YUNXUN_ALLOWED_ORIGINS` 必须列出实际前端来源。
- `VITE_YUNXUN_API_BASE_URL` 指向后端电脑的局域网地址。
- Windows 防火墙只开放实际使用的端口。

## 健康检查

- `/api/health`：运行状态和配置摘要。
- `/health/live`：进程存活。
- `/health/ready`：数据库连接、Schema 和核心表就绪。

健康检查只读取本机数据库和配置，不访问任何外部服务。

## 数据库与备份

SQLite 默认位于 `backend/yunxun.db`。备份、恢复、迁移或删除前应停止后端写入。使用 `scripts/database_admin.py` 通过 SQLite Backup API 操作，不直接复制活动中的 WAL 数据库。

## GitHub Pages 演示与后端的配对

`.github/workflows/deploy-frontend.yml` 会在每次推送到 `main` 时自动部署静态前端；
**后端不在这个仓库里自动部署**（根目录没有 `render.yaml`，Render 服务是在面板上手工建的）。
两边版本会自动漂移，所以上线后如果页面能打开但功能全空、或操作报错，先按下面顺序排查：

1. **确认后端跑的是最新代码。** 调用 `GET /api/health`，返回里必须有 `app_name` 与
   `schema_version`。如果只有 `mode` / `ai_configured` / `available_models` 这类字段，
   说明后端还是改造前的旧版本，需要在 Render 上重新部署当前 `main`。
2. **确认允许来源与浏览器的 Origin 完全一致。** 浏览器发出的 `Origin` 里主机名一律
   是小写，例如 `https://ptppppp.github.io`。`YUNXUN_ALLOWED_ORIGINS` 里写了大小写混合的
   `https://PtPPPPP.github.io` 时，CORS 匹配会失败、浏览器会拦掉**所有** API 请求，
   表现是页面加载出来但一直连不上后端。代码已对配置值统一转小写来容忍这种写法，
   但仍建议按实际 Origin 的写法配置。
3. **确认 `VITE_YUNXUN_API_BASE_URL` 指向后端地址。** 它来自仓库
   `Settings → Secrets and variables → Actions → Variables`，未配置时前端会回退到
   `http://127.0.0.1:8001`。

注意 Render 默认的文件系统是临时的：SQLite 存在实例磁盘上，每次重新部署或实例重建都会
重置（除非挂了持久磁盘）。所以公网这套只适合作为界面演示，真实台账数据请留在本机部署。

## 公网限制

仓库中的 GitHub Pages 工作流只部署静态前端。当前没有经过验收的公网后端、HTTPS、Nginx、容器、多实例、PostgreSQL 或集中监控方案；不得据此宣称已具备公网 SaaS 能力。
