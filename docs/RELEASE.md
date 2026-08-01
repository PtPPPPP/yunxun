# 发布与回滚

## 发布前

- 后端编译、单元测试、前端测试、lint、build、E2E 和依赖审计全部通过。
- 执行 `python scripts/check_release.py`。
- 使用 `scripts/database_admin.py` 创建并验证备份。
- 生产 Secret 至少 32 字符，关闭 Debug，CORS 只允许正式来源。
- 核对当前代码支持的 Schema；标签版 V1.0 为 1，当前工作区为 2。
- 核对 README、V1_SCOPE、CHANGELOG、软著材料和版本号。

## 发布演练

```powershell
python scripts\release_rehearsal.py
```

演练在临时目录中安装依赖、构建、启动、重启并验证备份恢复，不使用正式数据库。通过后再生成发布候选：

```powershell
python scripts\package_release.py
python scripts\check_release.py
```

发布包位于 `dist/release/`，不进入 Git。

## 发布中

- 停止后端写入并再次备份。
- 部署代码并执行启动迁移。
- 检查 `/health/live` 与 `/health/ready`。
- 部署前端，执行登录、会话、消息、图片和农活建议冒烟。

## 发布后

- 检查请求 ID、错误日志和数据库 Schema。
- 验证登录、新建会话、发送、删除和定时备份。
- 保存 Manifest、SHA-256、测试数字和备份验证记录。

## 回滚

先停止后端并备份当前数据库，再回滚代码。Schema 不支持自动降级；如果旧代码不支持当前 Schema，必须使用经过验证的发布前备份执行：

```powershell
python scripts\database_admin.py restore <备份文件> --dir <备份目录>
```

禁止通过删除数据库掩盖迁移失败。
