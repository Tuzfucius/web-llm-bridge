# Review Loop Scripts

这些脚本构成 Bridge-backed ChatGPT Review 的确定性边界：

- `build_review_prompt.py` 从干净的 Git HEAD 收集审查材料，并加入
  Review Context。
- `parse_review.py` 严格解析 PASS/REVISE 和 Codex 修改提示词 marker。
- `parse_review_context.py` 严格提取 Original task、Implementation summary
  和 Tests 三个 section。
- `review_state.py` 将会话、轮次和 at-most-once 状态保存到 `.git` 下。
- `review_driver.py` 复用 `WebLLMClient` 完成 smoke 与 review 流程，并在
  unsafe/unknown delivery 时 fail closed；正式 review 强制完整
  `REVIEW_CONTEXT`，并校验 active REVISE cycle 的 Original task 不漂移。
