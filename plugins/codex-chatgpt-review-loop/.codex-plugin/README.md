# Plugin Manifest

This directory contains the Codex plugin manifest. The manifest exposes a
user-invoked review Skill: explicit ChatGPT/Web LLM Bridge review intent and a
conversation URL or session ID are required. Codex discovers the plugin-local
`hooks/hooks.json`; its production configuration registers only the static Stop
gate. Hooks are local, bounded decision helpers; provider communication remains
in the Bridge review driver.
