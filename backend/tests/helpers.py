from pathlib import Path

from backend.app.core.config import Settings


def make_settings(db_path: Path) -> Settings:
    """构造一份指向临时数据库的测试配置。"""
    return Settings(
        app_name="yunxun-test",
        app_version="test",
        environment="test",
        debug=False,
        host="127.0.0.1",
        port=8001,
        backend_url="http://127.0.0.1:8001",
        jwt_secret="test-secret",
        database_url=f"sqlite:///{db_path}",
        db_path=str(db_path),
        allowed_origins_raw="http://127.0.0.1:5173",
        cors_methods_raw="GET,POST,PATCH,DELETE,OPTIONS",
        cors_headers_raw="Authorization,Content-Type",
        requests_per_minute=200,
        token_hours=168,
    )
