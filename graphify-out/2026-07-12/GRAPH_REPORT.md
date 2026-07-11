# Graph Report - yunxun  (2026-07-12)

## Corpus Check
- 84 files · ~34,711 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 691 nodes · 1521 edges · 54 communities (30 shown, 24 thin omitted)
- Extraction: 98% EXTRACTED · 2% INFERRED · 0% AMBIGUOUS · INFERRED: 36 edges (avg confidence: 0.58)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `28059b97`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- App.tsx
- auth.py
- chat.py
- get_settings
- chat.py
- Settings
- Backend Dependency Manifest
- count_source_lines.py
- DatabaseIdempotencyStore
- devDependencies
- InMemoryRateLimiter
- compilerOptions
- validate_image_payload
- compilerOptions
- ConfigParsingTestCase
- DecisionWorkspace.tsx
- VisionWorkspace.tsx
- AssistantAsyncTestCase
- Software Copyright Source Manifest
- tsconfig.json
- __init__.py
- Frontend Application Shell
- AppError
- PageParams
- 云寻智慧农业AI工作台软件
- main.py
- 云寻智慧农业AI工作台软件本地/内网商业 MVP 加固设计
- File Structure
- AGENTS.md
- Q: 如何完成本次前端交互修复、降低 App.tsx 集中度，并选择有价值的后端增强？
- API Base URL Configuration
- playwright.config.ts
- Preserve Existing Architecture
- Yunxun Project Collaboration Rules
- Small Verified Changes
- Sensitive-Safe Audit Logging
- Commercial MVP Final Verification
- Frontend Runtime Status Feedback
- Commercial MVP Local Intranet Implementation Plan
- Safe Runtime Status
- Local and Intranet Trial Scope
- No Large-Scale Rewrite
- Safe Local Observability
- AI Diagnosis Safety Boundary
- Local Demo Mode
- FastAPI React Vite SQLite Architecture
- Local and Intranet Commercial MVP
- Opaque Token Hash Storage

## God Nodes (most connected - your core abstractions)
1. `get_settings()` - 37 edges
2. `get_connection()` - 33 edges
3. `Settings` - 31 edges
4. `success_payload()` - 28 edges
5. `log_event()` - 22 edges
6. `云寻智慧农业AI工作台软件` - 22 edges
7. `AppError` - 21 edges
8. `DatabaseIdempotencyStore` - 20 edges
9. `create_session_message()` - 18 edges
10. `register_user()` - 17 edges

## Surprising Connections (you probably didn't know these)
- `guestLogin()` --references--> `Page`  [EXTRACTED]
  frontend/e2e/chat.spec.ts → backend/app/core/pagination.py
- `Backend Validation` --references--> `Backend Dependency Manifest`  [EXTRACTED]
  .github/workflows/ci.yml → backend/requirements.txt
- `AuthTokenHashingTestCase` --uses--> `Settings`  [INFERRED]
  backend/tests/test_auth_tokens.py → backend/app/core/config.py
- `ChatServiceIntegrationTestCase` --uses--> `Settings`  [INFERRED]
  backend/tests/test_chat_service.py → backend/app/core/config.py
- `DatabaseIdempotencyStoreTestCase` --uses--> `Settings`  [INFERRED]
  backend/tests/test_idempotency.py → backend/app/core/config.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Automated Project Verification** — _github_workflows_ci_backend_validation, _github_workflows_ci_frontend_validation, docs_superpowers_plans_2026_05_23_commercial_mvp_local_intranet_final_verification [INFERRED 0.85]

## Communities (54 total, 24 thin omitted)

### Community 0 - "App.tsx"
Cohesion: 0.07
Nodes (50): App(), DecisionWorkspace, VisionWorkspace, AuthScreen(), AuthScreenProps, ChatWorkspace(), ChatWorkspaceProps, prompts (+42 more)

