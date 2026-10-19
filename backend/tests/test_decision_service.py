import unittest

from backend.app.services.decision import build_decision_reply


class DecisionServiceTestCase(unittest.TestCase):
    def test_wet_weather_recommends_drainage(self) -> None:
        reply = build_decision_reply("水稻", "分蘖期", 80, 70, 25.0)
        self.assertIn("开沟排水", reply)
        self.assertIn("偏湿提示条件", reply)

    def test_dry_weather_recommends_light_irrigation(self) -> None:
        reply = build_decision_reply("玉米", "苗期", 20, 25, 30.0)
        self.assertIn("早晚小水慢灌", reply)
        self.assertIn("偏干提示条件", reply)

    def test_existing_water_thresholds_and_precedence_are_unchanged(self) -> None:
        for rain, moisture, condition in (
            (60, 0, "降雨概率或土壤湿度达到偏湿提示条件"), (0, 65, "降雨概率或土壤湿度达到偏湿提示条件"),
            (30, 35, "降雨概率与土壤湿度均达到偏干提示条件"), (0, 0, "降雨概率与土壤湿度均达到偏干提示条件"),
            (59, 64, "未触发偏湿或偏干提示条件"),
            (31, 35, "未触发偏湿或偏干提示条件"),
            (30, 36, "未触发偏湿或偏干提示条件"),
        ):
            with self.subTest(rain=rain, moisture=moisture):
                reply = build_decision_reply("玉米", "苗期", rain, moisture, 24.5)
                self.assertIn(f"水分条件：{condition}", reply)

    def test_crop_stage_and_temperature_are_recorded_without_changing_water_branch(self) -> None:
        original = build_decision_reply("玉米", "苗期", 20, 25, -10.0)
        changed = build_decision_reply("番茄", "采收期", 20, 25, 50.0)
        for prefix in ("1. ", "2. ", "4. "):
            first = next(line for line in original.splitlines() if line.startswith(prefix))
            second = next(line for line in changed.splitlines() if line.startswith(prefix))
            self.assertEqual(first, second)
        self.assertIn("番茄", changed)
        self.assertIn("采收期", changed)
        self.assertIn("50.0℃", changed)

    def test_reply_explains_user_input_and_does_not_claim_overall_risk(self) -> None:
        for rain, moisture in ((80, 70), (20, 25), (55, 42)):
            with self.subTest(rain=rain, moisture=moisture):
                reply = build_decision_reply("玉米", "苗期", rain, moisture, 24.5)
                self.assertIn("你填写或估计", reply)
                self.assertIn("没有自动天气或传感器数据", reply)
                self.assertIn("不参与分支判断", reply)
                self.assertIn("不是综合风险评估或用药依据", reply)
                self.assertNotIn("当前风险", reply)
                self.assertIn(f"降雨概率：{rain}%", reply)
                self.assertIn(f"土壤湿度：{moisture}%", reply)


if __name__ == "__main__":
    unittest.main()
