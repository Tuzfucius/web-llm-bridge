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

## Commands and state

Use `review_driver.py smoke --json` for a two-message Bridge connectivity test.
Use `review_driver.py review --json --context-file <temporary-file>` for one
bounded review attempt. The file contains the deterministic
`@@REVIEW_CONTEXT_BEGIN@@`/`@@REVIEW_CONTEXT_END@@` block from the Codex
development turn and must not be stored in a tracked path. State is stored
below `.git/codex-chatgpt-review/state.json`; it contains no cookies or tokens.
Three automatic rounds are allowed per review cycle. PASS followed by a new
commit starts a new cycle, and a new original task context can start a new
cycle after MAX_ROUNDS.
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
executing its prompt. Review results expose the first-stage `review_text` and,
for REVISE, the separate `codex_prompt` for user handling. Unknown prompt
delivery is recovered only from a user request marker in conversation history;
successful prompt recovery restores `last_status=REVISE` and same-SHA calls
return `NO_CODE_CHANGE`.

## Live test status

Unit and protocol tests are local/fake-client tests. A real Bridge smoke or
synthetic ChatGPT protocol test must be run only with the Extension installed
and `chatgpt.com` logged in; this README does not claim that live E2E is done.
