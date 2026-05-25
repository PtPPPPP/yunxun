import unittest

from backend.app.services.decision import build_decision_reply


class DecisionServiceTestCase(unittest.TestCase):
    def test_wet_weather_recommends_drainage(self) -> None:
        reply = build_decision_reply("水稻", "分蘖期", 80, 70, 25.0)
        self.assertIn("开沟排水", reply)
        self.assertIn("偏高", reply)

    def test_dry_weather_recommends_light_irrigation(self) -> None:
        reply = build_decision_reply("玉米", "苗期", 20, 25, 30.0)
        self.assertIn("早晚小水慢灌", reply)
        self.assertIn("中等", reply)


if __name__ == "__main__":
    unittest.main()
