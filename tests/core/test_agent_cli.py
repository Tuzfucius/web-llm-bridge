import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import AsyncMock, patch

from web_llm_bridge.cli.agent import main
from web_llm_bridge.errors import WebLLMBridgeError


class AgentCliTests(unittest.TestCase):
    def test_stdin_and_json_emit_success_envelope(self) -> None:
        output = io.StringIO()
        with patch("web_llm_bridge.cli.agent.rpc_call", AsyncMock(return_value={"text": "answer"})), patch("sys.stdin", io.StringIO("question")), redirect_stdout(output):
            self.assertEqual(main(["chat", "--stdin", "--json"]), 0)
        self.assertEqual(json.loads(output.getvalue()), {"ok": True, "result": {"text": "answer"}})

    def test_json_business_error_is_machine_readable(self) -> None:
        output = io.StringIO()
        error = WebLLMBridgeError("状态未知", "CHAT_STATE_UNKNOWN")
        with patch("web_llm_bridge.cli.agent.rpc_call", AsyncMock(side_effect=error)), redirect_stdout(output):
            self.assertNotEqual(main(["chat", "--text", "question", "--json"]), 0)

        payload = json.loads(output.getvalue())
        self.assertEqual(payload["ok"], False)
        self.assertEqual(payload["error"], {"code": "CHAT_STATE_UNKNOWN", "message": "状态未知", "safe_to_retry": False})

    def test_json_unexpected_error_uses_internal_error(self) -> None:
        output = io.StringIO()
        with patch("web_llm_bridge.cli.agent.rpc_call", AsyncMock(side_effect=RuntimeError("boom"))), redirect_stdout(output):
            self.assertEqual(main(["chat", "--text", "question", "--json"]), 1)

        self.assertEqual(
            json.loads(output.getvalue()),
            {"ok": False, "error": {"code": "INTERNAL_ERROR", "message": "boom", "safe_to_retry": False}},
        )

    def test_progress_stays_on_stderr(self) -> None:
        async def fake_rpc_call(method: str, params: dict, *, progress=None, **_: object) -> dict:
            if progress:
                progress({"phase": "thinking"})
            return {"text": "answer"}

        output = io.StringIO()
        diagnostics = io.StringIO()
        with patch("web_llm_bridge.cli.agent.rpc_call", side_effect=fake_rpc_call), patch("sys.stdin", io.StringIO("question")), redirect_stdout(output), redirect_stderr(diagnostics):
            self.assertEqual(main(["chat", "--stdin", "--json"]), 0)

        self.assertEqual(json.loads(output.getvalue()), {"ok": True, "result": {"text": "answer"}})
        self.assertEqual(diagnostics.getvalue(), "[thinking]\n")

    def test_non_json_success_remains_human_readable(self) -> None:
        output = io.StringIO()
        with patch("web_llm_bridge.cli.agent.rpc_call", AsyncMock(return_value={"text": "answer"})), redirect_stdout(output):
            self.assertEqual(main(["chat", "--text", "question"]), 0)
        self.assertEqual(output.getvalue(), "answer\n")

    def test_non_json_error_remains_human_readable(self) -> None:
        output = io.StringIO()
        error = io.StringIO()
        with patch("web_llm_bridge.cli.agent.rpc_call", AsyncMock(side_effect=WebLLMBridgeError("坏请求", "INVALID_ARGUMENT"))), redirect_stdout(output), redirect_stderr(error):
            self.assertEqual(main(["chat", "--text", "question"]), 1)
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(error.getvalue(), "Error: 坏请求\n")

    def test_help_lists_only_public_commands(self) -> None:
        output = io.StringIO()
        with self.assertRaises(SystemExit) as caught, redirect_stdout(output):
            main(["--help"])
        self.assertEqual(caught.exception.code, 0)
        for command in ("open", "chat", "get-messages", "list-sessions", "close-session", "forget-session", "get-artifact"):
            self.assertIn(command, output.getvalue())
        for command in ("debug-snapshot", "debug-trace", "wait-artifact"):
            self.assertNotIn(command, output.getvalue())

    def test_removed_commands_are_argparse_errors(self) -> None:
        diagnostics = io.StringIO()
        with self.assertRaises(SystemExit) as caught, redirect_stderr(diagnostics):
            main(["debug-snapshot"])
        self.assertEqual(caught.exception.code, 2)
        self.assertIn("invalid choice", diagnostics.getvalue())

    def test_session_commands_resolve_the_default_provider(self) -> None:
        cases = [
            (["open"], "open"),
            (["chat", "--text", "question"], "chat"),
            (["get-messages"], "get_messages"),
            (["list-sessions"], "list_sessions"),
            (["close-session", "--session-id", "saved"], "close_session"),
            (["forget-session", "--session-id", "saved"], "forget_session"),
        ]
        for argv, method in cases:
            with self.subTest(command=argv[0]), patch(
                "web_llm_bridge.cli.agent.resolve_provider", return_value="configured"
            ) as resolve, patch(
                "web_llm_bridge.cli.agent.rpc_call", AsyncMock(return_value={})
            ) as rpc:
                self.assertEqual(main(argv), 0)

            resolve.assert_called_once_with(None)
            self.assertEqual(rpc.await_args.args[0], method)
            self.assertEqual(rpc.await_args.args[1]["provider"], "configured")

    def test_open_and_chat_pass_explicit_cli_provider_to_resolver(self) -> None:
        cases = [
            (["open", "--provider", "chatgpt"], "open"),
            (["chat", "--text", "question", "--provider", "chatgpt"], "chat"),
        ]
        for argv, method in cases:
            with self.subTest(command=argv[0]), patch(
                "web_llm_bridge.cli.agent.resolve_provider", return_value="chatgpt"
            ) as resolve, patch(
                "web_llm_bridge.cli.agent.rpc_call", AsyncMock(return_value={})
            ) as rpc:
                self.assertEqual(main(argv), 0)

            resolve.assert_called_once_with("chatgpt")
            self.assertEqual(rpc.await_args.args[0], method)
            self.assertEqual(rpc.await_args.args[1]["provider"], "chatgpt")

    def test_artifact_command_does_not_resolve_provider(self) -> None:
        with patch("web_llm_bridge.cli.agent.resolve_provider") as resolve, patch(
            "web_llm_bridge.cli.agent.rpc_call", AsyncMock(return_value={"id": "artifact"})
        ) as rpc:
            self.assertEqual(main(["get-artifact", "--id", "artifact"]), 0)

        resolve.assert_not_called()
        self.assertEqual(rpc.await_args.args, ("get_artifact", {"artifact_id": "artifact", "output": None}))
