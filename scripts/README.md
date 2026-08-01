# 工具脚本

脚本路径保持不变，避免破坏 README、CI、PowerShell 和子进程引用。

- 开发：`start_backend.ps1`、`build_frontend.ps1`
- 测试：`http_load_test.py`
- 数据库运维：`database_admin.py`、`backup_task.ps1`
- 发布：`check_release.py`、`package_release.py`、`release_rehearsal.py`
- 实验：仅保留当前仍被引用的实验脚本；用户模型 API Key 接入脚本已删除。
