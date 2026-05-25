def build_decision_reply(
    crop: str,
    stage: str,
    rain_prob: int,
    soil_moisture: int,
    temperature: float,
) -> str:
    wet = rain_prob >= 60 or soil_moisture >= 65
    dry = rain_prob <= 30 and soil_moisture <= 35

    if wet:
        water_advice = "今天先不浇水，低洼地块及时开沟排水。"
        fertilizer_advice = "雨前不要大水大肥，等田间能下脚后再少量追肥。"
        risk_level = "偏高"
    elif dry:
        water_advice = "早晚小水慢灌，优先保苗保根。"
        fertilizer_advice = "可随水少量追肥，避开中午高温。"
        risk_level = "中等"
    else:
        water_advice = "保持现有墒情，今天重点巡田查虫查病。"
        fertilizer_advice = "长势弱的地块可少量补肥，长势正常的不用急着加量。"
        risk_level = "较低"

    return f"""
**今日建议**

1. {water_advice}
2. {fertilizer_advice}
3. {crop} 现在处于“{stage}”，建议上午巡田一次，重点看叶片背面、根部和低洼处。
4. 当前风险：**{risk_level}**。未来 24 到 48 小时若有强降雨或高温，及时调整浇水和用药。

**依据**

- 降雨概率：{rain_prob}%
- 土壤湿度：{soil_moisture}%
- 气温：{temperature:.1f}℃
""".strip()
