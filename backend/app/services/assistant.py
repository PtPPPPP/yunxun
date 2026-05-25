from functools import lru_cache

from fastapi import HTTPException
from openai import OpenAI

from backend.app.core.config import CHAT_SYSTEM_PROMPT, VISION_SYSTEM_PROMPT, get_settings


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
    return OpenAI(api_key=settings.api_key, base_url=settings.base_url, timeout=45)


def create_chat_reply(history: list[dict[str, str]], model_name: str) -> str:
    response = get_client().chat.completions.create(
        model=model_name,
        messages=[{"role": "system", "content": CHAT_SYSTEM_PROMPT}, *history],
        temperature=0.35,
    )
    reply = (response.choices[0].message.content or "").strip()
    if not reply:
        raise HTTPException(status_code=502, detail="这次没有生成有效内容，请换一种说法再试。")
    return reply


def create_vision_reply(image_base64: str, crop: str, symptom: str) -> str:
    settings = get_settings()
    response = get_client().chat.completions.create(
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
    reply = (response.choices[0].message.content or "").strip()
    if not reply:
        raise HTTPException(status_code=502, detail="视觉模型没有返回有效内容。")
    return reply
