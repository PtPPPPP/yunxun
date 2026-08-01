# V1.0 截图计划

截图必须来自 `v1.0.0` 可复现功能，不展示真实用户名、Token、API Key、数据库路径或内部地址。每张图拍摄后再更新“已截图”。

| 编号 | 页面或状态 | 功能说明 | 对应源码 | 已截图 | 敏感信息 | V1.0一致 |
| --- | --- | --- | --- | --- | --- | --- |
| 01 | 登录页 | 展示软件名称和登录入口 | `frontend/src/components/AuthScreen.tsx` | 是 | 使用演示账号 | 是 |
| 02 | 用户注册 | 展示注册字段与校验 | `frontend/src/components/AuthScreen.tsx` | 是 | 使用虚构信息 | 是 |
| 03 | 访客登录后首页 | 展示开箱即用流程 | `frontend/src/App.tsx` | 是 | 使用临时访客 | 是 |
| 04 | 农技问答空状态 | 展示问题引导 | `frontend/src/components/ChatWorkspace.tsx` | 是 | 无 | 是 |
| 05 | 新建农技会话 | 展示会话创建 | `frontend/src/features/chat/useChatController.ts` | 是 | 使用演示标题 | 是 |
| 06 | 农技消息发送中 | 展示乐观消息状态 | `frontend/src/components/ChatWorkspace.tsx` | 是 | 使用虚构问题 | 是 |
| 07 | 演示模式回复 | 明确固定演示回复 | `backend/app/services/assistant.py` | 是 | 不显示 Key | 是 |
| 08 | 会话历史列表 | 展示多会话管理 | `frontend/src/components/Sidebar.tsx` | 是 | 使用演示标题 | 是 |
| 09 | 会话重命名 | 展示重命名操作 | `frontend/src/App.tsx` | 是 | 使用演示标题 | 是 |
| 10 | 会话删除确认 | 展示防误删确认 | `frontend/src/components/ConfirmDialog.tsx` | 是 | 无 | 是 |
| 11 | 长会话历史 | 展示历史消息分页 | `frontend/src/features/chat/useChatController.ts` | 是 | 使用生成内容 | 是 |
| 12 | 发送失败恢复 | 展示输入恢复和错误提示 | `frontend/src/components/ChatWorkspace.tsx` | 是 | 不显示请求详情 | 是 |
| 13 | 图片诊断入口 | 展示图片与描述输入 | `frontend/src/components/VisionWorkspace.tsx` | 是 | 使用无敏感示例图 | 是 |
| 14 | 图片校验提示 | 展示不支持文件提示 | `frontend/src/lib/imageUpload.ts` | 是 | 无 | 是 |
| 15 | 图片初步诊断结果 | 展示初步判断和安全提醒 | `backend/app/services/tools.py` | 是 | 使用演示内容 | 是 |
| 16 | 今日农活输入 | 展示天气、地块和作物阶段 | `frontend/src/components/DecisionWorkspace.tsx` | 是 | 使用虚构条件 | 是 |
| 17 | 今日农活建议 | 展示当日操作建议 | `backend/app/services/decision.py` | 是 | 使用演示内容 | 是 |
| 18 | 用户资料设置 | 展示显示名称和模型偏好 | `frontend/src/App.tsx` | 是 | 使用虚构名称 | 是 |
| 19 | 后端健康检查 | 展示运行模式和就绪状态 | `backend/app/api/routes/system.py` | 是 | 仅显示隔离环境文件名和本地端口 | 是 |
| 20 | 移动端导航 | 展示响应式页面 | `frontend/src/components/Sidebar.tsx` | 是 | 使用临时访客 | 是 |

BYOK 模型设置、Cookie/CSRF 内部细节、PostgreSQL、Docker、管理员后台和计费页面不进入 V1.0 截图。
