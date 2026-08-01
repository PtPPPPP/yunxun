# 测试说明

所有默认验证使用临时或测试数据，不调用真实付费模型，不使用生产数据库。

## 快速检查

```powershell
python -m compileall backend
python -m unittest
Set-Location frontend
npm run test
npm run lint
npm run build
```

## 完整验证

```powershell
python -m compileall backend
python -m unittest

Set-Location frontend
npm run test
npm run lint
npm run build
npm run test:e2e
npm audit --audit-level=moderate
Set-Location ..

python -m pip_audit -r backend\requirements.txt
python scripts\check_release.py
python scripts\http_load_test.py
python scripts\release_rehearsal.py
```

`pip-audit` 未安装时，应在隔离虚拟环境中安装后执行，不写入项目依赖文件。Playwright 使用系统临时目录中的 SQLite 数据库，并在结束时清理。

## 数据库验证

```powershell
python scripts\database_admin.py backup --dir <临时目录> --keep 2
python scripts\database_admin.py verify <备份文件>
python scripts\database_admin.py rehearse-restore <备份文件>
```

不要在自动测试中执行覆盖正式数据库的 `restore`。

## BYOK 真实冒烟

`scripts/byok_real_smoke.py` 默认跳过。它属于 V1.2 前置验证，本轮不得读取真实 Key 或自动启用。只有人工明确提供临时测试 Key 并批准一次真实调用时才能运行。

## 结果记录

最终报告只记录各类通过数、失败数和关键失败原因，不用“存在 Mock”替代真实能力证明。
