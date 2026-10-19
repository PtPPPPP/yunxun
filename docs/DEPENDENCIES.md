# 后端依赖与配置维护

## 支持目标与安装

后端目标为 CPython 3.11 和 3.14，CI 的 Ubuntu 后端矩阵覆盖两者，E2E 和发布 CI 使用 3.11。Windows 为当前单机部署范围；实际完成的平台验证见 [本轮记录](audits/2026-10-19/依赖与配置清理验证.md)。不能将 CI 配置等同于已经执行成功的 CI，也不把两个版本的结果扩展为其他 Python 版本已通过。

在所选解释器创建的全新 venv 中，从项目根目录执行：

```powershell
# 运行部署
python -m pip install -r backend/requirements.txt
python -m pip check

# 开发或完整后端测试，已包含运行依赖
python -m pip install -r backend/requirements-test.txt
python -m unittest
```

两份清单自动读取相邻的 `backend/constraints.txt`，从其他工作目录调用 `-r` 同样有效。运行直接依赖只有 FastAPI、Pydantic、python-dotenv、Uvicorn；测试额外需要 httpx（TestClient 和真实服务并发测试），unittest 是标准库。SQLite、密码散列及数据库备份/迁移均由标准库实现。

历史审计复现脚本中使用 httpx 或 TestClient 的入口同样需要测试清单；原报告和快照里的旧安装命令不作为当前依赖入口。

SQLAlchemy、Alembic、psycopg[binary]、redis 在业务、脚本、测试、CI 和发布流程中无接入，已从运行声明移除；不为保留旧声明增加数据库或缓存架构。历史审计、验收 JSON 和软著归档中的旧版本清单保留原样。

## 版本约束与升级

`requirements*.txt` 表达直接依赖范围；`constraints.txt` 固定直接依赖及传递依赖的精确版本。constraints 只约束版本，不主动安装包，因此其中的 httpx 及其测试依赖不会被运行清单额外安装。语义依据：[pip constraints 文档](https://pip.pypa.io/en/stable/user_guide/#constraints-files)。

版本集合以 Python 3.11 的全新解析为基础，在 3.14 新环境独立安装复核，不复制已有 3.14 环境的 freeze。解释器/平台条件由包自身元数据和环境标记决定；若后续出现版本必须分支的传递依赖，应添加明确的 Python/平台 marker 并分别验证，不能靠不受约束的 fallback。

这是版本级的可复现约束，不是覆盖任意解释器、系统架构的二进制制品锁；不包括 Python/pip 安装器、审计工具、源码构建工具链或 wheel 哈希。验证平台使用 wheel 安装；未验证的平台不能据此宣称部署已验收。

受控升级步骤：

1. 保留当前清单与验证结果，先检查目标包元数据的 `Requires-Python`、依赖范围及公告；调整对应直接依赖范围和 constraints 精确版本，检查是否必须同步更新传递依赖。
2. 分别创建 3.11/3.14 新 venv，使用 `python -m pip install --dry-run --ignore-installed --report resolved.json -r backend/requirements-test.txt` 检查解析，再实际安装和 `pip check`。报告为临时验证产物，不将本机整个环境 freeze 写成部署锁。
3. 核对安装集合均受约束；执行完整后端测试、运行依赖独立启动、E2E、发布检查和依赖扫描。只有实际通过后才更新验证记录。
4. 发布包携带三份依赖文件；Manifest 的 `backend_dependency_hashes` 同时记录它们，旧 `backend_dependency_hash` 仍保留。

## 依赖扫描

审计器单独装在工具 venv，当前 CI 使用 `pip-audit==2.10.1`，不把它混入运行或测试依赖。以下命令在该工具环境执行：

```powershell
python -m pip_audit -r backend/requirements.txt
python -m pip_audit -r backend/requirements-test.txt
# Windows：再扫描目标新环境的真实安装集合；Linux 对应 lib/python3.x/site-packages
python -m pip_audit --path C:/path/to/new-venv/Lib/site-packages
```

运行与测试清单都应用同一 constraints。要求解析扫描和真实安装集合扫描都记录结果；工具安装失败、漏洞库不可达或被跳过均不能算扫描通过。

## 旧超时配置

`YUNXUN_REQUEST_TIMEOUT_SECONDS` 过去只被解析并放入内部运行摘要，没有设置 ASGI/HTTP 请求截止，也没有取消 SQLite 操作。已从 Settings、解析、摘要和 `.env.example` 删除，独占使用的 `_parse_float` 也已移除。

兼容处理：已有 `.env` 或部署环境残留该变量时直接忽略，包括空值、负数和非数字；不再因此启动失败，不再展示不存在的超时保证，建议部署者下次维护时删除旧项。公开健康接口原本就没有返回该字段。

前端 `src/lib/api.ts` 的 45 秒 HTTP 客户端超时仍实际生效，与该环境变量无关；SQLite 的 10 秒 busy timeout 也保持原样。客户端停止等待不等于服务端事务已取消，不增加通用超时或事务中断系统。
