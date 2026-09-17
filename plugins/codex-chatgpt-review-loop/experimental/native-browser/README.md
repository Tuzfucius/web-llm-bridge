# Experimental Native Browser Runtime

Status: blocked by Codex host capability.

Reason: the current Codex task surface exposes panel opening but no callable
DOM inspection, JavaScript evaluation, or CDP control.

This directory preserves the former DOM-injection runtime as an explicitly
experimental fallback. `chatgpt_runtime.js` is not registered by the plugin
and is not used by the Bridge-backed review loop.

The supported path is the Web LLM Bridge `review_driver`, which owns provider
transport, review state, prompt construction, and bounded retries. Native
browser/CDP automation, private ChatGPT APIs, cookies, tokens, and debugging
ports are intentionally out of scope. Do not use this runtime in the
production review path.
