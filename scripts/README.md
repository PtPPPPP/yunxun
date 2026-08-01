# 工程脚本

脚本保持现有路径，避免破坏 README、CI、PowerShell 和 Python 子进程调用。

## 开发

- `start_backend.ps1`：执行发布配置检查后启动后端。
- `build_frontend.ps1`：安装/检查前端依赖并构建前端。
- `count_source_lines.py`：统计正式源码；`--generate` 生成软著源码文本和清单。

## 测试

- `http_load_test.py`：使用临时 SQLite 和演示模型执行本地并发负载测试。
- 日常单元、前端和 E2E 测试直接使用 Python/npm 命令，脚本不复制测试逻辑。

## 数据库运维

- `database_admin.py backup`：通过 SQLite Backup API 创建一致性备份。
- `database_admin.py verify`：验证备份和 Schema。
- `database_admin.py rehearse-restore`：在临时目录演练恢复，不覆盖正式数据库。
- `database_admin.py restore`：覆盖性恢复；必须先停止后端并明确指定备份。
- `backup_task.ps1`：安装、查看、运行、禁用或删除 Windows 定时备份任务。

## 发布

- `check_release.py`：检查版本、配置、数据库和发布条件。
- `package_release.py`：生成 ZIP、Manifest 和 SHA-256 到 `dist/release/`。
- `release_rehearsal.py`：在临时目录执行依赖安装、构建、启动、重启和备份恢复演练。

## 实验性 BYOK

- `byok_real_smoke.py`：默认跳过；只有设置 `RUN_BYOK_REAL_SMOKE=1` 并人工提供临时测试 Key 时才进行一次真实调用。

BYOK 不属于 V1.0，本轮验证不得自动运行真实冒烟或读取真实 Key。
