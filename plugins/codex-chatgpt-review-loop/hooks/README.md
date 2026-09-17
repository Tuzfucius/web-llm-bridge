# Codex Hooks

`hooks.json` registers only the static Stop command for the production plugin.
It resolves `stop_review.py` through `${PLUGIN_ROOT}` because Codex runs hook
commands with the current workspace as cwd. The legacy `session_start.py`
script is retained for experiments but is intentionally not registered, so
installing the plugin does not inject a review lifecycle into ordinary tasks.

`stop_review.py` is a lightweight, fail-closed gate. It returns `{}` unless the
final non-empty line is `@@REVIEW_READY@@` and the message also contains one
valid activation marker plus a complete context block matching the repository
local activation file. It never performs provider communication, browser I/O,
or Git operations on the default path.
