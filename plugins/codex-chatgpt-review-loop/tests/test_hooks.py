import importlib.util
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).parents[1]
HOOKS = ROOT / "hooks"
SCRIPTS = ROOT / "skills" / "chatgpt-review-loop" / "scripts"


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


def make_repo(tmp_path: Path) -> Path:
    git(tmp_path, "init")
    git(tmp_path, "config", "user.email", "test@example.invalid")
    git(tmp_path, "config", "user.name", "Test")
    return tmp_path


def run_hook(name, payload):
    result = subprocess.run(
        [sys.executable, str(HOOKS / name)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(result.stdout)


def review_message(activation_id: str, *, task: str = "fix the feature") -> str:
    return f"""summary
@@REVIEW_ACTIVATION={activation_id}@@
@@REVIEW_CONTEXT_BEGIN@@
Original task:
{task}

Implementation summary:
implemented it

Tests:
pytest -q
@@REVIEW_CONTEXT_END@@
@@REVIEW_READY@@"""


def arm(repo: Path, *, task: str = "fix the feature"):
    return load("review_activation").arm(
        repo, task=task, conversation_url="https://chatgpt.com/c/test"
    )


def test_stop_hook_noops_without_review_ready(tmp_path):
    repo = make_repo(tmp_path)
    assert run_hook("stop_review.py", {"cwd": str(repo), "last_assistant_message": "done"}) == {}


def test_stop_hook_noops_for_review_ready_without_activation(tmp_path):
    repo = make_repo(tmp_path)
    assert run_hook("stop_review.py", {"cwd": str(repo), "last_assistant_message": "@@REVIEW_READY@@"}) == {}


def test_stop_hook_noops_for_unknown_activation_id(tmp_path):
    repo = make_repo(tmp_path)
    armed = arm(repo)
    unknown = "00000000-0000-4000-8000-000000000000"
    assert unknown != armed["activation_id"]
    assert run_hook("stop_review.py", {"cwd": str(repo), "last_assistant_message": review_message(unknown)}) == {}


def test_stop_hook_blocks_only_matching_armed_activation(tmp_path):
    repo = make_repo(tmp_path)
    activation = arm(repo)
    output = run_hook(
        "stop_review.py",
        {"cwd": str(repo), "last_assistant_message": review_message(activation["activation_id"])},
    )
    assert output["decision"] == "block"
    assert "chatgpt-review-loop Skill" in output["reason"]
    assert activation["activation_id"] in output["reason"]
    assert "conversation_url=https://chatgpt.com/c/test" in output["reason"]
    assert "fix the feature" in output["reason"]


def test_stop_hook_marker_and_context_fail_closed(tmp_path):
    repo = make_repo(tmp_path)
    activation = arm(repo)
    marker = activation["activation_id"]
    cases = [
        review_message(marker) + f"\n@@REVIEW_ACTIVATION={marker}@@",
        review_message(marker).replace(f"@@REVIEW_ACTIVATION={marker}@@", "@@REVIEW_ACTIVATION=@@"),
        review_message(marker).replace(f"@@REVIEW_ACTIVATION={marker}@@", f"```text\n@@REVIEW_ACTIVATION={marker}@@\n```"),
        review_message(marker).replace(f"@@REVIEW_ACTIVATION={marker}@@", f"prefix @@REVIEW_ACTIVATION={marker}@@"),
        review_message(marker).replace("@@REVIEW_CONTEXT_END@@", ""),
        review_message(marker).replace("@@REVIEW_CONTEXT_BEGIN@@", "@@REVIEW_CONTEXT_BEGIN@@\n@@REVIEW_CONTEXT_BEGIN@@"),
    ]
    for message in cases:
        assert run_hook("stop_review.py", {"cwd": str(repo), "last_assistant_message": message}) == {}


def test_stop_hook_requires_matching_original_task_hash(tmp_path):
    repo = make_repo(tmp_path)
    activation = arm(repo, task="original task")
    assert run_hook(
        "stop_review.py",
        {"cwd": str(repo), "last_assistant_message": review_message(activation["activation_id"], task="changed task")},
    ) == {}


def test_hooks_config_registers_only_stop_hook():
    config = json.loads((HOOKS / "hooks.json").read_text(encoding="utf-8"))
    assert set(config["hooks"]) == {"Stop"}
    hook = config["hooks"]["Stop"][0]["hooks"][0]
    assert "${PLUGIN_ROOT}" in hook["command"]
    assert "${PLUGIN_ROOT}" in hook["commandWindows"]


def test_plugin_metadata_uses_project_policy_urls_only():
    manifest = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    interface = manifest["interface"]
    assert interface["websiteURL"] == "https://github.com/Tuzfucius/web-llm-bridge"
    assert "automatic review lifecycle" not in interface["longDescription"]
    assert "privacyPolicyURL" not in interface
    assert "termsOfServiceURL" not in interface
