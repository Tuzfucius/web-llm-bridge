# Codex ChatGPT Review Loop

## English

This plugin is user-invoked, not a default review lifecycle. Installing it does
not cause ordinary coding tasks to contact ChatGPT or emit review markers.

### Prerequisites

- A Codex CLI version with Plugin support.
- The `web-llm-bridge` Python package can be imported.
- The Browser Extension is installed.
- A browser is running.
- `chatgpt.com` is signed in.
- The Bridge and Extension connection is working.

These runtime prerequisites are needed only for an explicitly requested
external review.

### Local development install

The plugin is located at:

```text
plugins/codex-chatgpt-review-loop
```

On Windows, use a Junction for local development. Do not overwrite an existing
target path; inspect or remove the old installation first.

```powershell
New-Item -ItemType Directory -Force "$HOME\plugins"

New-Item -ItemType Junction `
  -Path "$HOME\plugins\codex-chatgpt-review-loop" `
  -Target "<repo>\plugins\codex-chatgpt-review-loop"
```

Create `~/.agents/plugins/marketplace.json` with this local marketplace entry
(replace the path with your repository path when needed):

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

Install and verify the plugin:

```bash
codex plugin add codex-chatgpt-review-loop@local
codex plugin list --json
```

Fully exit and restart Codex after installation.

### Activation and use

The loop activates only when the same user request includes an explicit request
for external ChatGPT/Web LLM Bridge review and exactly one target: a ChatGPT
conversation URL or a Bridge session ID.

Valid examples:

```text
Complete this feature, then use https://chatgpt.com/c/xxxx for ChatGPT external review. Continue fixing issues for at most three rounds.
```

```text
After implementation, use Web LLM Bridge session abc123 to perform an external review.
```

These do not activate the plugin because they lack an explicit target:

```text
Fix this bug.
Complete it and help me review it.
Let ChatGPT take a look after implementation.
```

When the target is missing, the Skill asks for a conversation URL or session
ID. It does not create a ChatGPT conversation, reuse an old target, arm an
activation, or run the driver.

The Skill creates a repository-local one-shot activation at
`.git/codex-chatgpt-review/activation.json`:

```bash
python <plugin-root>/skills/chatgpt-review-loop/scripts/review_activation.py arm \
  --conversation-url "https://chatgpt.com/c/xxxx" \
  --task-file <original-task-file>
```

Use `--session-id "abc123"` instead for a Bridge session. The target options
are mutually exclusive.

### Activation conflicts and lifecycle

Only one `armed=true` activation may exist in the same Git worktree. A second
`arm` attempt returns `ACTIVATION_CONFLICT`; it never silently clears,
consumes, overwrites, or reuses the existing activation. Complete the current
review, or explicitly run the following command before arming a new target:

```bash
python <plugin-root>/skills/chatgpt-review-loop/scripts/review_activation.py clear
```

Consumed activations (`armed=false`) may be replaced by a new `arm`. Invalid
JSON, unsupported versions, and invalid activation data fail closed and remain
unchanged.

After a successful `arm`, if implementation fails, required tests fail, work
is blocked, a user decision is pending, the user cancels, the task is
abandoned, or a dirty/uncommitted worktree prevents the first
`@@REVIEW_READY@@`, the Skill must run `clear` before ending the turn. This
pre-review cleanup does not apply after the Driver starts the first review:
`REVIEW_DELIVERY_UNKNOWN` keeps its existing at-most-once recovery behavior.
After the first target binding succeeds, activation is cleared and later REVISE
rounds use the existing `state.json` version 2 state.

### Stop Hook

Codex statically registers the Stop Hook. On an ordinary turn end, the Hook
process may be called, but when review is not activated it immediately returns
`{}`. In that default no-op path it does not read activation, access Git, start
the Bridge, access the browser, access the network, or block Codex from ending.

The Hook blocks only when the final non-empty line is `@@REVIEW_READY@@` and
the message also includes one valid activation marker and one complete context
block. `@@REVIEW_READY@@` by itself never starts a review.

The Driver retains the bounded review state machine and its existing
at-most-once delivery behavior. The supported flow does not use private
ChatGPT APIs, cookies, tokens, CDP ports, or browser automation.

## 安装

本插件由用户显式触发，不会为普通编码任务自动执行外部审查。

### 前置条件

