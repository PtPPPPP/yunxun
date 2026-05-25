# 云寻 AI 本地/内网商业 MVP 加固 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `yunxun` 加固成本地/内网可试用的商业 MVP，同时保留现有 FastAPI + React/Vite + SQLite 架构。

**Architecture:** 后端增加运行状态、模型配置识别、启动日志和业务事件日志，仍由 `backend/main.py` 启动并保持现有 API 返回格式。前端只增强状态提示和错误可读性，不重做主界面；README 重写成交付文档，覆盖 Windows 本地和局域网试用流程。

**Tech Stack:** Python 3, FastAPI, SQLite, unittest, React 18, TypeScript, Vite, Axios, lucide-react.

---

## File Structure

- Modify: `backend/app/core/config.py`
  - 负责解析环境变量、识别真实模型 Key、暴露运行配置。
- Create: `backend/app/core/runtime_status.py`
  - 负责生成安全的运行状态和启动日志，不泄露密钥、token、密码或图片内容。
- Create: `backend/app/core/audit.py`
  - 负责结构化业务事件日志和敏感字段脱敏。
- Modify: `backend/app/core/database.py`
  - 负责 SQLite 初始化时的可读错误与日志。
- Modify: `backend/app/main.py`
  - 负责应用初始化时记录运行状态。
- Modify: `backend/app/services/system.py`
  - 负责 `/api/health` 返回更完整但安全的运行状态。
- Modify: `backend/app/services/auth.py`
  - 负责登录、注册、访客登录、退出、资料更新日志。
- Modify: `backend/app/api/routes/auth.py`
  - 负责把退出事件的用户标识传给 service。
- Modify: `backend/app/services/chat.py`
  - 负责聊天请求、模型模式、限流和失败日志。
- Modify: `backend/app/services/tools.py`
  - 负责田间诊断和今日农活日志。
- Create: `backend/tests/test_config_runtime.py`
  - 验证示例 Key 不会被当成真实模型配置，运行状态不会泄露敏感值。
- Create: `backend/tests/test_system_service.py`
  - 验证健康检查包含内网部署需要的信息。
- Create: `backend/tests/test_audit.py`
  - 验证审计日志会脱敏敏感字段。
- Modify: `frontend/src/types.ts`
  - 对齐新的健康检查字段。
- Modify: `frontend/src/App.tsx`
  - 负责把后端状态传给登录页和工作台。
- Modify: `frontend/src/components/AuthScreen.tsx`
  - 负责登录页显示后端地址、运行模式和模型状态。
- Modify: `frontend/src/components/TopBar.tsx`
  - 负责工作台顶部显示模型状态、后端地址和请求限制。
- Modify: `frontend/src/components/VisionWorkspace.tsx`
  - 负责强调演示模式不是实际图像识别。
- Modify: `frontend/src/styles.css`
  - 负责新增状态提示样式，保持当前视觉系统。
- Modify: `README.md`
  - 重写为 Windows 本地/局域网交付文档。
- Modify: `.env.example`
  - 补齐生产内网试用说明和安全注释。
- Modify: `frontend/.env.example`
  - 补齐局域网 API 地址示例。

---

### Task 1: Config And Runtime Status

**Files:**
- Modify: `backend/app/core/config.py`
- Create: `backend/app/core/runtime_status.py`
- Create: `backend/tests/test_config_runtime.py`

- [ ] **Step 1: Write failing tests for model Key detection and runtime status**

Create `backend/tests/test_config_runtime.py`:

```python
import unittest

from backend.app.core.config import Settings, has_real_api_key
from backend.app.core.runtime_status import build_runtime_status


def make_settings(**overrides: object) -> Settings:
    values = {
        "app_name": "云寻 AI",
        "app_version": "4.0.0",
        "environment": "intranet",
        "debug": False,
        "host": "0.0.0.0",
        "port": 8001,
        "backend_url": "http://192.168.1.10:8001",
        "jwt_secret": "change-me-in-production",
        "api_key": "",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "chat_endpoint": "doubao-seed-1-6-250615",
        "vision_endpoint": "doubao-seed-1-6-250615",
        "available_models_raw": "doubao-seed-1-6-250615",
        "database_url": "sqlite:///./backend/yunxun.db",
        "db_path": "D:/Program/vscode/yunxun/backend/yunxun.db",
        "allowed_origins_raw": "http://192.168.1.10:5173",
        "cors_methods_raw": "GET,POST,PATCH,DELETE,OPTIONS",
        "cors_headers_raw": "Authorization,Content-Type",
        "max_message_length": 3000,
        "requests_per_minute": 20,
        "token_hours": 168,
    }
    values.update(overrides)
    return Settings(**values)


class ConfigRuntimeTestCase(unittest.TestCase):
    def test_example_api_key_is_not_treated_as_configured(self) -> None:
        self.assertFalse(has_real_api_key(""))
        self.assertFalse(has_real_api_key("your-doubao-api-key"))
        self.assertFalse(has_real_api_key("change-me"))
        self.assertTrue(has_real_api_key("sk-real-example-value"))

    def test_runtime_status_uses_demo_mode_for_example_key(self) -> None:
        settings = make_settings(api_key="your-doubao-api-key")
        status = build_runtime_status(settings)

        self.assertEqual(status["mode"], "本地演示模式")
        self.assertFalse(status["ai_configured"])
        self.assertEqual(status["model_status"], "未配置真实模型 Key")
        self.assertNotIn("your-doubao-api-key", str(status))

    def test_runtime_status_includes_local_intranet_details(self) -> None:
        settings = make_settings(api_key="sk-real-example-value", jwt_secret="local-secret")
        status = build_runtime_status(settings)

        self.assertEqual(status["mode"], "AI 模式")
        self.assertTrue(status["ai_configured"])
        self.assertEqual(status["environment"], "intranet")
        self.assertEqual(status["backend_url"], "http://192.168.1.10:8001")
        self.assertEqual(status["database_path"], "D:/Program/vscode/yunxun/backend/yunxun.db")
        self.assertEqual(status["allowed_origins"], ["http://192.168.1.10:5173"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python -m unittest backend.tests.test_config_runtime
```

