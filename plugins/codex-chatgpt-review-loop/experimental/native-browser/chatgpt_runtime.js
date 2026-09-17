(function installCodexChatGPTRuntime(root) {
  "use strict";

  const VERSION = "0.1.0";
  const SELECTORS = Object.freeze({
    prompt: ["#prompt-textarea", '[contenteditable="true"][role="textbox"]'],
    send: ["#composer-submit-button", '[data-testid="send-button"]', 'button[aria-label="Send prompt"]'],
    stop: ['[data-testid="stop-button"]', 'button[aria-label*="Stop"]'],
    user: '[data-message-author-role="user"]',
    assistant: '[data-message-author-role="assistant"]',
    login: ['a[href*="/auth/login"]', 'button[data-testid*="login"]', 'button[aria-label*="Log in"]', 'form[action*="/auth/login"]', 'input[type="email"]'],
  });
  const DEFAULTS = Object.freeze({
    pollIntervalMs: 200,
    stableTimeMs: 2_000,
    readyTimeoutMs: 30_000,
    submissionTimeoutMs: 60_000,
    responseTimeoutMs: 120_000,
  });

  function clock() {
    return typeof root.performance?.now === "function" ? root.performance.now() : Date.now();
  }

  function sleep(milliseconds) {
    return new Promise((resolve) => root.setTimeout(resolve, milliseconds));
  }

  function failure(code, message, details = {}) {
    const error = new Error(message);
    error.code = code;
    Object.assign(error, details);
    return error;
  }

  function publicError(error) {
    return {
      code: error?.code || "RUNTIME_ERROR",
      message: error?.message || String(error),
    };
  }

  function documentRef() {
    return root.document || null;
  }

  function currentUrl() {
    return String(root.location?.href || "");
  }

  function currentHostname() {
    if (root.location?.hostname) return String(root.location.hostname).toLowerCase();
    try { return new URL(currentUrl()).hostname.toLowerCase(); } catch (_error) { return ""; }
  }

  function isChatGPTPage() {
    return currentHostname() === "chatgpt.com" || currentHostname() === "www.chatgpt.com";
  }

  function isElement(value) {
    return Boolean(value && (value.nodeType === 1 || typeof value.matches === "function"));
  }

  function visible(element) {
    if (!element) return false;
    try {
      const style = typeof root.getComputedStyle === "function" ? root.getComputedStyle(element) : null;
      if (style && (style.display === "none" || style.visibility === "hidden")) return false;
      return typeof element.getClientRects !== "function" || element.getClientRects().length > 0;
    } catch (_error) {
      return true;
    }
  }

  function queryAll(selector) {
    const document = documentRef();
    if (!document?.querySelectorAll) return [];
    try { return Array.from(document.querySelectorAll(selector)); } catch (_error) { return []; }
  }

  function findVisible(selectors) {
    const document = documentRef();
    for (const selector of selectors) {
      try {
        const candidate = document?.querySelector?.(selector) || queryAll(selector)[0];
        if (visible(candidate)) return candidate;
      } catch (_error) {}
    }
    return null;
  }

  function promptText(prompt) {
    if (!prompt) return "";
    if (typeof prompt.value === "string") return prompt.value;
    const innerText = String(prompt.innerText ?? "");
    return innerText || String(prompt.textContent ?? "");
  }

  function normalizeText(value) {
    return String(value ?? "").replace(/\u00a0/g, " ").replace(/\r\n/g, "\n").trim();
  }

  function assistantText(node) {
    const innerText = String(node?.innerText ?? "");
    return normalizeText(innerText || node?.textContent || "");
  }

  function assistantNodes() {
    return queryAll(SELECTORS.assistant);
  }

  function turnId(node) {
    let candidate = node;
    while (candidate) {
      for (const attribute of ["data-turn-id", "data-testid", "data-turn"]) {
        const value = candidate.getAttribute?.(attribute);
        if (value) return String(value);
      }
      candidate = candidate.parentElement || null;
    }
    return null;
  }

  function assistantSnapshot() {
    const nodes = assistantNodes();
    const node = nodes.length ? nodes[nodes.length - 1] : null;
    return { node, found: Boolean(node), text: assistantText(node), turn_id: turnId(node) };
  }

  function userCount() {
    return queryAll(SELECTORS.user).length;
  }

  function isGenerating() {
    return Boolean(findVisible(SELECTORS.stop));
  }

  function isEnabled(button) {
    return Boolean(button) && button.disabled !== true && button.getAttribute?.("aria-disabled") !== "true" && !button.hasAttribute?.("disabled");
  }

  function hasLoginMarker() {
    return SELECTORS.login.some((selector) => queryAll(selector).some(visible));
  }

  function probe() {
    if (!isChatGPTPage()) return { ok: false, reason: "NOT_CHATGPT_PAGE", version: VERSION, url: currentUrl() };
    const prompt = findVisible(SELECTORS.prompt);
    const send = findVisible(SELECTORS.send);
    const generating = isGenerating();
    const result = {
      ok: Boolean(prompt),
      version: VERSION,
      url: currentUrl(),
      prompt_found: Boolean(prompt),
      send_found: Boolean(send),
      generating,
    };
    if (!prompt) result.reason = hasLoginMarker() ? "NOT_LOGGED_IN" : "PROMPT_NOT_FOUND";
    return result;
  }

  async function waitForReady(options = {}) {
    if (!isChatGPTPage()) throw failure("NOT_CHATGPT_PAGE", "Current page is not chatgpt.com");
    const config = { ...DEFAULTS, ...options };
    const deadline = clock() + config.readyTimeoutMs;
    while (clock() < deadline) {
      if (hasLoginMarker()) throw failure("NOT_LOGGED_IN", "ChatGPT login is required");
      const prompt = findVisible(SELECTORS.prompt);
      if (prompt) return { ok: true, prompt, url: currentUrl() };
      await sleep(config.pollIntervalMs);
    }
    throw failure("PROMPT_NOT_FOUND", "ChatGPT prompt did not become ready");
  }

  function getLastAssistant() {
    const snapshot = assistantSnapshot();
    return { found: snapshot.found, text: snapshot.text, turn_id: snapshot.turn_id };
  }

  function dispatchInput(element, text) {
    let event;
    try {
      event = typeof root.InputEvent === "function"
        ? new root.InputEvent("input", { bubbles: true, inputType: "insertText", data: text })
        : new root.Event("input", { bubbles: true });
    } catch (_error) {
      event = { type: "input", bubbles: true, inputType: "insertText", data: text };
    }
    element.dispatchEvent?.(event);
  }

  function nativeValueSetter(element, value) {
    const prototype = Object.getPrototypeOf(element);
    const descriptor = prototype && Object.getOwnPropertyDescriptor(prototype, "value");
    if (descriptor?.set) descriptor.set.call(element, value);
    else element.value = value;
  }

  function writePrompt(prompt, text) {
    try {
      prompt.focus?.();
      if (prompt.isContentEditable) {
        const document = documentRef();
        const range = document?.createRange?.();
        const selection = root.getSelection?.();
        if (range && selection && prompt.hasChildNodes?.()) {
          range.selectNodeContents(prompt);
          selection.removeAllRanges();
          selection.addRange(range);
        }
        const deleted = document?.execCommand?.("delete", false);
        const inserted = document?.execCommand?.("insertText", false, text);
        if (!deleted || !inserted) {
          prompt.textContent = text;
          try { prompt.innerText = text; } catch (_error) {}
        }
      } else if ("value" in prompt) {
        nativeValueSetter(prompt, "");
        nativeValueSetter(prompt, text);
      } else {
        throw failure("INPUT_FAILED", "Prompt element does not support text input");
      }
      dispatchInput(prompt, text);
      if (normalizeText(promptText(prompt)) !== normalizeText(text)) {
        if (prompt.isContentEditable) {
          prompt.textContent = text;
          try { prompt.innerText = text; } catch (_error) {}
        } else nativeValueSetter(prompt, text);
        dispatchInput(prompt, text);
      }
      if (normalizeText(promptText(prompt)) !== normalizeText(text)) throw failure("INPUT_FAILED", "Prompt text was not accepted");
    } catch (error) {
      if (error?.code) throw error;
      throw failure("INPUT_FAILED", error?.message || "Unable to write prompt");
    }
  }

  async function waitFor(find, code, message, timeoutMs, pollIntervalMs) {
    const deadline = clock() + timeoutMs;
    while (clock() < deadline) {
      const value = find();
      if (value) return value;
      await sleep(pollIntervalMs);
    }
    throw failure(code, message);
  }

  function isNewAssistant(current, baseline) {
    if (!current.found) return false;
    if (!baseline || !baseline.found) return true;
    if (baseline.node && current.node !== baseline.node) return true;
    if (baseline.turn_id && current.turn_id && baseline.turn_id !== current.turn_id) return true;
    return current.text !== baseline.text;
  }

  async function waitForSubmission(beforeUsers, baseline, prompt, timeoutMs, pollIntervalMs) {
    const deadline = clock() + timeoutMs;
    while (clock() < deadline) {
      const currentPrompt = findVisible(SELECTORS.prompt) || prompt;
      const currentAssistant = assistantSnapshot();
      if (userCount() > beforeUsers) return "user_count";
      if (normalizeText(promptText(currentPrompt)) === "") return "prompt_cleared";
      if (isGenerating()) return "stop_button";
      if (isNewAssistant(currentAssistant, baseline)) return "assistant_changed";
      await sleep(pollIntervalMs);
    }
    throw failure("SEND_FAILED", "Send click did not produce submission evidence");
  }

  async function sendMessage(text, options = {}) {
    if (typeof text !== "string" || !text.trim()) throw failure("INPUT_FAILED", "Message must be a non-empty string");
    if (!isChatGPTPage()) throw failure("NOT_CHATGPT_PAGE", "Current page is not chatgpt.com");
    if (isGenerating()) throw failure("BUSY", "ChatGPT is still generating a response");
    const config = { ...DEFAULTS, ...options };
    const prompt = findVisible(SELECTORS.prompt);
    if (!prompt) throw failure(hasLoginMarker() ? "NOT_LOGGED_IN" : "PROMPT_NOT_FOUND", "ChatGPT prompt was not found");
    const beforeUsers = userCount();
    const baseline = assistantSnapshot();
    writePrompt(prompt, text);
    const button = await waitFor(() => {
      const candidate = findVisible(SELECTORS.send);
      return isEnabled(candidate) ? candidate : null;
    }, "SEND_BUTTON_NOT_FOUND", "ChatGPT send button is not available", config.readyTimeoutMs, config.pollIntervalMs);
    try {
      button.click?.();
    } catch (error) {
      throw failure("SEND_FAILED", error?.message || "Unable to click ChatGPT send button");
    }
    const submittedBy = await waitForSubmission(beforeUsers, baseline, prompt, config.submissionTimeoutMs, config.pollIntervalMs);
    return { ok: true, submitted_by: submittedBy, user_count: userCount(), url: currentUrl() };
  }

  function parseWaitArguments(first, second) {
    if (first && (first.nodeType || first.found !== undefined || first.node)) return { baseline: first, ...(second || {}) };
    return first || {};
  }

  async function waitForResponse(first = {}, second = {}) {
    const config = { ...DEFAULTS, ...parseWaitArguments(first, second) };
    const baselineInput = config.baseline;
    const baseline = baselineInput && (baselineInput.node || baselineInput.found !== undefined)
      ? baselineInput
      : { found: false, node: null, text: "", turn_id: null };
    const started = clock();
    let stableSince = null;
    let emptySince = null;
    let lastText = null;
    let observed = false;
    while (clock() - started < config.responseTimeoutMs) {
      const current = assistantSnapshot();
      const changed = isNewAssistant(current, baseline);
      if (changed) observed = true;
      if (current.text !== lastText) {
        lastText = current.text;
        stableSince = current.text ? clock() : null;
        emptySince = !current.text && observed ? clock() : null;
      }
      const generating = isGenerating();
      const elapsed = clock();
      if (observed && current.text && !generating && stableSince !== null && elapsed - stableSince >= config.stableTimeMs) {
        return { ok: true, text: current.text, turn_id: current.turn_id, elapsed_ms: Math.round(elapsed - started) };
      }
      if (observed && !current.text && !generating && emptySince !== null && elapsed - emptySince >= config.stableTimeMs) {
        throw failure("RESPONSE_EMPTY", "ChatGPT returned an empty assistant message");
      }
      await sleep(config.pollIntervalMs);
    }
    throw failure("RESPONSE_TIMEOUT", "Timed out waiting for a stable ChatGPT response");
  }

  async function chat(text, options = {}) {
    const started = clock();
    try {
      await waitForReady(options);
      const readiness = probe();
      if (!readiness.ok) throw failure(readiness.reason || "PROMPT_NOT_FOUND", `ChatGPT page is not ready: ${readiness.reason || "unknown"}`);
      const baseline = assistantSnapshot();
      await sendMessage(text, options);
      const response = await waitForResponse({ baseline, ...options });
      if (!response.text) throw failure("RESPONSE_EMPTY", "ChatGPT returned an empty assistant message");
      return { ok: true, request: text, response: response.text, url: currentUrl(), elapsed_ms: Math.round(clock() - started) };
    } catch (error) {
      return { ok: false, error: publicError(error), url: currentUrl(), elapsed_ms: Math.round(clock() - started) };
    }
  }

  root.__CODEX_CHATGPT_REVIEW__ = {
    version: VERSION,
    selectors: SELECTORS,
    probe,
    waitForReady,
    getLastAssistant,
    sendMessage,
    waitForResponse,
    chat,
  };
})(globalThis);
