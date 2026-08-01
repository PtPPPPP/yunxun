# 测试说明

默认测试使用临时数据库和演示模型，不读取真实付费 Key，也不修改正式用户数据库。

```powershell
python -m compileall backend
python -m unittest
Set-Location frontend
npm run test
npm run lint
npm run build
npm run test:e2e
npm audit --audit-level=moderate
```

发布和数据库演练：

```powershell
python scripts\check_release.py
python scripts\http_load_test.py
python scripts\release_rehearsal.py
python scripts\database_admin.py backup --dir <临时目录> --keep 2
```

`pip-audit` 在隔离环境中可单独安装运行；缺少工具时必须在最终报告中如实标记。

本轮新增后端会话功能测试、前端导出测试和 6 条演示模式 E2E 流程，覆盖搜索空状态、置顶、复制、导出、帮助、关于、清空和重新生成入口。