Expected: FAIL because `has_real_api_key` and `backend.app.core.runtime_status` do not exist yet.

- [ ] **Step 3: Implement model Key detection**

In `backend/app/core/config.py`, add this near the parser helpers:

```python
EXAMPLE_API_KEYS = {
    "",
    "your-doubao-api-key",
    "your-api-key",
    "change-me",
    "change-me-in-production",
}


def has_real_api_key(value: str | None) -> bool:
    normalized = (value or "").strip()
    if not normalized:
        return False
    return normalized.lower() not in EXAMPLE_API_KEYS
```

Replace the `Settings.ai_configured` property with:

```python
    @property
    def ai_configured(self) -> bool:
        return bool(has_real_api_key(self.api_key) and self.base_url.strip() and self.chat_endpoint.strip())
```

- [ ] **Step 4: Implement runtime status builder**

Create `backend/app/core/runtime_status.py`:

```python
import logging
from typing import Any

from backend.app.core.config import Settings


def build_runtime_warnings(settings: Settings) -> list[str]:
    warnings: list[str] = []

    if settings.environment != "development" and settings.jwt_secret == "change-me-in-production":
        warnings.append("当前仍使用默认安全密钥，内网试用前建议修改 YUNXUN_JWT_SECRET。")
    if not settings.allowed_origins:
        warnings.append("当前没有配置 CORS 来源，前端可能无法访问后端。")
    if not settings.ai_configured:
        warnings.append("当前未配置真实模型 Key，系统会进入本地演示模式。")

    return warnings


def build_runtime_status(settings: Settings) -> dict[str, Any]:
    return {
        "app_name": settings.app_name,
        "app_version": settings.app_version,
        "environment": settings.environment,
        "debug": settings.debug,
        "host": settings.host,
        "port": settings.port,
        "backend_url": settings.backend_url,
        "mode": "AI 模式" if settings.ai_configured else "本地演示模式",
        "ai_configured": settings.ai_configured,
        "model_status": "已配置真实模型 Key" if settings.ai_configured else "未配置真实模型 Key",
        "available_models": settings.available_models,
        "database_path": settings.db_path,
        "allowed_origins": settings.allowed_origins,
        "max_message_length": settings.max_message_length,
        "requests_per_minute": settings.requests_per_minute,
        "token_hours": settings.token_hours,
        "warnings": build_runtime_warnings(settings),
    }


def log_runtime_status(logger: logging.Logger, settings: Settings) -> None:
    status = build_runtime_status(settings)
    logger.info(
        "Runtime status: environment=%s debug=%s host=%s port=%s mode=%s database=%s origins=%s",
        status["environment"],
        status["debug"],
        status["host"],
        status["port"],
        status["mode"],
        status["database_path"],
        ",".join(status["allowed_origins"]),
    )
    for warning in status["warnings"]:
        logger.warning("Runtime warning: %s", warning)
```

- [ ] **Step 5: Run test to verify it passes**

Run:

```bash
python -m unittest backend.tests.test_config_runtime
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/config.py backend/app/core/runtime_status.py backend/tests/test_config_runtime.py
git commit -m "feat: add safe runtime status"
```

---

### Task 2: Health Payload And Startup Logging

**Files:**
- Modify: `backend/app/services/system.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_system_service.py`

- [ ] **Step 1: Write failing health payload test**

Create `backend/tests/test_system_service.py`:

