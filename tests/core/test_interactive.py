import asyncio
import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from web_llm_bridge.cli.interactive import _run
from web_llm_bridge.config import ProjectConfig
from web_llm_bridge.errors import WebLLMBridgeError


class InteractiveCliTests(unittest.TestCase):
    def test_provider_commands_keep_the_current_session_after_an_invalid_choice(self) -> None:
        first_session = SimpleNamespace()
        second_session = SimpleNamespace(chat=AsyncMock(return_value="answer"))
        prompts = iter(["", "/provider", "/provider chatgpt", "/provider missing", "hello", "/sessions", "/quit"])
        output = io.StringIO()
        diagnostics = io.StringIO()
        registry = SimpleNamespace(
            all=lambda: [SimpleNamespace(id="chatgpt")]
        )
        sessions = [
            {"session_id": "other-session", "provider": "other", "current_url": "https://other.example/c/1"},
            {"session_id": "chatgpt-session", "provider": "chatgpt", "current_url": "https://chatgpt.com/c/2"},
        ]

        def resolve(requested, *, config=None) -> str:
            if requested is None:
                self.assertIsNotNone(config)
                return "chatgpt"
            if requested == "missing":
                raise WebLLMBridgeError("不支持的 provider：missing", "PROVIDER_NOT_FOUND")
            return requested

        with patch("web_llm_bridge.cli.interactive.load_project_config", return_value=ProjectConfig()), patch(
            "web_llm_bridge.cli.interactive.resolve_provider", side_effect=resolve
        ), patch("web_llm_bridge.cli.interactive.ProviderRegistry", return_value=registry), patch(
            "web_llm_bridge.cli.interactive.WebLLMSession.open",
            AsyncMock(side_effect=[first_session, second_session]),
        ) as open_session, patch(
            "web_llm_bridge.client.WebLLMClient.list_sessions", AsyncMock(return_value=sessions)
        ), patch("builtins.input", side_effect=lambda _: next(prompts)), redirect_stdout(output), redirect_stderr(diagnostics):
            self.assertEqual(asyncio.run(_run()), 0)

        self.assertEqual(
            [call.kwargs for call in open_session.await_args_list],
            [{"provider": "chatgpt"}, {"provider": "chatgpt"}],
        )
        second_session.chat.assert_awaited_once()
        self.assertEqual(second_session.chat.await_args.args, ("hello",))
        self.assertGreaterEqual(output.getvalue().count("Current provider: chatgpt"), 2)
        self.assertIn("Available providers:", output.getvalue())
        self.assertIn("* chatgpt", output.getvalue())
        self.assertIn("answer", output.getvalue())
        self.assertIn("other-session other https://other.example/c/1", output.getvalue())
        self.assertIn("chatgpt-session chatgpt https://chatgpt.com/c/2", output.getvalue())
        self.assertIn("Error: 不支持的 provider：missing", diagnostics.getvalue())
