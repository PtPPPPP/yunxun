import logging
from functools import lru_cache
from typing import Callable, TypeVar

from fastapi.concurrency import run_in_threadpool
from fastapi import HTTPException
from openai import OpenAI

from backend.app.core.config import CHAT_SYSTEM_PROMPT, VISION_SYSTEM_PROMPT, get_settings


logger = logging.getLogger("yunxun.backend.assistant")
T = TypeVar("T")


def build_local_chat_reply(question: str) -> str:
    lowered = question.lower()
    if any(word in question for word in ["玉米", "苞谷"]):
        return (
            "先看心叶和叶片。如果有虫孔、虫粪，优先怀疑玉米螟或草地贪夜蛾。\n\n"
            "今天先做三件事：\n"
            "1. 连查 5 个点，每点看 20 株，确认虫口密度。\n"
            "2. 重度叶先清掉，田边杂草一并处理。\n"
            "3. 真要用药时，按当地农技站建议、标签剂量和安全间隔期执行。"
        )
    if "水稻" in question or "稻" in question:
        return (
            "水稻发黄先分清是湿害、缺肥还是病害。\n\n"
            "今天先拔一株看根，再拍叶片正反面。如果根发黑发臭，先排水透气；如果只是叶尖黄，优先排查肥水管理。"
        )
    if "小麦" in question or "麦" in question:
        return (
            "小麦返青慢、地里又偏湿时，不建议先猛追肥。\n\n"
            "先排湿，再查叶片有没有锈斑、白粉和条纹。地表能下脚后再少量追肥，会更稳。"
        )
    if any(word in lowered for word in ["price", "market"]) or any(word in question for word in ["价格", "卖粮", "行情"]):
        return (
            "卖粮先别只看一天价格，稳一点的做法是分批卖。\n\n"
            "急用钱的部分先出，剩下的盯 3 到 7 天的价格和天气。仓储条件一般时，先防霉变和虫蛀。"
        )
    return (
        "这个问题我先给稳妥建议：请补充作物、地区、生长期、最近天气，再拍一张清晰近照。\n\n"
        "没有把握前，不建议直接定病定药。今天先把重病株标出来，观察 24 小时有没有继续扩散。"
    )


def build_vision_demo_reply(crop: str) -> str:
    return (
        f"本地演示模式已收到 {crop} 照片，但没有配置 AI Key，暂时不能真正识别图片。\n\n"
        "建议先补拍 3 张照片：整株、发病部位近景、叶片背面。若病斑扩展快，先隔离重病株，暂停盲目混药。"
    )


@lru_cache(maxsize=1)
def get_client() -> OpenAI:
    settings = get_settings()
    if not settings.ai_configured:
        raise HTTPException(status_code=503, detail="AI 服务未配置，请先设置 DOUBAO_API_KEY。")
    return OpenAI(api_key=settings.api_key, base_url=settings.base_url, timeout=settings.ai_timeout_seconds)


async def create_chat_reply(history: list[dict[str, str]], model_name: str) -> str:
    _validate_history(history)
    model = _validate_model_name(model_name)
    return await run_in_threadpool(_create_chat_reply_sync, history, model)


def _create_chat_reply_sync(history: list[dict[str, str]], model_name: str) -> str:
    response = _run_with_retries(
        lambda: get_client().chat.completions.create(
            model=model_name,
            messages=[{"role": "system", "content": CHAT_SYSTEM_PROMPT}, *history],
            temperature=0.35,
        )
    )
    return _extract_text_reply(response, empty_message="这次没有生成有效内容，请换一种说法再试。")


async def create_vision_reply(image_base64: str, crop: str, symptom: str) -> str:
    if not image_base64.strip():
        raise HTTPException(status_code=400, detail="图片内容不能为空。")
    return await run_in_threadpool(_create_vision_reply_sync, image_base64, crop, symptom)


def _create_vision_reply_sync(image_base64: str, crop: str, symptom: str) -> str:
    settings = get_settings()
    response = _run_with_retries(
        lambda: get_client().chat.completions.create(
            model=settings.vision_endpoint,
            messages=[
                {"role": "system", "content": VISION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                f"作物：{crop or '未填写'}\n"
                                f"农户描述：{symptom or '未填写'}\n"
                                "请分析这张作物照片，给出初步诊断和处理建议。"
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"},
                        },
                    ],
                },
            ],
            temperature=0.2,
        )
    )
    return _extract_text_reply(response, empty_message="视觉模型没有返回有效内容。")


def _run_with_retries(operation: Callable[[], T]) -> T:
    settings = get_settings()
    attempts = settings.ai_max_retries + 1
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except HTTPException:
            raise
        except Exception as exc:
            last_error = exc
            logger.warning("AI request failed on attempt %s/%s: %s", attempt, attempts, type(exc).__name__)
            status = getattr(exc, "status_code", None)
            if status in {401, 403}:
                raise HTTPException(status_code=502, detail="模型服务鉴权失败，请检查服务端配置。") from exc

    if isinstance(last_error, TimeoutError) or "timeout" in type(last_error).__name__.lower():
        raise HTTPException(status_code=504, detail="模型服务响应超时，请稍后重试。") from last_error
    if getattr(last_error, "status_code", None) == 429:
        raise HTTPException(status_code=503, detail="模型服务当前繁忙，请稍后重试。") from last_error
    raise HTTPException(status_code=502, detail="模型服务暂时不可用，请稍后重试。") from last_error


def _validate_history(history: list[dict[str, str]]) -> None:
    if not history:
        raise HTTPException(status_code=400, detail="对话历史不能为空。")
    for item in history:
        role = item.get("role", "")
        content = item.get("content", "")
        if role not in {"user", "assistant", "system"}:
            raise HTTPException(status_code=400, detail="对话角色格式不正确。")
        if not content.strip():
            raise HTTPException(status_code=400, detail="对话内容不能为空。")


def _validate_model_name(model_name: str) -> str:
    normalized = model_name.strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="模型名称不能为空。")
    if len(normalized) > 128:
        raise HTTPException(status_code=400, detail="模型名称过长。")
    return normalized


def _extract_text_reply(response: object, *, empty_message: str) -> str:
    try:
        choices = getattr(response, "choices")
        first_choice = choices[0]
        message = getattr(first_choice, "message")
        content = getattr(message, "content")
    except (AttributeError, IndexError, TypeError) as exc:
        logger.warning("Invalid AI response shape: %s", type(response).__name__)
        raise HTTPException(status_code=502, detail="模型返回格式不正确。") from exc

    reply = (content or "").strip()
    if not reply:
        raise HTTPException(status_code=502, detail=empty_message)
    return reply
