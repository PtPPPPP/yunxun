# 云寻 AI 本地/内网商业 MVP 加固设计

## 目标

本阶段目标是把 `yunxun` 从可运行原型加固为“本地/内网可试用的商业 MVP”。它应当适合小团队、合作社、农场或基层农技场景在 Windows 电脑或局域网内小规模试用。

本阶段不追求云端 SaaS，不做大规模重构，也不更换技术栈。重点是让少量真实用户能用、出了问题能定位、交付时能讲清楚。

## 范围

必须保留当前技术架构：

- 后端：FastAPI，启动入口仍为 `backend/main.py`
- 前端：React/Vite，入口仍为 `frontend/src/main.tsx`
- 数据库：SQLite，适合单机和内网小规模试用
- 模型接入：继续支持豆包/Ark
- 部署方式：以 Windows 本地和局域网部署为主

本阶段不做：

- 多租户
- 支付
- 套餐系统
- PostgreSQL 迁移
- 复杂后台管理系统
- 公网 SaaS 部署
- 大规模重构或换框架

## 后端设计

后端只做上线 MVP 必要加固，不改变现有接口路径和返回格式。

### 配置

统一从 `.env` 读取运行配置，并在 README 中说明每个关键配置的用途。需要覆盖：

- `YUNXUN_ENV`
- `YUNXUN_DEBUG`
- `YUNXUN_HOST`
- `YUNXUN_PORT` / `PORT`
- `YUNXUN_BACKEND_URL`
- `YUNXUN_ALLOWED_ORIGINS`
- `YUNXUN_DATABASE_URL` / `YUNXUN_DB_PATH`
- `YUNXUN_MAX_MESSAGE_LENGTH`
- `YUNXUN_REQUESTS_PER_MINUTE`
- `YUNXUN_TOKEN_EXPIRE_HOURS`
- `DOUBAO_API_KEY`
- `DOUBAO_BASE_URL`
- `DOUBAO_CHAT_ENDPOINT`
- `DOUBAO_VISION_ENDPOINT`
- `DOUBAO_AVAILABLE_MODELS`

内网试用时，后端应继续支持 `0.0.0.0` 监听，并要求前端 API 地址改成后端电脑的局域网 IP。

### 启动检查

`python backend/main.py` 启动时应继续保留端口占用检查。后端初始化期间应能通过日志或健康检查确认：

- 当前运行模式
- 后端监听地址和端口
- 数据库路径
- CORS 允许来源
- 模型是否已配置
- 请求频率限制

这些信息不能泄露 API Key、token、密码或完整图片内容。

### 日志

增加适合本地/内网排障的基础日志。日志重点覆盖：

- 应用启动和初始化
- 登录、注册、访客登录、退出
- 聊天消息创建
- 田间诊断请求
- 今日农活请求
- 模型未配置和模型调用失败
- 限流触发
- 数据库初始化或不可写错误

日志不记录明文密码、认证 token、完整图片 base64、完整模型密钥。用户输入可以记录长度、会话 ID、功能类型等元信息，不默认记录全部正文。

### 错误处理

继续保持统一响应风格：

```json
{
  "success": false,
  "error": "错误信息"
}
```

需要让常见问题给出用户可理解提示：

- 后端未连接
- 未配置模型 Key
- 模型服务调用失败
- 请求太频繁
- 图片或文本过大
- 数据库不可写
- 登录状态失效

### SQLite

继续使用当前自动建表逻辑。README 需要明确：

- 数据库默认位置
- 首次启动会自动初始化
- 如何备份 `.db` 文件
- 如何恢复 `.db` 文件
- 如何删除数据库并重新初始化
- 不要把真实数据库提交到 Git

### 安全

本阶段保留数据库保存的 opaque token，不改成 JWT。README 需要明确生产/内网试用注意事项：

- 修改默认密钥和示例密码
- 限制 `YUNXUN_ALLOWED_ORIGINS`
- 不提交 `.env`
- 不提交 SQLite 数据库
- 不公开 `DOUBAO_API_KEY`
- 内网访问时确认防火墙和可信网络范围

## 前端设计

前端保持现有工作台结构，不重做整体视觉方向。重点补齐真实试用时的状态反馈。

### 状态展示

登录页和工作台应清楚显示：

- 当前后端地址
- 当前运行模式
- 模型状态：真实模型模式或本地演示模式
- 请求限制或可用模型数量

任何状态展示都不能泄露 API Key。

### 交互提示

用户遇到以下情况时，应看到能理解的提示：

- 后端没有启动
- 前端 API 地址配置错误
- 模型 Key 未配置，当前处于演示回退
- 模型调用失败
- 请求太频繁
- 输入文本或图片过大
- 登录状态失效

### 商用边界提醒

README 必须明确说明：AI 诊断只提供初步建议，农药、肥料、剂量和安全间隔期以当地农技站、产品标签和监管要求为准。前端现有回答策略已经包含安全提醒，本阶段不新增复杂合规系统。

## README 设计

README 要从“整理记录”升级为“交付文档”。建议结构：

1. 项目介绍
2. 适用场景
3. 功能清单
4. 技术架构
5. 目录结构
6. 环境要求
7. Windows 本地启动
8. 局域网访问
9. 环境变量说明
10. SQLite 初始化、备份、恢复和重建
11. 豆包/Ark API Key 配置
12. 演示模式说明
13. 最小验证流程
14. 常见问题
15. 商用 MVP 边界
16. 后续升级建议

README 中必须明确说明：未配置模型 Key 时，系统可以进入演示流程，但演示模式不等于真实 AI 识别。

## 验收标准

本阶段完成后应满足：

- `python backend/main.py` 可以启动后端
- `cd frontend && npm run dev` 可以启动前端
- 前端可以通过环境变量连接后端
- 没配置模型 Key 时，系统仍可进入演示流程
- 配置模型 Key 后，可以走真实模型调用流程
- README 能让新用户按步骤在 Windows 本地跑起来
- README 能说明局域网访问方式
- README 能说明 SQLite 数据位置、备份、恢复和重建
- 后端日志能辅助定位常见问题
- 不破坏现有 FastAPI + React/Vite 架构
- 不破坏已有接口返回格式

## 最小验证流程

实现完成后至少运行：

```bash
python -m compileall backend
python -m unittest backend.tests.test_decision_service
```

```bash
cd frontend
npm run build
```

在条件允许时，还要启动后端和前端，完成一次健康检查和页面连通验证：

- `GET /api/health`
- 登录或访客登录
- 发送一条聊天消息
- 在未配置模型 Key 时确认演示回退提示
- 在配置模型 Key 后确认真实模型调用路径

## 后续升级建议

本阶段之后，如果要继续走向更完整商业化，可按优先级逐步增加：

- PostgreSQL 和迁移工具
- 管理员后台
- 用量统计和审计日志
- 账号邀请和角色权限
- Docker Compose 内网部署包
- 公网 HTTPS 部署
- 付费、套餐和租户能力

