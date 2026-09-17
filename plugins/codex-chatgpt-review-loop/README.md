# Codex ChatGPT Review Loop

[English](#english) | [中文](#中文)

## English

### Overview

This plugin provides a Bridge-backed, bounded ChatGPT code-review loop for Codex:

```text
Codex
  -> SessionStart / Stop Hooks
  -> chatgpt-review-loop Skill
  -> review_driver.py
  -> WebLLMClient
  -> Broker
  -> Browser Extension
  -> ChatGPT Web
```

The intended workflow is:

```text
Codex implements the task
  -> tests
  -> commit / push
  -> @@REVIEW_READY@@
  -> Stop Hook hands off to the review Skill
  -> ChatGPT Web reviews the committed HEAD
     -> PASS: finish
     -> REVISE: Codex applies the generated prompt, retests, commits, and reviews again
     -> third REVISE: MAX_ROUNDS_REVISE, stop for user handling
```

The Bridge driver is the only supported provider path. Native browser runtime code is retained under `experimental/native-browser/` for experiments and is not part of the production flow.

### Prerequisites

- Codex CLI with plugin support.
- The `web-llm-bridge` Python package is importable in the Python environment used by Codex.
- The Web LLM Bridge browser extension is installed.
- The browser is running.
- `chatgpt.com` is already authenticated.
- The Bridge/extension connection is healthy.

### Installation

#### Option A: install from this repository as a local marketplace

This is the recommended development setup for this repository.

Create `.agents/plugins/marketplace.json` at the repository root:

```json
{
  "name": "web-llm-bridge-local",
  "interface": {
    "displayName": "Web LLM Bridge Local"
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

Register the repository marketplace and install the plugin:

```bash
codex plugin marketplace add .
codex plugin add codex-chatgpt-review-loop@web-llm-bridge-local
```

Verify:

```bash
codex plugin list --json
```

Start a new Codex session/thread after installation so the plugin skills and hooks are loaded.

#### Option B: install as a personal plugin

Use this when you want the plugin available in multiple repositories.

Personal marketplace location:

```text
~/.agents/plugins/marketplace.json
```

Personal plugin source location:

```text
~/plugins/codex-chatgpt-review-loop
```

On Windows, these correspond to locations under `%USERPROFILE%`.

Copy or link this plugin directory to:

```text
~/plugins/codex-chatgpt-review-loop
```

Then create or update `~/.agents/plugins/marketplace.json`:

```json
{
  "name": "personal",
  "interface": {
    "displayName": "Personal"
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

The default personal marketplace is discovered automatically. Install the plugin with:

```bash
codex plugin add codex-chatgpt-review-loop@personal
```

Verify:

```bash
codex plugin list --json
```

Then start a new Codex session/thread.

### Bridge smoke test

Before relying on the review loop, verify that Web LLM Bridge can communicate with the authenticated ChatGPT Web page:

```bash
python plugins/codex-chatgpt-review-loop/skills/chatgpt-review-loop/scripts/review_driver.py smoke --json
```

A successful smoke test returns `ok: true` and validates two messages in the same persisted session.

### Usage

Start Codex inside the repository you want to modify and give it a normal development task. For example:

```text
Implement the requested change.
Run the relevant tests.
Commit the completed change and push when required.
After implementation, enter the ChatGPT external review loop.
Apply REVISE feedback automatically, retest, commit, and review again.
Stop on PASS or MAX_ROUNDS_REVISE.
```

For code-change tasks, the SessionStart hook instructs Codex to finish the implementation turn with a deterministic context block followed by `@@REVIEW_READY@@`:

```text
@@REVIEW_CONTEXT_BEGIN@@
Original task:
<original development goal>

Implementation summary:
<what was implemented>

Tests:
<tests actually run and results>
@@REVIEW_CONTEXT_END@@

@@REVIEW_READY@@
```

The Stop hook only performs the initial handoff. Once the review Skill starts, subsequent REVISE rounds are driven directly by the Skill and `review_driver.py`; they do not re-enter the Stop hook.

### Review states

- `PASS`: the committed HEAD passed external review. The Skill finishes with `@@WEB_REVIEW_PASS@@`.
- `REVISE`: the driver returns both `review_text` and a separate `codex_prompt`; Codex applies the prompt, tests, commits, and starts the next review round.
- `MAX_ROUNDS_REVISE`: the third review still requires changes. The final prompt is returned for user handling but is not executed automatically.
- `REVIEW_DELIVERY_UNKNOWN`: delivery could not be proven. The driver fails closed and does not blindly resend.
- `NO_CODE_CHANGE`: a REVISE result exists but the reviewed HEAD has not changed.
- `REVIEW_CONTEXT_MISMATCH`: the original task changed during an active REVISE cycle.

Three automatic review rounds are allowed per cycle. After `MAX_ROUNDS`, a new cycle requires both a new original task and a new committed HEAD.

### State

Review state is stored below:

```text
.git/codex-chatgpt-review/state.json
```

The state contains review/session metadata only. It does not store cookies, ChatGPT access tokens, or full review text.

The formal review command is:

```bash
python <plugin-root>/skills/chatgpt-review-loop/scripts/review_driver.py review \
  --json \
  --context-file <temporary-file>
```

`--context-file` is mandatory. The driver rejects missing or empty `Original task`, `Implementation summary`, or `Tests` fields.

### Troubleshooting

If Codex does not enter the review loop:

1. Run `codex plugin list --json` and confirm `codex-chatgpt-review-loop` is installed.
2. Start a new Codex session/thread after installing or updating the plugin.
3. Confirm the browser extension is installed and the browser is running.
4. Confirm `chatgpt.com` is logged in.
5. Run the Bridge smoke test.
6. Check that the development turn ended with `@@REVIEW_READY@@` as the final non-empty line.
7. Check that the worktree was clean and the change was committed before review.
8. If Codex asks you to trust the plugin's command hooks, review the commands and allow them before retrying.

---

## 中文

### 功能说明

该插件为 Codex 提供一个基于 Web LLM Bridge 的有限轮次 ChatGPT Web 代码审查闭环：

```text
Codex
  -> SessionStart / Stop Hooks
  -> chatgpt-review-loop Skill
  -> review_driver.py
  -> WebLLMClient
  -> Broker
  -> 浏览器扩展
  -> ChatGPT Web
```

目标工作流：

```text
Codex 完成开发
  -> 运行测试
  -> commit / push
  -> 输出 @@REVIEW_READY@@
  -> Stop Hook 阻止本轮直接结束
  -> chatgpt-review-loop Skill 接管
  -> ChatGPT Web 独立审查当前 committed HEAD
     -> PASS：结束
     -> REVISE：生成 Codex 修改提示词，Codex 自动修复、测试、提交并再次审查
     -> 第 3 轮仍 REVISE：返回 MAX_ROUNDS_REVISE，停止自动修改，交给用户处理
```

正式路径只使用 Web LLM Bridge。`experimental/native-browser/` 中的原生浏览器运行时代码仅用于实验，不属于正式闭环。

### 前置条件

使用前需要满足：

- 已安装支持 Plugin 的 Codex CLI。
- Codex 使用的 Python 环境能够 `import web_llm_bridge`。
- 已安装 Web LLM Bridge 浏览器扩展。
- 浏览器处于运行状态。
- `chatgpt.com` 已完成登录。
- Browser Extension 与 Bridge Broker 可以正常连接。

### 安装方法

#### 方法一：将当前仓库注册为本地 Marketplace

这是开发和调试当前仓库时推荐的安装方式。

在 `web-llm-bridge` 仓库根目录创建：

```text
.agents/plugins/marketplace.json
```

内容：

```json
{
  "name": "web-llm-bridge-local",
  "interface": {
    "displayName": "Web LLM Bridge Local"
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

在仓库根目录执行：

```bash
codex plugin marketplace add .
codex plugin add codex-chatgpt-review-loop@web-llm-bridge-local
```

检查安装结果：

```bash
codex plugin list --json
```

安装后重新开启一个新的 Codex session/thread，使新的 Skill 和 Hook 被重新加载。

#### 方法二：安装为个人全局 Plugin

如果希望在 PersonalRecorder、Hermes、Zotero 插件或其它任意仓库中直接使用，建议安装到个人 Marketplace。

默认个人 Marketplace：

```text
~/.agents/plugins/marketplace.json
```

默认个人 Plugin 目录：

```text
~/plugins/codex-chatgpt-review-loop
```

Windows 下的 `~` 对应 `%USERPROFILE%`。

先把当前插件目录复制或链接到：

```text
~/plugins/codex-chatgpt-review-loop
```

然后创建或更新：

```text
~/.agents/plugins/marketplace.json
```

示例：

```json
{
  "name": "personal",
  "interface": {
    "displayName": "Personal"
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

默认个人 Marketplace 会被 Codex 自动发现，不需要再执行 `codex plugin marketplace add`。

安装：

```bash
codex plugin add codex-chatgpt-review-loop@personal
```

验证：

```bash
codex plugin list --json
```

然后重新启动一个新的 Codex session/thread。

### Windows 本地开发建议

如果不希望复制插件目录，可以使用目录 Junction，让个人插件目录直接指向当前仓库中的插件源码。

PowerShell 示例：

```powershell
New-Item -ItemType Directory -Force "$HOME\plugins"
New-Item -ItemType Junction `
  -Path "$HOME\plugins\codex-chatgpt-review-loop" `
  -Target "D:\path\to\web-llm-bridge\plugins\codex-chatgpt-review-loop"
```

将 `D:\path\to\web-llm-bridge` 替换为实际仓库路径。

### 安装后的 Bridge 连通性测试

正式使用闭环前，先验证 Bridge 能否与已登录的 ChatGPT Web 正常通信：

```bash
python plugins/codex-chatgpt-review-loop/skills/chatgpt-review-loop/scripts/review_driver.py smoke --json
```

成功时应返回：

```json
{
  "ok": true,
  "first": "BRIDGE_REVIEW_SMOKE_OK",
  "second": "BRIDGE_REVIEW_SECOND_OK"
}
```

该 smoke 会在同一个 Bridge session 中连续发送两条消息，用于验证 session 复用和浏览器通信。

### 如何使用

进入需要开发的目标仓库后启动 Codex，然后正常下达开发任务即可。

建议在任务末尾加入：

```text
完成实现并运行相关测试。
完成后 commit，并在当前工作流要求时 push。
随后进入 ChatGPT 外部审查闭环。
如果外部审查返回 REVISE，则按返回的 Codex prompt 自动修复、重新测试、commit/push，并继续下一轮审查。
PASS 后结束；如果达到 MAX_ROUNDS_REVISE，则停止自动修改并向我报告剩余问题。
```

对于明确要求修改代码的任务，SessionStart Hook 会要求 Codex 在开发完成后输出：

```text
@@REVIEW_CONTEXT_BEGIN@@
Original task:
<用户最初的开发目标>

Implementation summary:
<本轮实际完成内容>

Tests:
<实际运行过的测试和结果>
@@REVIEW_CONTEXT_END@@

@@REVIEW_READY@@
```

`@@REVIEW_READY@@` 必须是最后一个非空行。

Stop Hook 检测到该标记后，会阻止 Codex 直接结束，并将完整 `REVIEW_CONTEXT` 交给 `chatgpt-review-loop` Skill。

之后的 REVISE 轮次不会再次依赖 Stop Hook，而由 Skill 直接调用 `review_driver.py` 完成：

```text
Round 1 Review
  -> REVISE
  -> Codex 修改
  -> test
  -> commit / push
  -> Round 2 Review
  -> ...
```

### 审查状态

`PASS`

当前 committed HEAD 已通过外部 ChatGPT Review。Skill 最终输出：

```text
@@WEB_REVIEW_PASS@@
```

随后 Codex 正常结束。

`REVISE`

Driver 返回：

```json
{
  "status": "REVISE",
  "review_text": "ChatGPT 第一阶段审查原文",
  "codex_prompt": "交给 Codex 执行的修改提示词"
}
```

Codex 按 `codex_prompt` 修改代码、测试、commit/push，并直接进入下一轮 Review。

`MAX_ROUNDS_REVISE`

最多自动审查 3 轮。如果第三轮仍然是 REVISE，Driver 返回 `MAX_ROUNDS_REVISE`。

此时：

- 不再执行最终 `codex_prompt`。
- 不产生未经下一轮审查的新代码。
- 不发送第 4 次 Review。
- 将 `review_text` 和 `codex_prompt` 返回给用户处理。

`REVIEW_DELIVERY_UNKNOWN`

Bridge 无法确定消息是否已经成功送达时，Driver 会 fail closed，不会盲目重发，避免 ChatGPT 收到重复请求。

`NO_CODE_CHANGE`

上一轮是 REVISE，但当前 HEAD 没有发生变化，因此不会重复审查相同代码。

`REVIEW_CONTEXT_MISMATCH`

处于 active REVISE cycle 时，`Original task` 被修改。Driver 会停止并拒绝继续 Review。

### Review State

状态文件位于：

```text
.git/codex-chatgpt-review/state.json
```

其中只保存：

- session / conversation identity
- 当前 round
- HEAD SHA
- task hash
- cycle ID
- pending request
- terminal status

不会保存：

- ChatGPT Cookie
- Access Token
- 登录凭据
- 完整 `review_text`

### 手动调用 Review Driver

正式 Review：

```bash
python <plugin-root>/skills/chatgpt-review-loop/scripts/review_driver.py review \
  --json \
  --context-file <temporary-file>
```

`--context-file` 是必填项，其中必须包含完整的：

```text
@@REVIEW_CONTEXT_BEGIN@@
...
@@REVIEW_CONTEXT_END@@
```

并且以下三个字段必须非空：

- `Original task`
- `Implementation summary`
- `Tests`

正常使用 Codex Plugin 时不需要手动执行该命令，Skill 会自动调用。

### 常见问题排查

如果 Codex 完成开发后没有进入 ChatGPT Review：

1. 执行 `codex plugin list --json`，确认 `codex-chatgpt-review-loop` 已安装。
2. 安装或更新 Plugin 后，新建 Codex session/thread，不要继续使用安装前已经启动的旧 session。
3. 确认浏览器扩展已加载。
4. 确认浏览器正在运行。
5. 确认 `chatgpt.com` 已登录。
6. 运行 `review_driver.py smoke --json` 验证 Bridge。
7. 检查 Codex 最后是否输出了完整 `REVIEW_CONTEXT`。
8. 检查 `@@REVIEW_READY@@` 是否为最后一个非空行。
9. 检查代码是否已经 commit，worktree 是否 clean。
10. 如果 Codex 首次加载插件时要求信任命令 Hook，先审查 Hook 命令并允许执行，再重新测试。

### 当前验证状态

单元测试和协议测试已经覆盖 Driver、Hook、状态迁移、恢复语义和最大轮次行为。

真实使用仍建议依次验证：

```text
Bridge smoke
-> synthetic PASS
-> synthetic REVISE -> PASS
-> synthetic 3x REVISE -> MAX_ROUNDS_REVISE
-> fixture repository E2E
```

只有完整 fixture E2E 跑通后，才能证明实际的：

```text
Codex -> ChatGPT Web -> Codex
```

自动闭环在真实开发环境中完整成立。