```python
import unittest
from unittest.mock import patch

from backend.app.core.config import Settings
from backend.app.services import system as system_service


def make_settings(**overrides: object) -> Settings:
    values = {
        "app_name": "云寻 AI",
        "app_version": "4.0.0",
        "environment": "intranet",
        "debug": False,
        "host": "0.0.0.0",
        "port": 8001,
        "backend_url": "http://192.168.1.10:8001",
        "jwt_secret": "local-secret",
        "api_key": "",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "chat_endpoint": "doubao-seed-1-6-250615",
        "vision_endpoint": "doubao-seed-1-6-250615",
        "available_models_raw": "doubao-seed-1-6-250615",
        "database_url": "sqlite:///./backend/yunxun.db",
        "db_path": "D:/Program/vscode/yunxun/backend/yunxun.db",
        "allowed_origins_raw": "http://192.168.1.10:5173",
        "cors_methods_raw": "GET,POST,PATCH,DELETE,OPTIONS",
        "cors_headers_raw": "Authorization,Content-Type",
        "max_message_length": 3000,
        "requests_per_minute": 20,
        "token_hours": 168,
    }
    values.update(overrides)
    return Settings(**values)


class SystemServiceTestCase(unittest.TestCase):
    def test_health_payload_contains_safe_runtime_fields(self) -> None:
        settings = make_settings()
        with patch.object(system_service, "get_settings", return_value=settings):
            payload = system_service.build_health_payload()

        self.assertEqual(payload["mode"], "本地演示模式")
        self.assertEqual(payload["environment"], "intranet")
        self.assertEqual(payload["backend_url"], "http://192.168.1.10:8001")
        self.assertEqual(payload["database_path"], "D:/Program/vscode/yunxun/backend/yunxun.db")
        self.assertEqual(payload["model_status"], "未配置真实模型 Key")
        self.assertEqual(payload["allowed_origins"], ["http://192.168.1.10:5173"])
        self.assertNotIn("api_key", payload)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python -m unittest backend.tests.test_system_service
```

Expected: FAIL because `build_health_payload()` does not yet return `environment`, `database_path`, `model_status`, and `allowed_origins`.

- [ ] **Step 3: Update health payload**

Replace `backend/app/services/system.py` with:

```python
from backend.app.core.config import get_settings
from backend.app.core.runtime_status import build_runtime_status


def build_health_payload() -> dict[str, object]:
    settings = get_settings()
    status = build_runtime_status(settings)
    return {
        "mode": status["mode"],
        "ai_configured": status["ai_configured"],
        "model_status": status["model_status"],
        "environment": status["environment"],
        "backend_url": status["backend_url"],
        "available_models": status["available_models"],
        "max_message_length": status["max_message_length"],
        "requests_per_minute": status["requests_per_minute"],
        "debug": status["debug"],
        "database_path": status["database_path"],
        "allowed_origins": status["allowed_origins"],
        "warnings": status["warnings"],
    }
```

- [ ] **Step 4: Add startup runtime logging**

In `backend/app/main.py`, add:

```python
from backend.app.core.runtime_status import log_runtime_status
```

Inside `create_app()`, after `settings = get_settings()` and before `init_db()`, add:

```python
    log_runtime_status(logger, settings)
```

Keep the existing `logger.info("Application initialized", extra={"host": settings.host, "port": settings.port})` line.

- [ ] **Step 5: Run tests**

Run:

```bash
python -m unittest backend.tests.test_config_runtime backend.tests.test_system_service
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/system.py backend/app/main.py backend/tests/test_system_service.py
git commit -m "feat: expose safe health status"
```

---

### Task 3: Backend Audit Logs And Database Errors

**Files:**
- Create: `backend/app/core/audit.py`
- Modify: `backend/app/core/database.py`
- Modify: `backend/app/services/auth.py`
- Modify: `backend/app/api/routes/auth.py`
- Modify: `backend/app/services/chat.py`
- Modify: `backend/app/services/tools.py`
- Create: `backend/tests/test_audit.py`

- [ ] **Step 1: Write failing audit redaction test**

Create `backend/tests/test_audit.py`:

```python
import logging
import unittest

from backend.app.core.audit import log_event


class AuditLogTestCase(unittest.TestCase):
    def test_log_event_redacts_sensitive_fields(self) -> None:
        logger = logging.getLogger("yunxun.backend.test_audit")
        with self.assertLogs(logger, level="INFO") as captured:
            log_event(
                logger,
                "auth_login_attempt",
                username="demo",
                password="secret-password",
                token="secret-token",
                image_base64="abc123",
                message_length=12,
            )

        output = "\n".join(captured.output)
        self.assertIn("event=auth_login_attempt", output)
        self.assertIn("username=demo", output)
        self.assertIn("message_length=12", output)
        self.assertIn("password=[redacted]", output)
        self.assertIn("token=[redacted]", output)
        self.assertIn("image_base64=[redacted]", output)
        self.assertNotIn("secret-password", output)
        self.assertNotIn("secret-token", output)
        self.assertNotIn("abc123", output)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python -m unittest backend.tests.test_audit
```

Expected: FAIL because `backend.app.core.audit` does not exist.

- [ ] **Step 3: Implement audit logger helper**

Create `backend/app/core/audit.py`:

```python
import logging
from typing import Any


SENSITIVE_FIELDS = {
    "password",
    "password_hash",
    "token",
    "authorization",
    "api_key",
    "image_base64",
}


def _format_value(key: str, value: Any) -> str:
    if key in SENSITIVE_FIELDS:
        return "[redacted]"
    if value is None:
        return "none"
    text = str(value).replace("\n", " ").replace("\r", " ").strip()
    return text[:160]


def log_event(logger: logging.Logger, event: str, **fields: Any) -> None:
    ordered_fields = " ".join(f"{key}={_format_value(key, value)}" for key, value in sorted(fields.items()))
    if ordered_fields:
        logger.info("event=%s %s", event, ordered_fields)
    else:
        logger.info("event=%s", event)
```

