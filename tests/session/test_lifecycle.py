import tempfile
import unittest

from web_llm_bridge.providers.base import ProviderDefinition
from web_llm_bridge.artifacts.model import make_artifact_id
from web_llm_bridge.artifacts.store import ArtifactStore
from web_llm_bridge.providers.registry import ProviderRegistry
from web_llm_bridge.session.manager import SessionManager
from web_llm_bridge.session.store import SessionStore


class FakeRegistry:
    def get_provider(self, provider):
        return ProviderDefinition(provider, f"https://{provider}.example/", frozenset({f"{provider}.example"}), {})


class FakeTransport:
    def __init__(self):
        self.calls = []
        self.next_tab = 10
        self.started = False

    async def start(self):
        self.started = True

    async def close(self):
        return None

    async def request(self, method, params, **kwargs):
        self.calls.append((method, params))
        if method == "open":
            self.next_tab += 1
            return {"tab_id": self.next_tab, "url": params["url"]}
        if method == "chat":
            return {"text": "", "artifacts": [{"kind": "image", "turn_id": "turn", "index": 0, "mime_type": "image/png", "quality": "display", "_source": "data:image/png;base64,", "_source_kind": "data"}]}
        if method == "close_tab":
            return {"tab_id": params["tab_id"], "closed": True}
        if method == "get_messages":
            return {"messages": [{"role": "assistant", "content": "answer", "request_id": "hidden", "artifacts": [{"kind": "image", "turn_id": "turn", "index": 0, "mime_type": "image/png", "_source": "data:image/png;base64,AA==", "_source_kind": "data"}]}], "truncated": False, "url": "https://first.example/"}
        raise AssertionError(method)


class SessionLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def _open_legacy_chatgpt(self, current_url: str, requested_url: str) -> tuple[SessionManager, dict, FakeTransport]:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        store = SessionStore(directory.name)
        store.upsert(
            session_id="legacy-chatgpt",
            provider="chatgpt",
            tab_id=10,
            current_url=current_url,
            active=True,
        )
        transport = FakeTransport()
        manager = SessionManager(store, ProviderRegistry(), transport, ArtifactStore(directory.name + "/artifacts"))
        opened = await manager.open(provider="chatgpt", url=requested_url)
        return manager, opened, transport

    async def test_open_matches_legacy_www_chatgpt_session(self):
        manager, opened, transport = await self._open_legacy_chatgpt(
            "https://www.chatgpt.com/c/abc",
            "https://chatgpt.com/c/abc",
        )
        self.assertEqual(opened["session_id"], "legacy-chatgpt")
        self.assertEqual(len(manager.store.list("chatgpt")), 1)
        self.assertEqual(len(transport.calls), 1)

    async def test_open_matches_reverse_chatgpt_host(self):
        _manager, opened, transport = await self._open_legacy_chatgpt(
            "https://chatgpt.com/c/abc",
            "https://www.chatgpt.com/c/abc",
        )
        self.assertEqual(opened["session_id"], "legacy-chatgpt")
        self.assertEqual(len(transport.calls), 1)

    async def test_open_matches_legacy_query_and_trailing_slash(self):
        _manager, opened, transport = await self._open_legacy_chatgpt(
            "https://www.chatgpt.com/c/abc/?model=x",
            "https://chatgpt.com/c/abc",
        )
        self.assertEqual(opened["session_id"], "legacy-chatgpt")
        self.assertEqual(len(transport.calls), 1)

    async def test_open_skips_corrupt_legacy_url(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SessionStore(directory)
            store.upsert(
                session_id="corrupt-session",
                provider="chatgpt",
                tab_id=10,
                current_url="invalid-url",
                active=True,
            )
            transport = FakeTransport()
            manager = SessionManager(store, ProviderRegistry(), transport, ArtifactStore(directory + "/artifacts"))
            opened = await manager.open(provider="chatgpt", url="https://chatgpt.com/c/abc")
            self.assertEqual(store.get("corrupt-session")["current_url"], "invalid-url")

        self.assertNotEqual(opened["session_id"], "corrupt-session")
        self.assertEqual(len(transport.calls), 1)

    async def test_broker_restart_does_not_restore_active_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SessionStore(directory)
            first = SessionManager(store, FakeRegistry(), FakeTransport(), ArtifactStore(directory + "/artifacts"))
            opened = await first.open(provider="first")
            await first.close()
            restarted = SessionManager(store, FakeRegistry(), FakeTransport(), ArtifactStore(directory + "/artifacts"))
            self.assertFalse(restarted.store.get(opened["session_id"], "first")["active"])
            restored = await restarted.open(provider="first", session_id=opened["session_id"])
            self.assertEqual(restored["session_id"], opened["session_id"])

    async def test_close_reopen_forget_and_image_only_chat(self):
        with tempfile.TemporaryDirectory() as directory:
            transport = FakeTransport()
            manager = SessionManager(SessionStore(directory), FakeRegistry(), transport, ArtifactStore(directory + "/artifacts"))
            opened = await manager.open(provider="first", new=True)
            response = await manager.chat("prompt", provider="first", session_id=opened["session_id"])
            self.assertEqual(response["text"], "")
            self.assertEqual(len(response["artifacts"]), 1)
            self.assertEqual(response["artifacts"][0]["id"], make_artifact_id("first", "turn", 0))
            self.assertNotIn("request_id", response)
            closed = await manager.close_session(provider="first", session_id=opened["session_id"])
            self.assertNotIn("active", closed)
            reopened = await manager.open(provider="first", session_id=opened["session_id"])
            self.assertEqual(reopened["session_id"], opened["session_id"])
            history = await manager.get_messages(provider="first", session_id=opened["session_id"])
            self.assertNotIn("request_id", history["messages"][0])
            self.assertNotIn("_source", history["messages"][0]["artifacts"][0])
            forgotten = await manager.forget_session(provider="first", session_id=opened["session_id"])
            self.assertTrue(forgotten["forgotten"])
            self.assertIsNone(manager.store.get(opened["session_id"]))
            self.assertIsNone(SessionStore(directory).get(opened["session_id"]))
            self.assertIn("close_tab", [method for method, _ in transport.calls])
