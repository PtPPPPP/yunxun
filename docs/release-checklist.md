# V1.0 发布检查清单

## 发布前

- [ ] 后端、前端、E2E、依赖审计全部通过
- [ ] 执行 `python scripts/database_admin.py backup`
- [ ] `python scripts/check_release.py` 通过
- [ ] 生产 Secret 至少32字符，Debug关闭，CORS只含正式域名
- [ ] 前端构建完成，Schema 版本为1

## 发布中

- [ ] 停止后端写入并再次备份
- [ ] 部署代码并运行启动检查和迁移
- [ ] 启动后端，检查 `/health/live` 与 `/health/ready`
- [ ] 部署前端并执行登录、会话、消息 smoke test

## 发布后

- [ ] 检查 request ID 关联日志和错误数量
- [ ] 验证登录、新建会话、发送、删除和定时备份
- [ ] 确认数据库 Schema 版本和备份可验证

## 回滚

先停止后端并备份当前数据库，再回滚代码。Schema 不支持自动降级；如旧代码不支持当前 Schema，使用经过验证的发布前备份执行 `python scripts/database_admin.py restore <备份文件>`，然后重启。禁止删除数据库重新开始。
