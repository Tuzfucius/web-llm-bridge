import json
import tempfile
import unittest
from pathlib import Path

from web_llm_bridge.config import (
    CONFIG_FILENAME,
    ProjectConfig,
    find_project_config,
    load_project_config,
    resolve_provider,
    resolve_provider_selection,
)
from web_llm_bridge.errors import WebLLMBridgeError
from web_llm_bridge.providers.base import ProviderDefinition
from web_llm_bridge.providers.registry import ProviderRegistry


class ProjectConfigTests(unittest.TestCase):
    def test_nearest_config_is_found_by_walking_upward(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nested = root / "one" / "two"
            nested.mkdir(parents=True)
            config = root / CONFIG_FILENAME
            config.write_text('{"version": 1, "default_provider": "chatgpt"}', encoding="utf-8")

            self.assertEqual(find_project_config(nested), config)

    def test_nearest_child_config_overrides_root_default_with_registered_alternate(self) -> None:
        registry = ProviderRegistry()
        registry.register(
            ProviderDefinition("alternate", "https://alternate.example/", frozenset({"alternate.example"}), {})
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            child = root / "child" / "nested"
            child.mkdir(parents=True)
            (root / CONFIG_FILENAME).write_text(
                '{"version": 1, "default_provider": "chatgpt"}', encoding="utf-8"
            )
            child_config = child.parent / CONFIG_FILENAME
            child_config.write_text(
                '{"version": 1, "default_provider": "alternate"}', encoding="utf-8"
            )

            selection = resolve_provider_selection(None, start_dir=child, providers=registry)
            config = load_project_config(child, registry)

        self.assertEqual(selection.provider, "alternate")
        self.assertEqual(selection.source, "project_config")
        self.assertEqual(config.path, child_config)

    def test_no_config_uses_builtin_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = load_project_config(directory)

        self.assertIsNone(config.path)
        self.assertEqual(config.default_provider, "chatgpt")
        self.assertEqual(config.source, "builtin")

    def test_config_is_loaded_and_identifies_its_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / CONFIG_FILENAME
            path.write_text(json.dumps({"version": 1, "default_provider": "chatgpt"}), encoding="utf-8")

            config = load_project_config(directory)

        self.assertEqual(config.path, path)
        self.assertEqual(config.source, str(path))

    def test_schema_validation_rejects_invalid_versions_and_provider_values(self) -> None:
        invalid_values = (
            {"version": True, "default_provider": "chatgpt"},
            {"version": 2, "default_provider": "chatgpt"},
            {"version": 1, "default_provider": ""},
            {"version": 1, "default_provider": " chatgpt "},
            {"version": 1, "default_provider": "chatgpt", "unknown": True},
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / CONFIG_FILENAME
            for value in invalid_values:
                path.write_text(json.dumps(value), encoding="utf-8")
                with self.assertRaisesRegex(WebLLMBridgeError, "项目配置无效") as raised:
                    load_project_config(directory)
                self.assertEqual(raised.exception.code, "INVALID_CONFIG")

    def test_schema_validation_rejects_invalid_json_and_non_object_roots(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / CONFIG_FILENAME
            path.write_text("{", encoding="utf-8")
            with self.assertRaisesRegex(WebLLMBridgeError, "有效 JSON") as raised:
                load_project_config(directory)
            self.assertEqual(raised.exception.code, "INVALID_CONFIG")

            path.write_text("[]", encoding="utf-8")
            with self.assertRaisesRegex(WebLLMBridgeError, "项目配置无效") as raised:
                load_project_config(directory)
            self.assertEqual(raised.exception.code, "INVALID_CONFIG")

    def test_default_provider_is_validated_by_registry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / CONFIG_FILENAME
            path.write_text('{"version": 1, "default_provider": "missing"}', encoding="utf-8")

            with self.assertRaisesRegex(WebLLMBridgeError, "不支持的 provider") as raised:
                load_project_config(directory)

        self.assertEqual(raised.exception.code, "PROVIDER_NOT_FOUND")

    def test_explicit_provider_has_priority_over_project_default(self) -> None:
        registry = ProviderRegistry()
        registry.register(
            ProviderDefinition("alternate", "https://alternate.example/", frozenset({"alternate.example"}), {})
        )
        config = ProjectConfig(Path("project/.web-llm-bridge.json"), 1, "alternate")

        self.assertEqual(resolve_provider("chatgpt", config, providers=registry), "chatgpt")
        selection = resolve_provider_selection("chatgpt", config, providers=registry)
        self.assertEqual(selection.source, "explicit")

    def test_explicit_provider_does_not_parse_project_config(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / CONFIG_FILENAME
            path.write_text("{", encoding="utf-8")

            selection = resolve_provider_selection("chatgpt", start_dir=directory)

        self.assertEqual(selection.provider, "chatgpt")
        self.assertEqual(selection.source, "explicit")

    def test_resolve_provider_loads_config_when_not_passed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / CONFIG_FILENAME
            path.write_text('{"version": 1, "default_provider": "chatgpt"}', encoding="utf-8")

            selection = resolve_provider_selection(None, start_dir=directory)

        self.assertEqual(selection.provider, "chatgpt")
        self.assertEqual(selection.source, "project_config")
