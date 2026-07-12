import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

from backend.app.services import assistant
from backend.tests.test_chat_service import make_settings
from pathlib import Path


class ModelError(Exception):
    def __init__(self, status_code: int):
        self.status_code = status_code


class AssistantFaultTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = make_settings(Path("fault.db"))

    def test_timeout_is_reported_as_gateway_timeout(self) -> None:
        with patch.object(assistant, "get_settings", return_value=self.settings):
            with self.assertRaises(HTTPException) as raised:
                assistant._run_with_retries(lambda: (_ for _ in ()).throw(TimeoutError()))
        self.assertEqual(raised.exception.status_code, 504)

    def test_model_rate_limit_is_distinct_from_user_rate_limit(self) -> None:
        with patch.object(assistant, "get_settings", return_value=self.settings):
            with self.assertRaises(HTTPException) as raised:
                assistant._run_with_retries(lambda: (_ for _ in ()).throw(ModelError(429)))
        self.assertEqual(raised.exception.status_code, 503)

    def test_model_auth_failure_is_not_retried(self) -> None:
        calls = 0
        def fail():
            nonlocal calls
            calls += 1
            raise ModelError(401)
        with patch.object(assistant, "get_settings", return_value=self.settings):
            with self.assertRaises(HTTPException) as raised:
                assistant._run_with_retries(fail)
        self.assertEqual(raised.exception.status_code, 502)
        self.assertEqual(calls, 1)

    def test_empty_and_invalid_responses_are_rejected(self) -> None:
        empty = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="  "))])
        with self.assertRaises(HTTPException):
            assistant._extract_text_reply(empty, empty_message="empty")
        with self.assertRaises(HTTPException):
            assistant._extract_text_reply(object(), empty_message="empty")
