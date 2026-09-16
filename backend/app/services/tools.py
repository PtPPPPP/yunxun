import logging

from backend.app.core.audit import log_event
from backend.app.core.config import get_settings
from backend.app.core.rate_limit import InMemoryRateLimiter
from backend.app.core.security import safe_fingerprint
from backend.app.repositories import create_tool_record
from backend.app.services.decision import build_decision_reply


logger = logging.getLogger("yunxun.backend.tools")
rate_limiter = InMemoryRateLimiter()


def _persist_tool_record_safely(**record: object) -> None:
    """历史记录落库失败只记日志，不影响农活建议主流程。"""
    try:
        create_tool_record(**record)
    except Exception:
        logger.warning("Failed to persist tool record kind=%s", record.get("kind"), exc_info=True)


def create_decision_advice(
    user_id: str,
    client_host: str,
    crop: str,
    stage: str,
    rain_prob: int,
    soil_moisture: int,
    temperature: float,
) -> dict[str, str]:
    settings = get_settings()
    rate_limiter.check(f"decision:{user_id}:{client_host}", settings.requests_per_minute)
    log_event(
        logger,
        "decision_request",
        user_id=user_id,
        client_fingerprint=safe_fingerprint(client_host),
        crop=crop,
        stage=stage,
        rain_prob=rain_prob,
        soil_moisture=soil_moisture,
        temperature=temperature,
    )
    reply = build_decision_reply(
        crop=crop,
        stage=stage,
        rain_prob=rain_prob,
        soil_moisture=soil_moisture,
        temperature=temperature,
    )
    _persist_tool_record_safely(
        user_id=user_id,
        kind="decision",
        crop=crop.strip() or "当前作物",
        payload={
            "stage": stage,
            "rain_prob": rain_prob,
            "soil_moisture": soil_moisture,
            "temperature": temperature,
        },
        result=reply,
        mode="local",
    )
    return {"reply": reply}
