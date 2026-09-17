# Review loop scripts

These scripts form the deterministic boundary of the Bridge-backed review
workflow:

- `review_activation.py` manages the repository-local, explicit-target
  activation. It is separate from review state and stores no credentials.
- `build_review_prompt.py` collects clean Git HEAD material and adds the review
  context.
- `parse_review.py` strictly parses PASS/REVISE and Codex prompt markers.
- `parse_review_context.py` extracts the three required context sections and
  rejects duplicates or missing sections.
- `review_state.py` persists session, round, task hash, cycle identity, and
  at-most-once recovery state below `.git/codex-chatgpt-review/state.json`.
- `review_driver.py` reuses `WebLLMClient` for smoke and review operations. A
  new review cycle requires an explicit conversation URL or Bridge session ID;
  active REVISE/recovery cycles reuse only their current state target.

The driver owns the existing bounded protocol and never stores cookies,
tokens, or browser debugging information.
