# Codex Hooks

`hooks.json` registers the SessionStart and Stop commands for the plugin. Both
commands resolve their script through `${PLUGIN_ROOT}` because Codex runs hook
commands with the current workspace as cwd. `session_start.py` contributes the
development/review lifecycle policy; `stop_review.py` only returns a Codex stop
decision and copies a complete review-context block into the continuation
reason. Stop markers must occupy their own line; incidental prose containing a
marker does not trigger a continuation. Neither hook performs provider
communication or persists review state.
