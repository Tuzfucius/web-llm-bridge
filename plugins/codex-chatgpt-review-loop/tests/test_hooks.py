import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).parents[1]
HOOKS = ROOT / "hooks"


def run_hook(name, payload):
    result = subprocess.run(
        [sys.executable, str(HOOKS / name)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(result.stdout)


def test_session_start_adds_bridge_context():
    output = run_hook("session_start.py", {"cwd": "C:/workspace"})
    assert output["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    context = output["hookSpecificOutput"]["additionalContext"]
    assert "@@REVIEW_CONTEXT_BEGIN@@" in context
    assert "@@REVIEW_READY@@" in context
    assert "@@WEB_REVIEW_PASS@@" in context
    assert "C:/workspace" in context
    assert "worktree is clean" in context


def test_stop_hook_blocks_review_ready_until_pass():
    assert run_hook("stop_review.py", {"last_assistant_message": "@@REVIEW_READY@@"})["decision"] == "block"
    assert run_hook("stop_review.py", {"last_assistant_message": "@@WEB_REVIEW_PASS@@"}) == {}
    assert run_hook("stop_review.py", {"last_assistant_message": "done"}) == {}
    assert run_hook("stop_review.py", {"last_assistant_message": "@@REVIEW_READY@@", "stop_hook_active": True}) == {}


def test_stop_hook_uses_exact_sentinels_and_pass_has_priority():
    assert run_hook("stop_review.py", {"last_assistant_message": "本轮没有输出 REVIEW_READY，因为测试失败"}) == {}
    assert run_hook("stop_review.py", {"last_assistant_message": "WEB_REVIEW_PASS 只是协议名字"}) == {}
    assert run_hook("stop_review.py", {"last_assistant_message": "由于测试失败，本轮不会使用 @@REVIEW_READY@@ 标记。"}) == {}
    assert run_hook("stop_review.py", {"last_assistant_message": "`@@REVIEW_READY@@`"}) == {}
    assert run_hook("stop_review.py", {"last_assistant_message": "prefix@@REVIEW_READY@@suffix"}) == {}
    assert run_hook("stop_review.py", {"last_assistant_message": "本轮不会输出 @@WEB_REVIEW_PASS@@。"}) == {}
    assert run_hook("stop_review.py", {"last_assistant_message": "summary\n@@REVIEW_READY@@"})["decision"] == "block"
    assert run_hook(
        "stop_review.py",
        {"last_assistant_message": "@@WEB_REVIEW_PASS@@\n@@REVIEW_READY@@"},
    )["decision"] == "block"


def test_stop_hook_requires_marker_at_final_non_empty_line():
    assert run_hook("stop_review.py", {"last_assistant_message": "@@REVIEW_READY@@"})["decision"] == "block"
    assert run_hook("stop_review.py", {"last_assistant_message": "@@REVIEW_READY@@\n\n"})["decision"] == "block"
    assert run_hook("stop_review.py", {"last_assistant_message": "summary\n@@REVIEW_READY@@\nextra text"}) == {}
    assert run_hook("stop_review.py", {"last_assistant_message": "```text\n@@REVIEW_READY@@\n```"}) == {}
    assert run_hook("stop_review.py", {"last_assistant_message": "summary\n@@WEB_REVIEW_PASS@@"}) == {}
    assert run_hook("stop_review.py", {"last_assistant_message": "@@WEB_REVIEW_PASS@@\nextra text"}) == {}
    assert run_hook("stop_review.py", {"last_assistant_message": "```text\n@@WEB_REVIEW_PASS@@\n```"}) == {}


def test_stop_hook_copies_context_into_continuation_reason():
    message = """summary
@@REVIEW_CONTEXT_BEGIN@@
Original task:
fix the feature

Implementation summary:
implemented it

Tests:
pytest -q
@@REVIEW_CONTEXT_END@@
@@REVIEW_READY@@"""
    output = run_hook("stop_review.py", {"last_assistant_message": message})
    assert output["decision"] == "block"
    assert "@@REVIEW_CONTEXT_BEGIN@@" in output["reason"]
    assert "fix the feature" in output["reason"]


def test_hooks_config_uses_plugin_root_commands():
    config = json.loads((HOOKS / "hooks.json").read_text(encoding="utf-8"))
    for event in ("SessionStart", "Stop"):
        hook = config["hooks"][event][0]["hooks"][0]
        assert "${PLUGIN_ROOT}" in hook["command"]
        assert "commandWindows" in hook
        assert "${PLUGIN_ROOT}" in hook["commandWindows"]
        assert not hook["command"].startswith("python hooks/")


def test_plugin_metadata_uses_project_policy_urls_only():
    manifest = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    interface = manifest["interface"]
    assert interface["websiteURL"] == "https://github.com/Tuzfucius/web-llm-bridge"
    assert "privacyPolicyURL" not in interface
    assert "termsOfServiceURL" not in interface
