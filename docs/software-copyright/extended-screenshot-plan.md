# 云寻 AI 轻量功能扩展截图计划

本清单用于本轮新增功能的软著展示准备，不改变已封存的 V1.0 最终交付材料。截图应来自本地演示模式或 Mock 数据，截图前检查页面中不存在 Token、Cookie、用户 ID、数据库路径、Request ID、API Key 或内部错误详情。

| 编号 | 真实页面或状态 | 对应源码 | 设备 | 验收要点 |
| --- | --- | --- | --- | --- |
| 01 | 登录页访客模式入口 | `frontend/src/components/AuthScreen.tsx` | 桌面 | 软件名称与 V1.0 文案一致 |
| 02 | 智能问答空会话 | `frontend/src/components/ChatWorkspace.tsx` | 桌面 | 新建会话、提示词入口可见 |
| 03 | 已发送问答消息 | `frontend/src/components/ChatWorkspace.tsx` | 桌面 | 用户问题与 AI 回复完整显示 |
| 04 | 历史会话列表 | `frontend/src/components/Sidebar.tsx` | 桌面 | 标题、模型、最近消息可读 |
| 05 | 会话搜索有结果 | `frontend/src/components/Sidebar.tsx` | 桌面 | 中文标题筛选即时生效 |
| 06 | 会话搜索无结果 | `frontend/src/components/Sidebar.tsx` | 桌面 | 明确显示无匹配状态 |
| 07 | 会话置顶状态 | `frontend/src/components/Sidebar.tsx` | 桌面 | 置顶标记与置顶按钮可见 |
| 08 | 置顶会话刷新后排序 | `frontend/src/components/Sidebar.tsx` | 桌面 | 置顶会话仍在顶部 |
| 09 | 重命名和删除入口 | `frontend/src/components/Sidebar.tsx` | 桌面 | 当前会话管理操作可见 |
| 10 | AI 回复复制成功反馈 | `frontend/src/components/ChatWorkspace.tsx` | 桌面 | 仅复制回复正文并显示短反馈 |
| 11 | 当前会话导出格式选择 | `frontend/src/components/ChatWorkspace.tsx` | 桌面 | TXT 与 Markdown 控件可见 |
| 12 | 清空会话确认框 | `frontend/src/components/ConfirmDialog.tsx` | 桌面 | 明确说明保留会话、不支持撤销 |
| 13 | 清空后的空会话 | `frontend/src/components/ChatWorkspace.tsx` | 桌面 | 侧栏仍保留会话，消息为空 |
| 14 | 重新生成加载状态 | `frontend/src/components/ChatWorkspace.tsx` | 桌面 | 按钮禁用且加载状态明确 |
| 15 | 使用帮助弹窗 | `frontend/src/App.tsx` | 桌面 | 只描述当前已实现功能 |
| 16 | 关于软件弹窗 | `frontend/src/App.tsx` | 桌面 | 全称、简称、版本、运行模式来自真实配置 |
| 17 | 图片诊断页面 | `frontend/src/components/VisionWorkspace.tsx` | 桌面 | 上传、作物和症状字段可见 |
| 18 | 今日农活计划页面 | `frontend/src/components/DecisionWorkspace.tsx` | 桌面 | 输入与建议结果区域可见 |
| 19 | 移动端侧栏抽屉 | `frontend/src/components/Sidebar.tsx` | 手机 | 搜索、置顶、帮助入口可操作 |
| 20 | 移动端问答与导出 | `frontend/src/components/ChatWorkspace.tsx` | 手机 | 输入、复制、导出和清空布局不截断 |

每张截图完成后记录：截图文件名、生成日期、演示账号类型、是否经过敏感信息检查、是否与 V1.0 功能范围一致。正式申报材料仍以 `docs/software-copyright/final-delivery/` 中已封存文件为准。
