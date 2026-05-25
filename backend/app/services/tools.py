import logging

from fastapi import HTTPException

from backend.app.core.audit import log_event
from backend.app.core.config import get_settings
from backend.app.services.assistant import build_vision_demo_reply, create_vision_reply
from backend.app.services.chat import rate_limiter
from backend.app.services.decision import build_decision_reply


logger = logging.getLogger("yunxun.backend.tools")


def create_vision_analysis(user_id: str, client_host: str, image_base64: str, crop: str, symptom: str) -> dict[str, str]:
    settings = get_settings()
    rate_limiter.check(f"vision:{user_id}:{client_host}", settings.requests_per_minute)

    normalized_crop = crop.strip() or "当前作物"
    log_event(
        logger,
        "vision_request",
        user_id=user_id,
        client_host=client_host,
        crop=normalized_crop,
        image_length=len(image_base64),
        ai_configured=settings.ai_configured,
    )
    if not settings.ai_configured:
        log_event(logger, "vision_demo_mode", user_id=user_id, crop=normalized_crop)
        return {"reply": build_vision_demo_reply(normalized_crop), "mode": "demo"}

    try:
        reply = create_vision_reply(image_base64, crop, symptom)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail="视觉模型暂时不可用，请稍后再试。") from exc

    log_event(logger, "vision_success", user_id=user_id, crop=normalized_crop, reply_length=len(reply))
    return {"reply": reply, "mode": "live"}


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
        client_host=client_host,
        crop=crop,
        stage=stage,
        rain_prob=rain_prob,
        soil_moisture=soil_moisture,
        temperature=temperature,
    )
    return {
        "reply": build_decision_reply(
            crop=crop,
            stage=stage,
            rain_prob=rain_prob,
            soil_moisture=soil_moisture,
            temperature=temperature,
        )
    }
