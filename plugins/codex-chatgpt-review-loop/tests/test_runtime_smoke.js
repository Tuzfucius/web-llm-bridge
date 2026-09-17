const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const RUNTIME = path.join(__dirname, "..", "experimental", "native-browser", "chatgpt_runtime.js");

class FakeElement {
  constructor(kind, attrs = {}, text = "") {
    this.kind = kind;
    this.attrs = { ...attrs };
    this.innerText = text;
    this.textContent = text;
    this.disabled = false;
    this.isContentEditable = false;
    this.parentElement = null;
    this.childNodes = [];
    this.nodeType = 1;
    this.events = [];
    this.onInput = null;
  }

  getAttribute(name) { return this.attrs[name] ?? null; }
  hasAttribute(name) { return Object.prototype.hasOwnProperty.call(this.attrs, name); }
  getClientRects() { return [{}]; }
  hasChildNodes() { return this.childNodes.length > 0; }
  focus() {}
  dispatchEvent(event) { this.events.push(event); this.onInput?.(event); }
  click() {}
}

function valuePrompt() {
  const prompt = new FakeElement("prompt");
  prompt.value = "";
  return prompt;
}

function editablePrompt(text = "") {
  const prompt = new FakeElement("prompt", {}, text);
  prompt.isContentEditable = true;
  return prompt;
}

function createHarness() {
  const state = {
    prompt: valuePrompt(),
    send: new FakeElement("send"),
    stop: null,
    login: null,
    users: [],
    assistants: [],
    inputValues: [],
    execCommandMode: "failure",
    execCommands: [],
  };
  const setPromptText = (text) => {
    if (!state.prompt) return;
    state.prompt.textContent = text;
    state.prompt.innerText = text;
  };
  const document = {
    body: new FakeElement("body"),
    scrollingElement: null,
    querySelector(selector) { return this.querySelectorAll(selector)[0] || null; },
    querySelectorAll(selector) {
      if (selector === "#prompt-textarea") return state.prompt && !state.prompt.isContentEditable ? [state.prompt] : [];
      if (selector === '[contenteditable="true"][role="textbox"]') return state.prompt?.isContentEditable ? [state.prompt] : [];
      if (selector === "#composer-submit-button" || selector === '[data-testid="send-button"]' || selector === 'button[aria-label="Send prompt"]') return state.send ? [state.send] : [];
      if (selector === '[data-testid="stop-button"]' || selector === 'button[aria-label*="Stop"]') return state.stop ? [state.stop] : [];
      if (selector === 'a[href*="/auth/login"]' || selector === 'button[data-testid*="login"]' || selector === 'button[aria-label*="Log in"]' || selector === 'form[action*="/auth/login"]' || selector === 'input[type="email"]') return state.login ? [state.login] : [];
      if (selector === '[data-message-author-role="user"]') return state.users;
      if (selector === '[data-message-author-role="assistant"]') return state.assistants;
      return [];
    },
    execCommand(command, _showUI, text) {
      state.execCommands.push([command, text]);
      if (state.execCommandMode !== "success") return false;
      setPromptText(command === "insertText" ? text : "");
      return true;
    },
    createRange() { return { selectNodeContents() {} }; },
  };
  const context = {
    document,
    location: { href: "https://chatgpt.com/c/test", hostname: "chatgpt.com" },
    performance,
    setTimeout,
    clearTimeout,
    getComputedStyle: () => ({ display: "block", visibility: "visible" }),
    getSelection: () => ({ removeAllRanges() {}, addRange() {} }),
    InputEvent: class InputEvent { constructor(type, init = {}) { Object.assign(this, { type }, init); } },
    Event: class Event { constructor(type, init = {}) { Object.assign(this, { type }, init); } },
    console,
  };
  context.globalThis = context;
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(RUNTIME, "utf8"), context, { filename: RUNTIME });
  return { context, state };
}

async function assertReject(promise, code) {
  try {
    await promise;
    assert.fail(`expected ${code}`);
  } catch (error) {
    assert.equal(error.code, code);
  }
}

function configureImmediateSend(state, text = "submitted") {
  state.send = new FakeElement("send");
  state.send.click = () => {
    if (state.prompt?.isContentEditable) {
      state.prompt.textContent = "";
      state.prompt.innerText = "";
    } else if (state.prompt) state.prompt.value = "";
    state.users.push(new FakeElement("user", { "data-message-author-role": "user" }, text));
  };
}

