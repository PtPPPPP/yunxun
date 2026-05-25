# AGENTS.md

本文件记录 `yunxun` 项目的默认协作规则，供 Codex 或其他自动化助手在本仓库内工作时参考。

## 1. 项目目标

`yunxun` 是一个前后端分离项目，当前优先目标是：

- 保证项目稳定可运行
- 保证后端 FastAPI 服务可启动
- 保证前端 React/Vite 页面可开发和构建
- 保持现有 FastAPI + React/Vite 架构
- 小步修改、明确验证、避免无关重构
- 在不破坏现有接口的前提下逐步提升工程质量

除非用户明确要求，不要为了“看起来更规范”而大规模重写业务逻辑或整体目录结构。

## 2. 项目入口

### 后端

- 后端启动入口：`backend/main.py`
- FastAPI app：`backend/app/main.py`
- 推荐启动命令：

```bash
python backend/main.py