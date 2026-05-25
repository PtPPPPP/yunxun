from fastapi import APIRouter, Depends, Request

from backend.app.api.deps import get_current_user
from backend.app.core.exceptions import success_payload
from backend.app.schemas import DecisionRequest, VisionRequest
from backend.app.services.tools import create_decision_advice, create_vision_analysis


router = APIRouter(prefix="/api", tags=["tools"])


@router.post("/vision")
async def vision_api(
    request: VisionRequest,
    http_request: Request,
    user: dict[str, str] = Depends(get_current_user),
) -> dict[str, object]:
    client_host = http_request.client.host if http_request.client else "local"
    payload = create_vision_analysis(
        user_id=user["id"],
        client_host=client_host,
        image_base64=request.image_base64,
        crop=request.crop,
        symptom=request.symptom,
    )
    return success_payload(**payload)


@router.post("/decision")
async def decision_api(
    request: DecisionRequest,
    http_request: Request,
    user: dict[str, str] = Depends(get_current_user),
) -> dict[str, object]:
    client_host = http_request.client.host if http_request.client else "local"
    payload = create_decision_advice(
        user_id=user["id"],
        client_host=client_host,
        crop=request.crop,
        stage=request.stage,
        rain_prob=request.rain_prob,
        soil_moisture=request.soil_moisture,
        temperature=request.temperature,
    )
    return success_payload(**payload)
