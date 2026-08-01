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

健康检查不会调用付费模型。

## 数据库与备份

SQLite 默认位于 `backend/yunxun.db`。备份、恢复、迁移或删除前应停止后端写入。使用 `scripts/database_admin.py` 通过 SQLite Backup API 操作，不直接复制活动中的 WAL 数据库。

## 公网限制

仓库中的 GitHub Pages 工作流只部署静态前端。当前没有经过验收的公网后端、HTTPS、Nginx、容器、多实例、PostgreSQL 或集中监控方案；不得据此宣称已具备公网 SaaS 能力。
