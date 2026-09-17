# Codex ChatGPT Review Loop

## Current status

This plugin provides a Bridge-backed, bounded ChatGPT code review loop:

```text
Codex -> SessionStart/Stop Hooks -> Skill -> `review_driver.py` -> WebLLMClient -> Broker -> Browser Extension -> ChatGPT Web
```

Implemented:

- `hooks/hooks.json` registering SessionStart and Stop commands.
- Hook scripts that only provide context and make a stop decision; they do not
  communicate with a provider. Hook commands use `${PLUGIN_ROOT}` so their
  paths remain valid when the workspace cwd is another repository.
- `build_review_prompt.py`, `parse_review.py`, `parse_review_context.py`,
  `review_state.py`, and `review_driver.py` for the two-stage PASS/REVISE
  protocol.

This MVP does not perform Codex self-modification in this repository. The
REVISE prompt is handed back to Codex; tests, commits, and pushes remain in the
normal Codex development turn.

## Execution boundary

The Bridge driver is the only supported provider path. Native browser runtime
code is preserved under `experimental/native-browser/` for experiments and is
not registered by the manifest. Native Codex Browser is blocked by host
capability and is not a production path.

## Prerequisites

- The `web-llm-bridge` Python package is importable.
- Browser Extension is installed and the browser is running.
- `chatgpt.com` is already authenticated.

## 中文说明

`codex-chatgpt-review-loop` 是一个由用户显式触发的外部代码审查插件。只有当同一条请求同时包含外部 ChatGPT 审查意图，以及明确的 ChatGPT conversation URL 或 Web LLM Bridge session ID 时，Skill 才会创建 activation 并进入审查流程。普通的编码、修复或泛化的“帮我 review”请求不会启动 Bridge，也不会打开浏览器或复用旧会话。

首次审查会将明确指定的目标交给 Bridge Driver；后续 `REVISE` 回合复用当前 cycle 的状态。activation 仅用于首次授权，不保存浏览器凭据、cookie 或 token。插件的 Stop Hook 始终静态注册，但在未满足 `@@REVIEW_READY@@`、activation marker 和完整 context block 条件时立即返回 `{}`，不会访问 Git、Bridge、浏览器或网络。

## 部署与配置提示

按以下顺序完成本地部署，避免在 Plugin 已安装但 Bridge 未就绪时触发审查失败：

1. 在仓库根目录安装 Python package：`python -m pip install -e .`。
2. 在 Chrome 或 Edge 的扩展管理页启用开发者模式，并加载仓库的 `extension/` 目录；在同一浏览器 profile 中正常登录 `chatgpt.com`。
3. 启动 Broker：`web-llm-broker serve`。需要时可先执行 `review_driver.py smoke --json` 验证 Bridge、Extension 和浏览器连接。
4. 将本插件登记到 Codex 本地 Marketplace。创建或更新 `~/.agents/plugins/marketplace.json`，其中 `path` 应指向本仓库内的插件目录：

```json
{
  "name": "local",
  "interface": {
    "displayName": "Local Plugins"
  },
  "plugins": [
    {
      "name": "codex-chatgpt-review-loop",
      "source": {
        "source": "local",
        "path": "./plugins/codex-chatgpt-review-loop"
      },
      "policy": {
        "installation": "AVAILABLE",
        "authentication": "ON_INSTALL"
      },
      "category": "Developer Tools"
    }
  ]
}
```

5. 安装并确认插件：

```console
codex plugin add codex-chatgpt-review-loop@local
codex plugin list --json
```

安装后请完全退出并重启 Codex。若 `path` 已通过 Windows Junction 映射到仓库，请先确认旧的 Junction 或目录不存在，避免直接覆盖已有安装。

部署完成后，可使用以下形式显式请求审查：

```text
完成这个功能，然后使用 https://chatgpt.com/c/xxxx 进行 ChatGPT 外部审查，有问题继续修复，最多三轮。
```

## Commands and state

Use `review_driver.py smoke --json` for a two-message Bridge connectivity test.
Use `review_driver.py review --json --context-file <temporary-file>` for one
bounded review attempt. The file contains the deterministic
`@@REVIEW_CONTEXT_BEGIN@@`/`@@REVIEW_CONTEXT_END@@` block from the Codex
development turn and must not be stored in a tracked path. State is stored
below `.git/codex-chatgpt-review/state.json`; it contains no cookies or tokens.
Three automatic rounds are allowed per review cycle. PASS followed by a new
commit starts a new cycle. After MAX_ROUNDS, a new cycle requires both a new
original task context and a new committed HEAD.
Each request marker includes repository identity, cycle identity, HEAD SHA, and
round, so identical commits in different cycles cannot collide during recovery.

`--context-file` is mandatory for formal review. The driver also rejects direct
API calls whose `original_task`, `implementation_summary`, or `tests` field is
missing or empty. During an active REVISE cycle, changing `original_task`
returns `REVIEW_CONTEXT_MISMATCH` without sending another request.

The review prompt includes the original task, implementation summary, actual
test results, and the clean `git show HEAD` patch. PASS emits
`@@WEB_REVIEW_PASS@@`; REVISE returns a deterministic Codex prompt for the
next development turn. Repository content is explicitly treated as untrusted
data, and the second-stage Codex prompt is restricted to the current review
findings.

The driver fails closed on unsafe or unknown delivery. It first checks history
for the deterministic request marker and returns `REVIEW_DELIVERY_UNKNOWN`
instead of blindly resending a request it cannot prove was not delivered.

SessionStart injects the lifecycle policy for producing context and
`@@REVIEW_READY@@`. Stop only blocks on a final non-empty line containing that
sentinel; it allows only a final non-empty `@@WEB_REVIEW_PASS@@` line and never
contacts the Bridge. After the initial handoff, the Skill drives subsequent
REVISE rounds directly and never routes them through Stop again. A REVISE at
the maximum round is returned by the Driver as `MAX_ROUNDS_REVISE` without
executing its prompt. Review results for PASS, REVISE, and MAX_ROUNDS_REVISE
always expose the first-stage `review_text` field. It is `null` only when prompt
recovery proves the second-stage prompt but cannot deterministically reconstruct
the first-stage review. For REVISE, the separate `codex_prompt` is returned for
user handling. Unknown prompt
delivery is recovered only from a user request marker in conversation history;
successful prompt recovery restores `last_status=REVISE` and same-SHA calls
return `NO_CODE_CHANGE`.

## Live test status

Unit and protocol tests are local/fake-client tests. A real Bridge smoke or
synthetic ChatGPT protocol test must be run only with the Extension installed
and `chatgpt.com` logged in; this README does not claim that live E2E is done.