### Community 1 - "auth.py"
Cohesion: 0.14
Nodes (22): logout_api(), _format_value(), log_event(), Any, Logger, create_token(), hash_auth_token(), hash_password() (+14 more)

### Community 2 - "chat.py"
Cohesion: 0.09
Nodes (44): get_current_user(), auth_me_api(), auth_profile_api(), guest_login_api(), login_api(), register_api(), chat_session_detail_api(), chat_stats_api() (+36 more)

### Community 3 - "get_settings"
Cohesion: 0.12
Nodes (26): _format_bounds(), get_settings(), _getenv(), _parse_bool(), _parse_float(), _parse_int(), _parse_optional_str(), _resolve_database_path() (+18 more)

### Community 4 - "chat.py"
Cohesion: 0.12
Nodes (44): list_chat_sessions_api(), get_connection(), choose_model(), cleanup_expired_tokens(), count_all_sessions(), count_messages_for_user(), count_sessions(), count_sessions_by_feature() (+36 more)

### Community 5 - "Settings"
Cohesion: 0.11
Nodes (13): has_real_api_key(), _normalize_example_key(), _parse_csv(), Settings, build_runtime_status(), build_runtime_warnings(), log_runtime_status(), Any (+5 more)

### Community 6 - "Backend Dependency Manifest"
Cohesion: 0.22
Nodes (9): Backend Validation, CI Workflow, Frontend Validation, Backend Dependency Manifest, FastAPI, OpenAI Python Client, Pydantic, python-dotenv (+1 more)

### Community 7 - "count_source_lines.py"
Cohesion: 0.18
Nodes (22): CopyrightSourceMaterialTests, Namespace, c_like_source_lines(), calculate_statistics(), category_for_path(), collect_source_files(), generate_materials(), is_excluded() (+14 more)

### Community 8 - "DatabaseIdempotencyStore"
Cohesion: 0.08
Nodes (20): _create_auth_tokens_table(), _ensure_auth_tokens_schema(), ensure_parent_dir(), get_db_path(), init_db(), Path, _table_columns(), DatabaseIdempotencyStore (+12 more)

### Community 9 - "devDependencies"
Cohesion: 0.07
Nodes (28): dependencies, axios, lucide-react, react, react-dom, devDependencies, eslint, @eslint/js (+20 more)

### Community 10 - "InMemoryRateLimiter"
Cohesion: 0.16
Nodes (6): InMemoryRateLimiter, RateLimitBucket, RateLimitResult, ManualClock, RateLimitTestCase, TimeProvider

### Community 11 - "compilerOptions"
Cohesion: 0.11
Nodes (17): compilerOptions, allowJs, allowSyntheticDefaultImports, esModuleInterop, forceConsistentCasingInFileNames, isolatedModules, jsx, lib (+9 more)

### Community 12 - "validate_image_payload"
Cohesion: 0.29
Nodes (9): _compact_base64(), _decode_base64(), _detect_mime_type(), _format_bytes(), ImageUploadPolicy, _split_data_url(), validate_image_payload(), ValidatedImagePayload (+1 more)

### Community 13 - "compilerOptions"
Cohesion: 0.25
Nodes (7): compilerOptions, allowSyntheticDefaultImports, composite, module, moduleResolution, skipLibCheck, include

### Community 15 - "DecisionWorkspace.tsx"
Cohesion: 0.40
Nodes (3): crops, DecisionWorkspaceProps, stages

### Community 18 - "Software Copyright Source Manifest"
Cohesion: 0.67
Nodes (3): Software Copyright Source Manifest, Stable Source Selection and Ordering, Software Copyright Source Package

### Community 27 - "AppError"
Cohesion: 0.11
Nodes (23): AppError, duplicate_request(), ErrorCode, forbidden(), idempotency_conflict(), message_empty(), message_too_long(), model_unavailable() (+15 more)

