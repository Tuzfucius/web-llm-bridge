const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../../..");

function makeHarness(initialTabs, options = {}) {
  const tabs = new Map(initialTabs.map((tab) => [tab.id, { status: "complete", ready: true, ...tab }]));
  const updatedListeners = new Set();
  const removedListeners = new Set();
  const stats = { reload: [], create: [], events: [], pingStatuses: [] };
  let reloadStarted = false;
  let reloadReturned = false;
  let nextId = Math.max(0, ...tabs.keys()) + 1;
  const context = {
    globalThis: null,
    URL,
    setTimeout,
    clearTimeout,
    chrome: {
      tabs: {
        get: async (id) => {
          if (options.failGetDuringReloadPoll && reloadStarted && reloadReturned) throw new Error("No tab with id");
          const tab = tabs.get(id);
          if (!tab) throw new Error("No tab with id");
          return { ...tab };
        },
        query: async () => [...tabs.values()].map((tab) => ({ ...tab })),
        reload: async (id) => {
          const tab = tabs.get(id);
          if (!tab) throw new Error("No tab with id");
          stats.reload.push(id);
          if (options.staleCompleteBeforeReload) {
            stats.events.push("complete:stale");
            for (const listener of updatedListeners) listener(id, { status: "complete" }, { ...tab });
          }
          reloadStarted = true;
          tab.status = "loading";
          tab.ready = false;
          stats.events.push("loading");
          if (!options.noLoadingEvent) {
            for (const listener of updatedListeners) listener(id, { status: "loading" }, { ...tab });
          }
          if (options.closeDuringReload) {
            setTimeout(() => {
              tabs.delete(id);
              for (const listener of removedListeners) listener(id);
            }, 2);
          } else {
            setTimeout(() => {
              const current = tabs.get(id);
              if (!current) return;
              current.status = "complete";
              stats.events.push("complete");
              for (const listener of updatedListeners) listener(id, { status: "complete" }, { ...current });
            }, 2);
            setTimeout(() => {
              const current = tabs.get(id);
              if (current) current.ready = true;
            }, options.readyDelayMs || 5);
          }
          reloadReturned = true;
        },
        create: async ({ url }) => {
          const id = nextId++;
          const tab = { id, url, status: "complete", ready: true };
          tabs.set(id, tab);
          stats.create.push(url);
          return { ...tab };
        },
        sendMessage: async (id, message) => {
          const tab = tabs.get(id);
          if (!tab) throw new Error("No tab with id");
          if (message.method === "ping") stats.pingStatuses.push(tab.status);
          if (message.method !== "ping" || !tab.ready) throw new Error("Content script is not ready");
          return { ok: true, result: { ready: true } };
        },
        onUpdated: { addListener: (listener) => updatedListeners.add(listener), removeListener: (listener) => updatedListeners.delete(listener) },
        onRemoved: { addListener: (listener) => removedListeners.add(listener), removeListener: (listener) => removedListeners.delete(listener) },
      },
    },
  };
  context.globalThis = context;
  vm.createContext(context);
  for (const file of ["extension/core/utils.js", "extension/core/registry.js", "extension/core/tabs.js", "extension/providers/chatgpt/profile.js"]) {
    vm.runInContext(fs.readFileSync(path.join(root, file), "utf8"), context, { filename: file });
  }
  context.WebLLMBridge.registerProvider(context.WebLLMBridge.ChatGPTProfile);
  const bridgeTabs = context.WebLLMBridge.createTabs({ contentReadyTimeoutMs: 40, contentRetryIntervalMs: 1 });
  return { bridgeTabs, profile: context.WebLLMBridge.ChatGPTProfile, stats, listeners: { updated: updatedListeners, removed: removedListeners } };
}

