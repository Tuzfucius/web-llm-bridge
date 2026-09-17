"""项目级 Web LLM Bridge 配置解析。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .errors import WebLLMBridgeError
from .providers.registry import ProviderRegistry


CONFIG_FILENAME = ".web-llm-bridge.json"
CONFIG_VERSION = 1
BUILTIN_DEFAULT_PROVIDER = "chatgpt"


@dataclass(frozen=True)
class ProjectConfig:
    """已验证的项目配置；``path`` 为 ``None`` 时表示使用内置默认值。"""

    path: Path | None = None
    version: int = CONFIG_VERSION
    default_provider: str = BUILTIN_DEFAULT_PROVIDER

    @property
    def source(self) -> str:
        return str(self.path) if self.path is not None else "builtin"


@dataclass(frozen=True)
class ProviderSelection:
    """最终 Provider 及其选择来源。"""

    provider: str
    source: str


def find_project_config(start_dir: Path | str | None = None) -> Path | None:
    """从起始目录向上查找最近的项目配置文件。"""

    current = _start_directory(start_dir)
    while True:
        candidate = current / CONFIG_FILENAME
        if candidate.is_file():
            return candidate
        if current.parent == current:
            return None
        current = current.parent


def load_project_config(
    start_dir: Path | str | None = None,
    providers: ProviderRegistry | None = None,
) -> ProjectConfig:
    """加载并严格校验项目配置。"""

    registry = providers or ProviderRegistry()
    path = find_project_config(start_dir)
    if path is None:
        registry.get_provider(BUILTIN_DEFAULT_PROVIDER)
        return ProjectConfig(None, CONFIG_VERSION, BUILTIN_DEFAULT_PROVIDER)

    value = _read_config(path)
    _validate_schema(value, path)
    default_provider = value["default_provider"]
    # Provider 是否受支持只由注册表定义，避免配置层复制该策略。
    registry.get_provider(default_provider)
    return ProjectConfig(path, value["version"], default_provider)


def resolve_provider(
    explicit_provider: str | None = None,
    config: ProjectConfig | None = None,
    *,
    start_dir: Path | str | None = None,
    providers: ProviderRegistry | None = None,
) -> str:
    """返回显式 Provider 或项目默认 Provider，显式值优先。"""

    return resolve_provider_selection(
        explicit_provider,
        config,
        start_dir=start_dir,
        providers=providers,
    ).provider


def resolve_provider_selection(
    explicit_provider: str | None = None,
    config: ProjectConfig | None = None,
    *,
    start_dir: Path | str | None = None,
    providers: ProviderRegistry | None = None,
) -> ProviderSelection:
    """解析 Provider 并保留来源，供交互界面展示。"""

    registry = providers or ProviderRegistry()
    if explicit_provider is not None:
        if not isinstance(explicit_provider, str) or not explicit_provider.strip():
            raise WebLLMBridgeError("provider 必须是非空字符串", "INVALID_ARGUMENT")
        provider = explicit_provider.strip()
        registry.get_provider(provider)
        return ProviderSelection(provider, "explicit")

    resolved_config = config or load_project_config(start_dir, registry)
    registry.get_provider(resolved_config.default_provider)
    source = "project_config" if resolved_config.path is not None else "builtin"
    return ProviderSelection(resolved_config.default_provider, source)


def _start_directory(start_dir: Path | str | None) -> Path:
    path = Path.cwd() if start_dir is None else Path(start_dir)
    path = path.resolve()
    return path.parent if path.is_file() else path


def _read_config(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise WebLLMBridgeError(f"无法读取项目配置：{path}", "INVALID_CONFIG") from error
    except (UnicodeError, json.JSONDecodeError) as error:
        raise WebLLMBridgeError(f"项目配置不是有效 JSON：{path}", "INVALID_CONFIG") from error


def _validate_schema(value: object, path: Path) -> None:
    if not isinstance(value, dict):
        _invalid_config(path, "根节点必须是对象")
    expected = {"version", "default_provider"}
    if set(value) != expected:
        _invalid_config(path, "必须且只能包含 version 和 default_provider")
    version = value["version"]
    if isinstance(version, bool) or not isinstance(version, int) or version != CONFIG_VERSION:
        _invalid_config(path, f"version 必须是整数 {CONFIG_VERSION}")
    provider = value["default_provider"]
    if not isinstance(provider, str) or not provider.strip():
        _invalid_config(path, "default_provider 必须是非空字符串")
    if provider != provider.strip():
        _invalid_config(path, "default_provider 不能包含首尾空白")


def _invalid_config(path: Path, reason: str) -> None:
    raise WebLLMBridgeError(f"项目配置无效（{path}）：{reason}", "INVALID_CONFIG")
