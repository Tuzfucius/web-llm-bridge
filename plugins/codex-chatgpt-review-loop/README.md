# Codex ChatGPT Review Loop

## English

This plugin is **user-invoked**, not an automatic review lifecycle. Installing
it does not make ordinary Codex coding tasks produce review markers or contact
ChatGPT.

The loop is activated only when one user request contains both:

- an explicit request for external review through ChatGPT/Web LLM Bridge; and
- exactly one explicit target: a ChatGPT conversation URL or a Web LLM Bridge
  session ID.

Valid examples:

```text
Complete this feature, then use https://chatgpt.com/c/xxxx for ChatGPT external review. Continue fixing issues until PASS.
```

```text
After implementation, use Bridge session abc123 for external review.
```

These are not enough to activate the plugin:

```text
Fix this bug.
Review it after implementation.
Let ChatGPT take a look after implementation.
```

When the target is missing, the Skill asks for a conversation URL or session
ID. It does not create a new ChatGPT conversation and does not reuse a target
from a previous completed cycle.

### Hooks

The production `hooks/hooks.json` registers only the static `Stop` hook.
`SessionStart` is not registered. The legacy `hooks/session_start.py` remains
available for experiments but is never injected by default.

The Stop hook is a lightweight fail-closed gate. It immediately returns `{}`
unless the final non-empty line is `@@REVIEW_READY@@` and the message includes
one valid activation marker and one complete context block. `@@REVIEW_READY@@`
alone never triggers a review. The hook performs no network, browser, Bridge,
or Git work.

### Activation

The Skill arms a repository-local authorization file:

```text
.git/codex-chatgpt-review/activation.json
```

Example commands:

```bash
python plugins/codex-chatgpt-review-loop/skills/chatgpt-review-loop/scripts/review_activation.py arm \
  --conversation-url "https://chatgpt.com/c/xxxx" \
  --task-file original-task.txt

python plugins/codex-chatgpt-review-loop/skills/chatgpt-review-loop/scripts/review_activation.py arm \
  --session-id "abc123" \
  --task-file original-task.txt
```

The URL and session ID options are mutually exclusive. Activation contains no
credentials or browser information:

```json
{
  "version": 1,
  "activation_id": "<uuid>",
  "target_kind": "conversation_url",
  "target_value": "https://chatgpt.com/c/xxxx",
  "task_hash": "<normalized original task hash>",
  "armed": true
}
```

`arm`, `status`, `consume`, and `clear` use atomic writes and fail closed on
invalid JSON, unknown versions, or invalid target combinations. Activation is
cleared after the first review successfully binds its target, and is also
cleared on PASS, MAX_ROUNDS, terminal protocol failure, or user cancellation.
An uncertain delivery result remains recoverable.

### Review command and target binding

The Skill passes the target explicitly to the driver:

```bash
python plugins/codex-chatgpt-review-loop/skills/chatgpt-review-loop/scripts/review_driver.py review \
  --json \
  --context-file <temporary-context-file> \
  --conversation-url "https://chatgpt.com/c/xxxx"
```

Use `--session-id` instead for a Bridge session. A new cycle without either
option returns `REVIEW_TARGET_REQUIRED` without calling `client.open` or
`client.chat`. A URL is opened with `client.open(provider="chatgpt", url=...)`;
a session ID uses `client.open(provider="chatgpt", session_id=...)`. The
resolved target is stored in the existing review state (version 2). Active
REVISE/recovery cycles reuse that state target, while completed cycles never
inherit it. The formal review path never falls back to `new=True`.

The existing state machine is unchanged: `PASS`, `REVISE`,
`MAX_ROUNDS_REVISE`, `MAX_ROUNDS`, `NO_CODE_CHANGE`,
`REVIEW_DELIVERY_UNKNOWN`, and `PROTOCOL_ERROR`, with `MAX_ROUNDS = 3` and
at-most-once recovery semantics.

### Installation and prerequisites

The Web LLM Bridge Python package, browser extension, running browser, and an
authenticated `chatgpt.com` page are required only when an explicit review is
requested. Install the plugin through the repository marketplace as described
in the root project documentation, then start a new Codex task/thread.

## 中文

本插件是**用户显式调用**的外部审查工具，不是全局自动审查生命周期。安装
后，普通的“修复 bug”“实现功能”“重构代码”任务不会注入 Review 标记，也不会
联系 ChatGPT。

只有同一条用户请求同时满足以下条件才会激活：

1. 明确要求通过 ChatGPT 或 Web LLM Bridge 进行外部代码审查；
2. 明确提供且仅提供一个目标：ChatGPT conversation URL，或 Web LLM Bridge
   session ID。

例如：

```text
完成这个功能，然后使用 https://chatgpt.com/c/xxxx 进行 ChatGPT 外部 Review，有问题就继续修复，直到 PASS。
```

```text
完成后使用 Bridge session abc123 做外部审查。
```

只说“完成后帮我 review”或“完成后让 ChatGPT 看一下”都不够。缺少 target
时，Skill 必须要求用户提供 URL 或 session ID，不得自动打开新页面、复用旧
review session、arm activation 或运行 Driver。

正式 `hooks.json` 只注册 Stop Hook，不再注册 SessionStart。Stop Hook 默认
立即 no-op；只有最终非空行是 `@@REVIEW_READY@@`，并且存在唯一且匹配的
activation marker 和完整 context 时才允许 block。单独的 `@@REVIEW_READY@@`
永远不会触发审查，Hook 也不会进行网络、浏览器、Bridge 或 Git 操作。

Activation 位于 `.git/codex-chatgpt-review/activation.json`，与现有
`state.json` version 2 分开管理。Skill 先解析显式 target 并执行
`review_activation.py arm`，开发、测试、commit 完成后输出：

```text
@@REVIEW_ACTIVATION=<activation_id>@@
@@REVIEW_CONTEXT_BEGIN@@
Original task:
...
Implementation summary:
...
Tests:
...
@@REVIEW_CONTEXT_END@@
@@REVIEW_READY@@
```

Driver 必须显式接收 `--conversation-url` 或 `--session-id`。缺少 target 的
新 cycle 返回 `REVIEW_TARGET_REQUIRED`，且不调用 Bridge。首次绑定成功后保存
resolved target，并清除 activation；active REVISE/recovery 继续复用当前 cycle
的 target。PASS、MAX_ROUNDS、terminal protocol failure 或取消时清理；完成的
旧 cycle 不会成为新任务的默认 target。正式 review path 不再使用
`client.open(new=True)` 回退。

## License

AGPL-3.0-only