- [ ] **Step 4: Add database initialization logging and readable errors**

In `backend/app/core/database.py`, add imports:

```python
import logging
from fastapi import HTTPException
```

Add module logger after imports:

```python
logger = logging.getLogger("yunxun.backend.database")
```

Replace `init_db()` with:

```python
def init_db() -> None:
    db_path = get_db_path()
    try:
        with get_connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    preferred_model TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS auth_tokens (
                    token TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    feature TEXT NOT NULL DEFAULT 'chat',
                    model_name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS chat_messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES chat_sessions(id)
                );
                """
            )
    except OSError as exc:
        logger.exception("SQLite database path is not writable: %s", db_path)
        raise HTTPException(status_code=500, detail=f"数据库路径不可写：{db_path}") from exc
    except sqlite3.Error as exc:
        logger.exception("SQLite initialization failed: %s", db_path)
        raise HTTPException(status_code=500, detail="数据库初始化失败，请检查 SQLite 文件权限。") from exc

    logger.info("SQLite database initialized: %s", db_path)
```

- [ ] **Step 5: Add auth service event logs**

In `backend/app/services/auth.py`, add imports:

```python
import logging
from backend.app.core.audit import log_event
```

Add module logger:

```python
logger = logging.getLogger("yunxun.backend.auth")
```

After successful `create_user(...)` in `register_user`, add:

```python
    log_event(logger, "auth_register_success", user_id=user_record["id"], username=normalized_username)
```

After successful password verification in `login_user`, before issuing token, add:

```python
    log_event(logger, "auth_login_success", user_id=user_record["id"], username=user_record["username"])
```

At the start of `guest_login()`, after `suffix = uuid.uuid4().hex[:8]`, add:

```python
    log_event(logger, "auth_guest_login", guest_suffix=suffix)
```

Change `logout_user` signature from:

```python
def logout_user(authorization: str | None) -> None:
```

to:

```python
def logout_user(authorization: str | None, user_id: str | None = None) -> None:
```

After `delete_auth_token(token)`, add:

```python
    log_event(logger, "auth_logout", user_id=user_id or "unknown")
```

At the end of `update_profile`, before `return public_user(updated_record)`, add:

```python
    log_event(logger, "auth_profile_update", user_id=user_id, preferred_model=normalized_model)
```

- [ ] **Step 6: Pass user ID into logout route**

In `backend/app/api/routes/auth.py`, keep the existing FastAPI import because this file still uses `Depends`:

```python
from fastapi import APIRouter, Depends, Header
```

Replace `logout_api` with:

```python
@router.post("/logout")
async def logout_api(authorization: str | None = Header(default=None)) -> dict[str, str]:
    user_id: str | None = None
    if authorization and authorization.startswith("Bearer "):
        try:
            user_id = get_current_user_from_header(authorization)["id"]
        except Exception:
            user_id = None
    logout_user(authorization, user_id=user_id)
    return success_payload(message="已退出登录。")
```

Add this import:

```python
from backend.app.services.auth import get_current_user_from_header, guest_login, login_user, logout_user, register_user, update_profile
```

- [ ] **Step 7: Add chat and tools event logs**

In `backend/app/services/chat.py`, add imports:

```python
import logging
from backend.app.core.audit import log_event
```

Add module logger:

```python
logger = logging.getLogger("yunxun.backend.chat")
```

In `create_user_session`, after `session_record = create_session(...)`, add:

```python
    log_event(logger, "chat_session_create", user_id=user_id, session_id=session_record["id"], feature=feature.strip(), model_name=normalized_model)
```

In `create_session_message`, after `rate_limiter.check(...)`, add:

```python
    log_event(
        logger,
        "chat_message_request",
        user_id=user["id"],
        session_id=session_id,
        client_host=client_host,
        message_length=len(message_text.strip()),
        ai_configured=settings.ai_configured,
    )
```

After `assistant_message = save_message(session_id, "assistant", reply)`, add:

```python
    log_event(
        logger,
        "chat_message_success",
        user_id=user["id"],
        session_id=session_id,
        model_name=selected_model,
        reply_length=len(reply),
    )
```

In `backend/app/services/tools.py`, add imports:

```python
import logging
from backend.app.core.audit import log_event
```

Add module logger:

```python
logger = logging.getLogger("yunxun.backend.tools")
```

In `create_vision_analysis`, after rate limiting, add:

```python
    log_event(
        logger,
        "vision_request",
        user_id=user_id,
        client_host=client_host,
        crop=normalized_crop,
        image_length=len(image_base64),
        ai_configured=settings.ai_configured,
    )
```

Before returning the demo reply, add:

```python
        log_event(logger, "vision_demo_mode", user_id=user_id, crop=normalized_crop)
```

After successful `reply = create_vision_reply(...)`, add:

