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


def make_plot(
    user_id: str,
    name: str = "东坡三亩地",
    crop: str = "玉米",
    area_mu: float = 3.5,
    started_on: str | None = "2026-05-12",
) -> dict:
    """建一块地并按需开好第一茬，返回地块行（含 id）。

    作物现在属于茬次而不是地块，所以测试要想让地块有当季作物，就必须建茬。
    """
    from backend.app.repositories import create_plot, create_season

    plot = create_plot(
        user_id=user_id,
        name=name,
        area_mu=area_mu,
        soil_type="壤土",
        irrigation="井灌",
        notes="",
    )
    if crop:
        create_season(
            user_id=user_id,
            plot_id=plot["id"],
            crop=crop,
            started_on=started_on,
            notes="",
        )
    return plot