- Codex CLI 支持 Plugin。
- `web-llm-bridge` Python package 可以正常 import。
- Browser Extension 已安装。
- 浏览器已运行。
- 已登录 `chatgpt.com`。
- Bridge 与 Extension 通路正常。

上述运行条件只在用户显式要求外部审查时需要满足。

### 本地开发安装

Plugin 位于：

```text
plugins/codex-chatgpt-review-loop
```

Windows 本地开发推荐使用 Junction。若目标已存在，请先处理旧安装，不能直接覆盖。

```powershell
New-Item -ItemType Directory -Force "$HOME\plugins"

New-Item -ItemType Junction `
  -Path "$HOME\plugins\codex-chatgpt-review-loop" `
  -Target "<repo>\plugins\codex-chatgpt-review-loop"
```

在 `~/.agents/plugins/marketplace.json` 配置本地 Marketplace。必要时将 `path`
替换为本机仓库路径：

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

安装并检查：

```bash
codex plugin add codex-chatgpt-review-loop@local
codex plugin list --json
```

安装后必须完全退出并重新启动 Codex。

### 使用与激活

仅当同一条用户请求同时包含明确的 ChatGPT/Web LLM Bridge 外部审查要求，以及唯一的显式目标（ChatGPT conversation URL 或 Bridge session ID）时，Skill 才会激活。

有效自然语言示例：

```text
完成这个功能，然后使用 https://chatgpt.com/c/xxxx 进行 ChatGPT 外部审查，有问题继续修复，最多三轮。
```

```text
完成后使用 Web LLM Bridge session abc123 执行外部 Review。
```

以下不会触发，因为缺少显式 target：

```text
修复这个 bug
完成后帮我 review
完成后让 ChatGPT 看一下
```

缺少 target 时，Skill 会要求用户提供 conversation URL 或 session ID；不会创建新的 ChatGPT 页面、复用旧 target、arm activation 或运行 Driver。

Skill 在 `.git/codex-chatgpt-review/activation.json` 创建仓库本地的一次性 activation：

```bash
python <plugin-root>/skills/chatgpt-review-loop/scripts/review_activation.py arm \
  --conversation-url "https://chatgpt.com/c/xxxx" \
  --task-file <original-task-file>
```

使用 Bridge session 时改用 `--session-id "abc123"`，两个 target 选项互斥。

### Activation 冲突与生命周期

同一个 Git worktree 同时只能存在一个 `armed=true` activation。再次触发 `arm`
会返回 `ACTIVATION_CONFLICT`，绝不静默 clear、consume、overwrite 或 reuse 旧 activation。
必须完成当前 review，或显式执行以下命令后，才能 arm 新 activation：

```bash
python <plugin-root>/skills/chatgpt-review-loop/scripts/review_activation.py clear
```

已 consumed 的 activation（`armed=false`）允许被新的 `arm` 替换。invalid JSON、未知版本和无效 activation 数据保持 fail-closed，原文件不会被覆盖。

一旦 `arm` 成功，若首次 `@@REVIEW_READY@@` 前出现 implementation failure、required tests failed、blocker、pending user decision、user cancellation、abandoned task、阻止审查的 dirty/uncommitted state，或任何其他提前结束，Skill 必须先执行 `clear` 再结束。本规则只适用于首次 handoff 前；Driver 已开始首次 review 后，`REVIEW_DELIVERY_UNKNOWN` 保持现有 at-most-once recovery，不得因通用清理丢失恢复信息。首次 target 绑定成功后仍会 clear activation，后续 REVISE 使用现有 `state.json` version 2 状态。

### Stop Hook

Codex 仍静态注册 Stop Hook。普通 turn 结束时 Hook 进程可能被调用，但未激活 Review 时会立即返回 `{}`；不读取 activation、不访问 Git、不启动 Bridge、不访问浏览器、不访问网络，也不阻止 Codex 结束。

仅当最终非空行是 `@@REVIEW_READY@@`，且消息同时包含唯一有效的 activation marker 与完整 context block 时，Hook 才会 block。单独的 `@@REVIEW_READY@@` 不会启动审查。

Driver 的有界状态机与 at-most-once delivery 语义保持不变。支持路径不会使用私有 ChatGPT API、cookie、token、CDP port 或浏览器自动化。

## License

AGPL-3.0-only