### Community 28 - "PageParams"
Cohesion: 0.11
Nodes (15): build_page(), decode_cursor(), encode_cursor(), Page, PageParams, parse_page_params(), Any, 分页工具。  把“解析页码参数 + 边界裁剪 + 组装分页视图”的零散逻辑收口到这里，避免 在路由和仓储层各自手写 ``offset``/``limit`` 计 (+7 more)

### Community 29 - "云寻智慧农业AI工作台软件"
Cohesion: 0.06
Nodes (35): 1. 复制环境变量模板, 2. 安装后端依赖, 3. 启动后端, 4. 安装并启动前端, Key 已配置但仍然是演示模式, SQLite 数据库, Windows 本地启动（详细）, 云寻智慧农业AI工作台软件 (+27 more)

### Community 30 - "main.py"
Cohesion: 0.19
Nodes (16): error_response(), http_exception_handler(), HTTPException, Request, 构造统一的错误响应。      ``code`` 仅在 ``AppError``（或显式传入）时出现，普通错误载荷保持     ``{"success": Fa, unexpected_exception_handler(), validation_exception_handler(), get_request_id() (+8 more)

### Community 31 - "云寻智慧农业AI工作台软件本地/内网商业 MVP 加固设计"
Cohesion: 0.11
Nodes (18): README 设计, SQLite, 云寻智慧农业AI工作台软件本地/内网商业 MVP 加固设计, 交互提示, 前端设计, 后端设计, 后续升级建议, 启动检查 (+10 more)

### Community 32 - "File Structure"
Cohesion: 0.20
Nodes (9): File Structure, Self-Review, Task 1: Config And Runtime Status, Task 2: Health Payload And Startup Logging, Task 3: Backend Audit Logs And Database Errors, Task 4: Frontend Runtime Status Feedback, Task 5: Environment Templates And README, Task 6: Final Verification (+1 more)

### Community 33 - "AGENTS.md"
Cohesion: 0.40
Nodes (3): 1. 项目目标, 2. 项目入口, 后端

### Community 34 - "Q: 如何完成本次前端交互修复、降低 App.tsx 集中度，并选择有价值的后端增强？"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: 如何完成本次前端交互修复、降低 App.tsx 集中度，并选择有价值的后端增强？, Source Nodes

## Knowledge Gaps
- **148 isolated node(s):** `name`, `private`, `version`, `type`, `dev` (+143 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **24 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Settings` connect `Settings` to `auth.py`, `get_settings`, `chat.py`, `DatabaseIdempotencyStore`, `AppError`?**
  _High betweenness centrality (0.049) - this node is a cross-community bridge._
- **Why does `get_settings()` connect `get_settings` to `auth.py`, `chat.py`, `chat.py`, `Settings`, `DatabaseIdempotencyStore`, `AppError`, `main.py`?**
  _High betweenness centrality (0.043) - this node is a cross-community bridge._
- **Why does `InMemoryRateLimiter` connect `InMemoryRateLimiter` to `chat.py`?**
  _High betweenness centrality (0.024) - this node is a cross-community bridge._
- **Are the 6 inferred relationships involving `Settings` (e.g. with `AuthTokenHashingTestCase` and `ChatServiceIntegrationTestCase`) actually correct?**
  _`Settings` has 6 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `FastAPI` (e.g. with `.setUp()` and `.test_root_reports_backend_is_running()`) actually correct?**
  _`FastAPI` has 2 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Yunxun backend application package.`, `统一异常与错误码体系。  把过去散落在各处的 ``raise HTTPException(detail=...)`` 收敛为一套带稳定 机器可读 ``code``, `稳定的错误码常量。      命名遵循 ``DOMAIN_REASON`` 约定。新增场景时只在这里追加常量，避免     在调用处出现魔法字符串。` to the rest of the system?**
  _167 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `App.tsx` be split into smaller, more focused modules?**
  _Cohesion score 0.06923076923076923 - nodes in this community are weakly interconnected._