```python
        log_event(logger, "vision_success", user_id=user_id, crop=normalized_crop, reply_length=len(reply))
```

In `create_decision_advice`, after rate limiting, add:

```python
    log_event(
        logger,
        "decision_request",
        user_id=user_id,
        client_host=client_host,
        crop=crop,
        stage=stage,
        rain_prob=rain_prob,
        soil_moisture=soil_moisture,
        temperature=temperature,
    )
```

- [ ] **Step 8: Run audit test and existing backend tests**

Run:

```bash
python -m unittest backend.tests.test_audit backend.tests.test_config_runtime backend.tests.test_system_service backend.tests.test_decision_service
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add backend/app/core/audit.py backend/app/core/database.py backend/app/services/auth.py backend/app/api/routes/auth.py backend/app/services/chat.py backend/app/services/tools.py backend/tests/test_audit.py
git commit -m "feat: add backend audit logging"
```

---

### Task 4: Frontend Runtime Status Feedback

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/AuthScreen.tsx`
- Modify: `frontend/src/components/TopBar.tsx`
- Modify: `frontend/src/components/VisionWorkspace.tsx`
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: Update frontend health type**

In `frontend/src/types.ts`, replace `HealthPayload` with:

```ts
export interface HealthPayload {
  success: boolean;
  mode: string;
  ai_configured: boolean;
  model_status: string;
  environment: string;
  backend_url: string;
  available_models: string[];
  max_message_length: number;
  requests_per_minute: number;
  debug: boolean;
  database_path: string;
  allowed_origins: string[];
  warnings: string[];
  error?: string;
}
```

- [ ] **Step 2: Pass full health status into auth and vision UI**

In `frontend/src/components/AuthScreen.tsx`, replace the prop interface fields:

```ts
  backendMode: string;
  backendUrl: string;
```

with:

```ts
  backendMode: string;
  backendUrl: string;
  modelStatus: string;
  environment: string;
  warnings: string[];
```

Replace the destructuring line with:

```ts
  const {
    mode,
    backendMode,
    backendUrl,
    modelStatus,
    environment,
    warnings,
    loading,
    form,
    onModeChange,
    onChange,
    onSubmit,
    onGuestLogin,
  } = props;
```

Replace the `.auth-hero__meta` block with:

```tsx
          <div className="auth-hero__meta">
            <span>运行模式：{backendMode}</span>
            <span>模型状态：{modelStatus}</span>
            <span>环境：{environment}</span>
            <span>后端地址：{backendUrl}</span>
          </div>

          {warnings.length > 0 && (
            <div className="mode-note" role="status">
              {warnings[0]}
            </div>
          )}
```

In `frontend/src/App.tsx`, update the `AuthScreen` props:

```tsx
          backendMode={health.mode}
          backendUrl={health.backend_url || api.defaults.baseURL || ""}
          modelStatus={health.model_status}
          environment={health.environment}
          warnings={health.warnings}
```

When rendering `VisionWorkspace`, add:

```tsx
              modelMode={health.mode}
              aiConfigured={health.ai_configured}
```

- [ ] **Step 3: Update vision props and copy**

In `frontend/src/components/VisionWorkspace.tsx`, add props:

```ts
  modelMode: string;
  aiConfigured: boolean;
```

Update destructuring:

```ts
  const {
    previewUrl,
    crop,
    symptom,
    result,
    modelMode,
    aiConfigured,
    onFileChange,
    onCropChange,
    onSymptomChange,
    onSubmit,
  } = props;
```

Replace the diagnosis result helper paragraph with:

```tsx
            <p>
              当前为{modelMode}。{aiConfigured ? "会调用已配置的视觉模型。" : "此时不会进行真实图片识别，只返回补拍和排查建议。"}
            </p>
```

- [ ] **Step 4: Update top bar status chips**

In `frontend/src/components/TopBar.tsx`, replace the second status chip with:

```tsx
        <div className={health.ai_configured ? "status-chip" : "status-chip status-chip--warning"}>
          <ShieldCheck size={16} />
          <span>{health.model_status}</span>
        </div>
```

Add a backend URL chip after the model count chip:

```tsx
        <div className="status-chip">
          <LineChart size={16} />
          <span>{health.backend_url}</span>
        </div>
```

- [ ] **Step 5: Add CSS for mode warning**

In `frontend/src/styles.css`, after `.status-chip`, add:

```css
.status-chip--warning {
  border-color: rgba(184, 91, 91, 0.2);
  background: rgba(255, 245, 235, 0.96);
  color: #7e4a2f;
}

.mode-note {
  max-width: 620px;
  padding: 12px 14px;
  border: 1px solid rgba(184, 91, 91, 0.18);
  border-radius: var(--radius);
  background: rgba(255, 245, 235, 0.9);
  color: #7e4a2f;
}
```

- [ ] **Step 6: Build frontend**

Run:

```bash
cd frontend
npm run build
```

Expected: PASS with TypeScript and Vite build completing.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/types.ts frontend/src/App.tsx frontend/src/components/AuthScreen.tsx frontend/src/components/TopBar.tsx frontend/src/components/VisionWorkspace.tsx frontend/src/styles.css
git commit -m "feat: show runtime mode in frontend"
```