async function main() {
  const { context, state } = createHarness();
  const runtime = context.__CODEX_CHATGPT_REVIEW__;

  let result = runtime.probe();
  assert.equal(result.ok, true);
  assert.equal(result.prompt_found, true);
  assert.equal(result.send_found, true);
  assert.equal(result.generating, false);

  state.send = null;
  result = runtime.probe();
  assert.equal(result.ok, true);
  assert.equal(result.prompt_found, true);
  assert.equal(result.send_found, false);

  state.prompt = null;
  result = runtime.probe();
  assert.equal(result.ok, false);
  assert.equal(result.reason, "PROMPT_NOT_FOUND");

  state.prompt = valuePrompt();
  state.stop = new FakeElement("stop", { "data-testid": "stop-button" });
  result = runtime.probe();
  assert.equal(result.ok, true);
  assert.equal(result.generating, true);

  state.stop = null;
  state.assistants.push(new FakeElement("assistant", { "data-message-author-role": "assistant", "data-turn-id": "turn-1" }, "hello"));
  const assistant = runtime.getLastAssistant();
  assert.equal(assistant.found, true);
  assert.equal(assistant.text, "hello");
  assert.equal(assistant.turn_id, "turn-1");

  state.assistants = [];
  state.prompt = null;
  const hydration = setTimeout(() => { state.prompt = valuePrompt(); }, 25);
  const ready = await runtime.waitForReady({ pollIntervalMs: 5, readyTimeoutMs: 200 });
  clearTimeout(hydration);
  assert.equal(ready.ok, true);
  assert.equal(ready.url, "https://chatgpt.com/c/test");

  state.prompt = null;
  await assertReject(runtime.waitForReady({ pollIntervalMs: 5, readyTimeoutMs: 30 }), "PROMPT_NOT_FOUND");

  state.login = new FakeElement("login", { href: "/auth/login" });
  await assertReject(runtime.waitForReady({ pollIntervalMs: 5, readyTimeoutMs: 200 }), "NOT_LOGGED_IN");
  state.login = null;

  state.prompt = editablePrompt();
  state.execCommandMode = "success";
  state.execCommands = [];
  state.inputValues = [];
  state.prompt.events = [];
  state.prompt.onInput = () => state.inputValues.push(state.prompt.innerText);
  state.users = [];
  configureImmediateSend(state, "contenteditable-success");
  result = await runtime.sendMessage("contenteditable-success", { pollIntervalMs: 5, readyTimeoutMs: 100, submissionTimeoutMs: 100 });
  assert.equal(result.ok, true);
  assert.deepEqual(state.execCommands.map(([command]) => command), ["delete", "insertText"]);
  assert.ok(state.inputValues.includes("contenteditable-success"));
  assert.equal(state.prompt.innerText, "");
  assert.ok(state.prompt.events.length >= 1);

  state.prompt = editablePrompt();
  state.execCommandMode = "failure";
  state.execCommands = [];
  state.inputValues = [];
  state.prompt.events = [];
  state.prompt.onInput = () => state.inputValues.push(state.prompt.innerText);
  state.users = [];
  configureImmediateSend(state, "contenteditable-fallback");
  result = await runtime.sendMessage("contenteditable-fallback", { pollIntervalMs: 5, readyTimeoutMs: 100, submissionTimeoutMs: 100 });
  assert.equal(result.ok, true);
  assert.ok(state.inputValues.includes("contenteditable-fallback"));
  assert.equal(state.prompt.textContent, "");
  assert.ok(state.prompt.events.length >= 1);

  state.assistants = [];
  state.users = [];
  state.stop = null;
  state.prompt = valuePrompt();
  state.send = null;
  result = runtime.probe();
  assert.equal(result.ok, true);
  assert.equal(result.prompt_found, true);
  assert.equal(result.send_found, false);
  state.prompt.onInput = () => {
    if (state.send) return;
    state.send = new FakeElement("send");
    state.send.click = () => {
      setTimeout(() => {
        state.prompt.value = "";
        state.users.push(new FakeElement("user", { "data-message-author-role": "user" }, "hello"));
        state.stop = new FakeElement("stop", { "data-testid": "stop-button" });
      }, 10);
      setTimeout(() => {
        state.stop = null;
        state.assistants.push(new FakeElement("assistant", { "data-message-author-role": "assistant", "data-turn-id": "turn-2" }, "CODEX_BROWSER_SMOKE_OK"));
      }, 35);
    };
  };
  result = await runtime.chat("hello", { pollIntervalMs: 5, stableTimeMs: 20, readyTimeoutMs: 100, submissionTimeoutMs: 100, responseTimeoutMs: 500 });
  assert.equal(result.ok, true);
  assert.equal(result.response, "CODEX_BROWSER_SMOKE_OK");
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
