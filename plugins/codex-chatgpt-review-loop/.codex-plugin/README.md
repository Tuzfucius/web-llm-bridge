# Plugin Manifest

This directory contains the validation-ready Codex plugin manifest. The
manifest registers the Bridge-backed review Skill. Codex discovers the
plugin-local default `hooks/hooks.json`; its commands resolve scripts through
`${PLUGIN_ROOT}`. Hooks are local, bounded decision helpers; provider
communication remains in the Bridge review driver.