---

### Task 5: Environment Templates And README

**Files:**
- Modify: `.env.example`
- Modify: `frontend/.env.example`
- Modify: `README.md`

- [ ] **Step 1: Update root environment template**

Replace `.env.example` with:

```env
# 云寻 AI 后端配置
# Windows 本地试用：复制为 .env 后按需修改。

YUNXUN_APP_NAME=云寻 AI
YUNXUN_APP_VERSION=4.0.0
YUNXUN_ENV=development
YUNXUN_DEBUG=false

# 本机访问可保留 0.0.0.0；局域网访问也建议保留 0.0.0.0。
YUNXUN_HOST=0.0.0.0
YUNXUN_PORT=8001
PORT=8001

# 本机使用 http://127.0.0.1:8001。
# 局域网使用后端电脑 IP，例如 http://192.168.1.10:8001。
YUNXUN_BACKEND_URL=http://127.0.0.1:8001

# 当前项目使用数据库保存的 opaque token，不是 JWT。
# 内网试用前请改成一段足够长的随机字符串。
YUNXUN_JWT_SECRET=change-me-in-production
YUNXUN_TOKEN_EXPIRE_HOURS=168

# SQLite 数据库。默认首次启动自动创建。
YUNXUN_DATABASE_URL=sqlite:///./backend/yunxun.db
YUNXUN_DB_PATH=./backend/yunxun.db

# CORS 来源必须包含前端地址。
# 本机示例：http://localhost:5173,http://127.0.0.1:5173
# 局域网示例：http://192.168.1.10:5173,http://192.168.1.20:5173
YUNXUN_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174,http://localhost:4173,http://127.0.0.1:4173
YUNXUN_CORS_METHODS=GET,POST,PATCH,DELETE,OPTIONS
YUNXUN_CORS_HEADERS=Authorization,Content-Type

# API 限制
YUNXUN_MAX_MESSAGE_LENGTH=3000
YUNXUN_REQUESTS_PER_MINUTE=20

# 豆包 / Ark
# 保持 your-doubao-api-key 时会进入本地演示模式。
DOUBAO_API_KEY=your-doubao-api-key
DOUBAO_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
DOUBAO_CHAT_ENDPOINT=doubao-seed-1-6-250615
DOUBAO_VISION_ENDPOINT=doubao-seed-1-6-250615
DOUBAO_AVAILABLE_MODELS=doubao-seed-1-6-250615
```

- [ ] **Step 2: Update frontend environment template**

Replace `frontend/.env.example` with:

```env
# 本机访问
VITE_YUNXUN_API_BASE_URL=http://127.0.0.1:8001

# 局域网访问时改成后端电脑 IP，例如：
# VITE_YUNXUN_API_BASE_URL=http://192.168.1.10:8001
```

- [ ] **Step 3: Replace README with delivery documentation**

Replace `README.md` with:

```markdown
# 云寻 AI

云寻 AI 是一个面向农业场景的本地/内网 AI 工作台，提供农技问答、田间图片初步诊断和今日农活建议。当前版本定位为“本地/内网可试用的商业 MVP”：适合小团队、合作社、农场或基层农技人员在 Windows 电脑和局域网内小规模试用。

## 适用场景

- 农技员整理农户问题和历史沟通记录
- 合作社内部试用农技问答和初步诊断工具
- 农场在内网电脑上部署一个轻量 AI 助手
- 项目演示、客户试用和功能验证

本项目当前不是公网 SaaS，不包含多租户、支付、套餐系统、复杂后台管理和 PostgreSQL 迁移。

## 功能清单

- 智能问答：保存历史会话上下文，支持模型偏好
- 田间诊断：上传作物图片并结合现场描述生成初步建议
- 今日农活：根据作物、生长期、降雨概率、墒情和温度生成当天建议
- 登录注册：支持普通账号和访客账号
- 演示回退：未配置豆包/Ark Key 时仍可体验本地演示流程
- 健康检查：查看运行模式、模型状态、后端地址和请求限制

## 技术架构

- 后端：FastAPI
- 前端：React + Vite + TypeScript
- 数据库：SQLite
- 模型接入：豆包/Ark 兼容 OpenAI SDK
- 默认部署：Windows 本机或局域网

## 目录结构

```text
yunxun/
├─ backend/
│  ├─ app/
│  │  ├─ api/
│  │  ├─ core/
│  │  ├─ services/
│  │  ├─ main.py
│  │  ├─ repositories.py
│  │  └─ schemas.py
│  ├─ tests/
│  ├─ main.py
│  └─ requirements.txt
├─ frontend/
│  ├─ src/
│  ├─ .env.example
│  ├─ package.json
│  └─ vite.config.ts
├─ .env.example
└─ README.md
```

## 环境要求

- Windows 10/11
- Python 3.10 或更高版本
- Node.js 18 或更高版本
- npm

## Windows 本地启动

进入项目目录：

```powershell
cd D:\Program\vscode\yunxun
```

复制环境变量模板：

```powershell
copy .env.example .env
copy frontend\.env.example frontend\.env
```

安装后端依赖：

```powershell
pip install -r backend\requirements.txt
```

启动后端：

```powershell
python backend\main.py
```

后端默认地址：

- http://127.0.0.1:8001
- 健康检查：http://127.0.0.1:8001/api/health
- 接口文档：http://127.0.0.1:8001/docs

安装前端依赖并启动：

```powershell
cd frontend
npm install
npm run dev
```

前端默认地址：

- http://127.0.0.1:5173

## 局域网访问

局域网试用时，后端电脑继续启动：

```powershell
python backend\main.py
```

查看后端电脑的局域网 IP，例如 `192.168.1.10`。然后修改根目录 `.env`：

```env
YUNXUN_HOST=0.0.0.0
YUNXUN_PORT=8001
YUNXUN_BACKEND_URL=http://192.168.1.10:8001
YUNXUN_ALLOWED_ORIGINS=http://192.168.1.10:5173,http://127.0.0.1:5173,http://localhost:5173
```

修改 `frontend/.env`：

```env
VITE_YUNXUN_API_BASE_URL=http://192.168.1.10:8001
```

重启前端后，局域网内其他电脑访问：

```text
http://192.168.1.10:5173
```

如果无法访问，检查 Windows 防火墙是否允许 Python 和 Node.js 使用对应端口。

## 环境变量说明

| 变量 | 说明 |
| --- | --- |
| `YUNXUN_ENV` | 运行环境，默认 `development` |
| `YUNXUN_DEBUG` | 是否启用调试模式 |
| `YUNXUN_HOST` | 后端监听地址，内网通常使用 `0.0.0.0` |
| `YUNXUN_PORT` / `PORT` | 后端端口，默认 `8001` |
| `YUNXUN_BACKEND_URL` | 后端对外访问地址 |
| `YUNXUN_ALLOWED_ORIGINS` | 允许访问后端的前端来源 |
| `YUNXUN_DATABASE_URL` | SQLite 数据库 URL |
| `YUNXUN_DB_PATH` | SQLite 文件路径，优先级高于 URL 推导路径 |
| `YUNXUN_MAX_MESSAGE_LENGTH` | 单次聊天输入最大长度 |
| `YUNXUN_REQUESTS_PER_MINUTE` | 每分钟请求限制 |
| `YUNXUN_TOKEN_EXPIRE_HOURS` | 登录 token 有效小时数 |
| `DOUBAO_API_KEY` | 豆包/Ark API Key |
| `DOUBAO_BASE_URL` | 豆包/Ark API 地址 |
| `DOUBAO_CHAT_ENDPOINT` | 聊天模型名称 |
| `DOUBAO_VISION_ENDPOINT` | 视觉模型名称 |
| `VITE_YUNXUN_API_BASE_URL` | 前端连接的后端地址 |

## SQLite 数据库

默认数据库位置：

```text
backend/yunxun.db
```

首次启动后端时会自动创建数据库和数据表。

备份数据库：

```powershell
copy backend\yunxun.db backup\yunxun-2026-05-23.db
```

恢复数据库：

```powershell
copy backup\yunxun-2026-05-23.db backend\yunxun.db
```

删除并重新初始化：

```powershell
del backend\yunxun.db
python backend\main.py
```

不要把真实 `.db` 文件提交到 Git。

## 豆包 / Ark 配置

在根目录 `.env` 中配置：

```env
DOUBAO_API_KEY=你的真实 API Key
DOUBAO_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
DOUBAO_CHAT_ENDPOINT=doubao-seed-1-6-250615
DOUBAO_VISION_ENDPOINT=doubao-seed-1-6-250615
DOUBAO_AVAILABLE_MODELS=doubao-seed-1-6-250615
```

配置后重启后端，再访问：

```text
http://127.0.0.1:8001/api/health
```

如果 `ai_configured` 为 `true`，说明真实模型调用路径已启用。

## 演示模式说明

当 `DOUBAO_API_KEY` 为空、保留为 `your-doubao-api-key`，或使用明显示例值时，系统进入本地演示模式。

演示模式可以：

- 打开前端
- 注册、登录或访客登录
- 创建会话
- 体验本地固定回复
- 体验田间诊断的补拍建议
- 体验今日农活建议

演示模式不等于真实 AI 识别。演示模式下不会真正分析图片，也不会调用真实模型。

## 最小验证流程

后端语法检查：

```powershell
python -m compileall backend
```

后端测试：

```powershell
python -m unittest backend.tests.test_decision_service
```

前端构建：

```powershell
cd frontend
npm run build
```

运行联通验证：

1. 启动后端：`python backend\main.py`
2. 访问：`http://127.0.0.1:8001/api/health`
3. 启动前端：`cd frontend && npm run dev`
4. 打开：`http://127.0.0.1:5173`
5. 使用访客登录
6. 发送一条聊天消息
7. 上传一张图片测试田间诊断
8. 打开今日农活并生成建议

## 常见问题

### 前端提示 Network Error

检查：