async function main() {
  const profile = makeHarness([]).profile;
  assert.equal(JSON.stringify(profile.getConversationIdentity("https://chatgpt.com/c/abc/")), JSON.stringify({ kind: "conversation", id: "abc" }));
  assert.equal(JSON.stringify(profile.getConversationIdentity("https://www.chatgpt.com/c/abc?foo=bar#part")), JSON.stringify({ kind: "conversation", id: "abc" }));
  assert.equal(JSON.stringify(profile.getConversationIdentity("https://chatgpt.com/")), JSON.stringify({ kind: "root", id: null }));

  {
    const harness = makeHarness([{ id: 10, url: "https://chatgpt.com/c/abc" }]);
    const result = await harness.bridgeTabs.attach({ provider: "chatgpt", url: "https://chatgpt.com/c/abc", tab_id: 10 });
    assert.equal(result.tab_id, 10);
    assert.deepEqual(harness.stats.reload, []);
    assert.deepEqual(harness.stats.create, []);
  }
  {
    const harness = makeHarness([{ id: 20, url: "https://chatgpt.com/c/abc" }]);
    const result = await harness.bridgeTabs.attach({ provider: "chatgpt", url: "https://chatgpt.com/c/abc", tab_id: 10 });
    assert.equal(result.tab_id, 20);
    assert.deepEqual(harness.stats.reload, [20]);
    assert.deepEqual(harness.stats.create, []);
    assert.equal(harness.listeners.updated.size, 0);
    assert.equal(harness.listeners.removed.size, 0);
  }
  {
    const harness = makeHarness([{ id: 20, url: "https://chatgpt.com/c/abc?model=xxx" }]);
    const result = await harness.bridgeTabs.attach({ provider: "chatgpt", url: "https://chatgpt.com/c/abc" });
    assert.equal(result.tab_id, 20);
    assert.deepEqual(harness.stats.reload, [20]);
  }
  {
    const harness = makeHarness([{ id: 20, url: "https://www.chatgpt.com/c/abc" }]);
    const result = await harness.bridgeTabs.attach({ provider: "chatgpt", url: "https://chatgpt.com/c/abc" });
    assert.equal(result.tab_id, 20);
    assert.deepEqual(harness.stats.reload, [20]);
  }
  {
    const harness = makeHarness([{ id: 20, url: "https://chatgpt.com/c/aaa" }]);
    const result = await harness.bridgeTabs.attach({ provider: "chatgpt", url: "https://chatgpt.com/c/bbb" });
    assert.notEqual(result.tab_id, 20);
    assert.deepEqual(harness.stats.reload, []);
    assert.equal(harness.stats.create.length, 1);
  }
  {
    const harness = makeHarness([{ id: 20, url: "https://www.chatgpt.com/" }]);
    const result = await harness.bridgeTabs.attach({ provider: "chatgpt", url: "https://chatgpt.com/" });
    assert.equal(result.tab_id, 20);
    assert.deepEqual(harness.stats.reload, []);
    assert.deepEqual(harness.stats.create, []);
  }
  {
    const harness = makeHarness([{ id: 20, url: "https://chatgpt.com/c/aaa" }]);
    const result = await harness.bridgeTabs.attach({ provider: "chatgpt", url: "https://chatgpt.com/" });
    assert.notEqual(result.tab_id, 20);
    assert.deepEqual(harness.stats.reload, []);
    assert.equal(harness.stats.create.length, 1);
  }
  {
    const harness = makeHarness([{ id: 20, url: "https://chatgpt.com/c/abc" }]);
    const result = await harness.bridgeTabs.attach({ provider: "chatgpt", url: "https://chatgpt.com/c/abc", new: true, tab_id: 20 });
    assert.notEqual(result.tab_id, 20);
    assert.deepEqual(harness.stats.reload, []);
    assert.equal(harness.stats.create.length, 1);
  }
  {
    const harness = makeHarness([{ id: 20, url: "https://chatgpt.com/c/abc" }]);
    const result = await harness.bridgeTabs.attach({ provider: "chatgpt", url: "https://chatgpt.com/c/abc" });
    assert.equal(result.tab_id, 20);
  }
  {
    const harness = makeHarness([
      { id: 20, url: "https://chatgpt.com/c/abc" },
      { id: 30, url: "https://www.chatgpt.com/c/abc?model=xxx" },
    ]);
    const result = await harness.bridgeTabs.attach({ provider: "chatgpt", url: "https://chatgpt.com/c/abc" });
    assert.equal(result.tab_id, 20);
    assert.deepEqual(harness.stats.reload, [20]);
    assert.deepEqual(harness.stats.create, []);
  }
  {
    const harness = makeHarness([{ id: 20, url: "https://chatgpt.com/c/abc" }], { staleCompleteBeforeReload: true });
    const result = await harness.bridgeTabs.attach({ provider: "chatgpt", url: "https://chatgpt.com/c/abc" });
    assert.equal(result.tab_id, 20);
    assert.deepEqual(harness.stats.events, ["complete:stale", "loading", "complete"]);
    assert.equal(harness.stats.pingStatuses[0], "complete");
    assert.deepEqual(harness.stats.reload, [20]);
  }
  {
    const harness = makeHarness([{ id: 20, url: "https://chatgpt.com/c/abc" }], { noLoadingEvent: true });
    const result = await harness.bridgeTabs.attach({ provider: "chatgpt", url: "https://chatgpt.com/c/abc" });
    assert.equal(result.tab_id, 20);
    assert.deepEqual(harness.stats.events, ["loading", "complete"]);
    assert.deepEqual(harness.stats.reload, [20]);
  }
  {
    const harness = makeHarness([{ id: 20, url: "https://chatgpt.com/c/abc" }], { failGetDuringReloadPoll: true });
    await assert.rejects(
      () => harness.bridgeTabs.attach({ provider: "chatgpt", url: "https://chatgpt.com/c/abc" }),
      (error) => {
        assert.equal(error.code, "TAB_CLOSED");
        return true;
      },
    );
    assert.equal(harness.listeners.updated.size, 0);
    assert.equal(harness.listeners.removed.size, 0);
  }
  {
    const harness = makeHarness([{ id: 20, url: "https://chatgpt.com/c/abc" }], { closeDuringReload: true });
    await assert.rejects(
      () => harness.bridgeTabs.attach({ provider: "chatgpt", url: "https://chatgpt.com/c/abc" }),
      (error) => error.code === "TAB_CLOSED",
    );
    assert.equal(harness.listeners.updated.size, 0);
    assert.equal(harness.listeners.removed.size, 0);
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
