"""人机交互式 Broker 客户端。"""

from __future__ import annotations

import asyncio
import argparse
import sys
from typing import Sequence

from ..config import load_project_config, resolve_provider
from ..errors import WebLLMBridgeError
from ..providers.registry import ProviderRegistry
from ..session.model import WebLLMSession


async def _run() -> int:
    config = load_project_config()
    provider = resolve_provider(None, config=config)
    print("Web LLM Bridge")
    print(f"Provider: {provider}")
    if config.path is None:
        print("Config: built-in default")
    else:
        print(f"Config: {config.path}")

    target = await asyncio.to_thread(input, "Session (Enter to resume, 'new' to create, or URL)> ")
    if target.strip().lower() == "new":
        session = await WebLLMSession.open(provider=provider, new=True)
    elif target.strip():
        session = await WebLLMSession.open(provider=provider, url=target.strip())
    else:
        session = await WebLLMSession.open(provider=provider)

    def progress(event: dict[str, object]) -> None:
        print(f"[{event.get('phase', 'working')}]", file=sys.stderr, flush=True)

    while True:
        text = await asyncio.to_thread(input, "You> ")
        if text.strip() in {"/quit", "/exit"}:
            return 0
        if text.strip() == "/new":
            session = await WebLLMSession.open(provider=provider, new=True)
            continue
        if text.startswith("/open "):
            session = await WebLLMSession.open(provider=provider, url=text.removeprefix("/open ").strip())
            continue
        if text.strip() == "/provider" or text.startswith("/provider "):
            requested = text.removeprefix("/provider").strip()
            if not requested:
                print(f"Current provider: {provider}")
                print("\nAvailable providers:")
                for definition in ProviderRegistry().all():
                    marker = "*" if definition.id == provider else " "
                    print(f"{marker} {definition.id}")
                continue
            try:
                next_provider = resolve_provider(requested)
                # Opening by Provider ID restores that Provider's active session;
                # it does not mutate the session bound to the previous Provider.
                session = await WebLLMSession.open(provider=next_provider)
            except WebLLMBridgeError as exc:
                print(f"Error: {exc}", file=sys.stderr)
                continue
            provider = next_provider
            print(f"Current provider: {provider}")
            continue
        if text.startswith("/history"):
            option = text.removeprefix("/history").strip().lower()
            full = option == "all"
            limit = None if full else (int(option) if option.isdigit() else 5)
            for message in await session.get_messages(limit=limit, full=full):
                print(f"{message['role']}: {message['content']}")
            continue
        if text.strip() == "/sessions":
            from ..client import WebLLMClient
            for item in await WebLLMClient().list_sessions():
                print(f"{item['session_id']} {item['provider']} {item['current_url']}")
            continue
        print(await session.chat(text, progress=progress))


def _parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(
        description="Open an interactive console backed by the local Web LLM Broker.",
        epilog="Management command: web-llm-bridge install --skills",
    )


def main(argv: Sequence[str] | None = None) -> int:
    _parser().parse_args(argv)
    try:
        return asyncio.run(_run())
    except WebLLMBridgeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
