import inspect
import unittest

from backend.app.services import assistant


class AssistantAsyncTestCase(unittest.TestCase):
    def test_live_ai_entrypoints_are_async_to_avoid_blocking_routes(self) -> None:
        self.assertTrue(inspect.iscoroutinefunction(assistant.create_chat_reply))
        self.assertTrue(inspect.iscoroutinefunction(assistant.create_vision_reply))


if __name__ == "__main__":
    unittest.main()
