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
        water_condition = "降雨概率或土壤湿度达到偏湿提示条件"
    elif dry:
        water_advice = "早晚小水慢灌，优先保苗保根。"
        fertilizer_advice = "可随水少量追肥，避开中午高温。"
        water_condition = "降雨概率与土壤湿度均达到偏干提示条件"
    else:
        water_advice = "保持现有墒情，今天重点巡田查虫查病。"
        fertilizer_advice = "长势弱的地块可少量补肥，长势正常的不用急着加量。"
        water_condition = "未触发偏湿或偏干提示条件"

    return f"""
**今日建议（水分条件提示）**

仅依据你填写或估计的降雨概率和土壤湿度给出提示，没有自动天气或传感器数据。作物、生长期和气温只作记录，不参与分支判断；这不是综合风险评估或用药依据，实际农事请结合现场情况核对。

1. {water_advice}
2. {fertilizer_advice}
3. 你记录的作物为 {crop}，生长期为“{stage}”；巡田时请核对实际长势。
4. 水分条件：{water_condition}。请自行核对后续天气与田间实际情况。

**用户填写的条件**

- 降雨概率：{rain_prob}%
- 土壤湿度：{soil_moisture}%
- 气温（仅记录）：{temperature:.1f}℃
""".strip()
