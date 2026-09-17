import unittest
from unittest.mock import AsyncMock, patch

from web_llm_bridge.session.model import WebLLMSession
from web_llm_bridge.client import WebLLMClient


class SessionModelTests(unittest.IsolatedAsyncioTestCase):
    async def test_session_id_is_sent_to_broker_without_legacy_policy(self) -> None:
        response = {"provider": "chatgpt", "session_id": "saved", "conversation_url": "https://chatgpt.com/c/a"}
        with patch("web_llm_bridge.session.model.rpc_call", AsyncMock(return_value=response)) as rpc:
            session = await WebLLMSession.open(session_id="saved")
        self.assertEqual(session.session_id, "saved")
        self.assertEqual(rpc.await_args.args[1], {"provider": "chatgpt", "new": False, "url": None, "session_id": "saved"})

    async def test_history_public_default_is_none(self) -> None:
        session = WebLLMSession(session_id="saved")
        with patch("web_llm_bridge.session.model.rpc_call", AsyncMock(return_value={"messages": []})) as rpc:
            await session.get_messages()
        self.assertIsNone(rpc.await_args.args[1]["limit"])

    async def test_client_open_does_not_send_legacy_policy(self) -> None:
        client = WebLLMClient()
        with patch.object(
            client,
            "call",
            AsyncMock(return_value={"session_id": "saved"}),
        ) as call:
            await client.open(session_id="saved")
        self.assertNotIn("reopen_on_closed", call.await_args.args[1])

    async def test_session_open_resolves_default_provider_and_persists_it(self) -> None:
        response = {"provider": "broker-value", "session_id": "saved", "conversation_url": "https://configured.example/c/a"}
        with patch("web_llm_bridge.session.model.resolve_provider", return_value="configured") as resolve, patch(
            "web_llm_bridge.session.model.rpc_call", AsyncMock(return_value=response)
        ) as rpc:
            session = await WebLLMSession.open(session_id="saved")

        resolve.assert_called_once_with(None)
        self.assertEqual(rpc.await_args.args[1]["provider"], "configured")
        self.assertEqual(session.provider, "configured")

    async def test_session_operations_use_the_persisted_provider(self) -> None:
        session = WebLLMSession(provider="configured", session_id="saved")
        responses = [
            {"provider": "configured", "session_id": "saved", "text": "answer"},
            {"provider": "configured", "session_id": "saved", "messages": []},
            {"provider": "configured", "session_id": "saved"},
            {"provider": "configured", "session_id": "saved", "forgotten": True},
        ]
        with patch("web_llm_bridge.session.model.resolve_provider") as resolve, patch(
            "web_llm_bridge.session.model.rpc_call", AsyncMock(side_effect=responses)
        ) as rpc:
            await session.chat_result("question")
            await session.get_messages()
            await session.close()
            await session.forget()

        self.assertEqual(
            [call.args[1]["provider"] for call in rpc.await_args_list],
            ["configured", "configured", "configured", "configured"],
        )
        resolve.assert_not_called()

    async def test_session_artifact_request_does_not_resolve_provider(self) -> None:
        session = WebLLMSession(session_id="saved")
        with patch("web_llm_bridge.session.model.resolve_provider") as resolve, patch(
            "web_llm_bridge.session.model.rpc_call", AsyncMock(return_value={"id": "artifact"})
        ) as rpc:
            await session.get_artifact("artifact")

        resolve.assert_not_called()
        self.assertEqual(rpc.await_args.args, ("get_artifact", {"artifact_id": "artifact", "output": None}))


class ClientProviderResolutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_client_resolves_provider_for_every_session_command(self) -> None:
        client = WebLLMClient()
        with patch("web_llm_bridge.client.resolve_provider", return_value="configured") as resolve, patch.object(
            client, "call", AsyncMock(return_value={"sessions": []})
        ) as call:
            await client.open()
            await client.chat("question")
            await client.get_messages()
            await client.list_sessions()
            await client.close_session("saved")
            await client.forget_session("saved")

        self.assertEqual(resolve.call_count, 5)
        self.assertEqual([item.args[1]["provider"] for item in call.await_args_list if "provider" in item.args[1]], ["configured"] * 5)
        self.assertEqual(call.await_args_list[3].args[1], {})

    async def test_client_artifact_request_does_not_resolve_provider(self) -> None:
        client = WebLLMClient()
        with patch("web_llm_bridge.client.resolve_provider") as resolve, patch.object(
            client, "call", AsyncMock(return_value={"id": "artifact"})
        ) as call:
            await client.get_artifact("artifact")

        resolve.assert_not_called()
        self.assertEqual(call.await_args.args, ("get_artifact", {"artifact_id": "artifact", "output": None}))
