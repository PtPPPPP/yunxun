# 待人工清理候选

以下内容无法仅凭静态引用安全删除，本轮保留。

| 路径 | 怀疑原因 | 当前引用或价值 | 风险 | 建议 |
| --- | --- | --- | --- | --- |
| `.claude/` | 工具配置目录 | 可能保存项目级协作配置 | 删除会影响其他助手 | 人工确认后再处理 |
| `.mimocode/` | 工具生成目录 | 用途未在源码中说明 | 可能影响外部工具 | 人工确认后再处理 |
| `.qa-project-20260723/` | QA 演练目录 | 可能保存人工验收证据 | 可能包含未归档结果 | 人工查看内容后决定 |
| `docs/superpowers/` | 历史规格和计划 | 可解释既有设计来源 | 当成当前事实会误导 | 保留并标记为历史材料 |
| `graphify-out/.graphify_labels.json` | 可再生成的 Graphify 状态 | 影响现有图标签 | 删除可能降低复现性 | 先保留 |
| `graphify-out/.graphify_learning.json` | Graphify 学习状态 | 用途由 Graphify 管理 | 删除可能丢失反馈 | 先保留 |
| `graphify-out/.vocab.txt` | Graphify 查询词表 | 现有图查询可用 | 删除可能降低查询命中 | 先保留 |

已确认的机器路径文件 `.graphify_python` 和 `.graphify_root` 不属于候选，将从仓库移除并忽略。