1. 后端是否已启动
2. `frontend/.env` 的 `VITE_YUNXUN_API_BASE_URL` 是否正确
3. 根目录 `.env` 的 `YUNXUN_ALLOWED_ORIGINS` 是否包含前端地址
4. 修改 `.env` 后是否重启了前端

### 后端端口被占用

修改 `.env`：

```env
YUNXUN_PORT=8011
PORT=8011
YUNXUN_BACKEND_URL=http://127.0.0.1:8011
```

同时修改 `frontend/.env`：

```env
VITE_YUNXUN_API_BASE_URL=http://127.0.0.1:8011
```

### 局域网电脑无法访问

检查：

1. 后端是否监听 `0.0.0.0`
2. 前端 API 地址是否使用后端电脑 IP
3. CORS 是否包含前端访问地址
4. Windows 防火墙是否放行端口 `8001` 和 `5173`
5. 两台电脑是否在同一局域网

### 配了 Key 还是演示模式

检查：

1. `.env` 是否在项目根目录
2. `DOUBAO_API_KEY` 是否仍是 `your-doubao-api-key`
3. 修改 `.env` 后是否重启后端
4. `/api/health` 的 `ai_configured` 是否为 `true`

## 商用 MVP 边界

当前版本适合本地/内网小规模试用。AI 诊断只提供初步建议，农药、肥料、剂量和安全间隔期必须以当地农技站、产品标签和监管要求为准。

当前版本不包含：

- 多租户
- 支付和套餐
- 管理员后台
- 完整审计系统
- 公网 HTTPS 部署
- PostgreSQL 高并发数据库方案

## 后续升级建议

- Docker Compose 内网部署包
- PostgreSQL 和迁移工具
- 管理员后台
- 用量统计
- 角色权限
- 公网 HTTPS 部署
- SaaS 计费和租户系统
```

- [ ] **Step 4: Commit**

```bash
git add .env.example frontend/.env.example README.md
git commit -m "docs: rewrite local intranet setup guide"
```

---

### Task 6: Final Verification

**Files:**
- No source changes unless verification exposes a defect.

- [ ] **Step 1: Run backend compile check**

Run:

```bash
python -m compileall backend
```

Expected: command finishes without syntax errors.

- [ ] **Step 2: Run backend tests**

Run:

```bash
python -m unittest backend.tests.test_config_runtime backend.tests.test_system_service backend.tests.test_audit backend.tests.test_decision_service
```

Expected: PASS.

- [ ] **Step 3: Run frontend build**

Run:

```bash
cd frontend
npm run build
```

Expected: PASS.

- [ ] **Step 4: Start backend for smoke test**

Run:

```bash
python backend\main.py
```

Expected: backend starts on configured port and logs runtime status. If port `8001` is occupied, set `YUNXUN_PORT=8011`, `PORT=8011`, and align `frontend/.env`.

- [ ] **Step 5: Check health endpoint**

Run from a second PowerShell window:

```bash
Invoke-RestMethod http://127.0.0.1:8001/api/health
```

Expected: response includes `success=True`, `mode`, `model_status`, `backend_url`, `database_path`, and no API Key.

- [ ] **Step 6: Start frontend for smoke test**

Run:

```bash
cd frontend
npm run dev
```

Expected: frontend starts and prints a local URL such as `http://localhost:5173/`.

- [ ] **Step 7: Browser smoke path**

Open the Vite URL and verify:

- Login page shows backend address, environment, mode, and model status.
- Guest login succeeds.
- Chat workspace loads.
- Sending one chat message returns a reply.
- Vision workspace says whether current mode is real model mode or local demo mode.
- Today task workspace generates a recommendation.

- [ ] **Step 8: Commit any verification fixes**

If no fixes are needed, do not create an empty commit. If a fix is needed:

```bash
git add <changed-files>
git commit -m "fix: resolve MVP verification issue"
```

---

## Self-Review

Spec coverage:

- `.env / .env.example` configuration: Task 5.
- Backend port, frontend API address, CORS: Task 5 and Task 2 health fields.
- Windows local startup: Task 5 README and Task 6 verification.
- LAN access: Task 5 README.
- SQLite initialization, data location, backup, restore: Task 3 database logging and Task 5 README.
- Doubao/Ark API Key: Task 1 detection, Task 2 health, Task 5 README.
- Demo fallback mode: Task 1, Task 2, Task 4, Task 5.
- README says demo mode is not real AI recognition: Task 5.
- Basic logs and errors: Task 3.
- Minimal verification: Task 6.
- Preserve FastAPI + React/Vite and existing response format: all tasks keep routes and payload shape.

Placeholder scan:

- The plan contains no open-ended implementation markers.
- Each code-changing task includes concrete file paths and code snippets.
- Test commands and expected results are listed for each task.

Type consistency:

- `model_status`, `environment`, `backend_url`, `database_path`, `allowed_origins`, and `warnings` are added in backend health payload and frontend `HealthPayload`.
- `VisionWorkspace` receives `modelMode` and `aiConfigured` from `App.tsx`.
- `runtime_status.build_runtime_status()` uses the existing `Settings` dataclass.
