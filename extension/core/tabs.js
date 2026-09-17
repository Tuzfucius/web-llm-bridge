(function (root) {
  "use strict";
  const bridge = (root.WebLLMBridge = root.WebLLMBridge || {});

  bridge.createTabs = function createTabs(timing) {
    const readyTimeoutMs = Number.isFinite(timing?.contentReadyTimeoutMs) ? timing.contentReadyTimeoutMs : 30_000;
    const retryIntervalMs = Number.isFinite(timing?.contentRetryIntervalMs) ? timing.contentRetryIntervalMs : 200;

    async function get(tabId) {
      if (!Number.isInteger(tabId)) throw bridge.error("TAB_CLOSED", "The bound tab does not exist", true);
      try {
        return await chrome.tabs.get(tabId);
      } catch (_error) {
        throw bridge.error("TAB_CLOSED", "The bound tab has been closed", true);
      }
    }

    async function close(tabId) {
      if (!Number.isInteger(tabId)) throw bridge.error("TAB_CLOSED", "The bound tab does not exist", true);
      try {
        await chrome.tabs.remove(tabId);
      } catch (error) {
        const message = String(error?.message || error || "");
        if (/no tab|not found|does not exist|closed|不存在|已关闭/i.test(message)) return { tab_id: tabId, closed: true };
        throw bridge.error("CONTENT_SCRIPT_UNAVAILABLE", "Unable to close the bound tab");
      }
      return { tab_id: tabId, closed: true };
    }

    async function waitForContent(tabId) {
      const deadline = Date.now() + readyTimeoutMs;
      while (Date.now() < deadline) {
        await get(tabId);
        try {
          const response = await chrome.tabs.sendMessage(tabId, { method: "ping" });
          if (response?.ok && response.result?.ready) return;
        } catch (_error) {}
        await bridge.sleep(retryIntervalMs);
      }
      throw bridge.error("PAGE_NOT_READY", "The content script did not become ready in time");
    }

    function conversationIdentity(provider, value) {
      try {
        if (!provider.matchesUrl(value || "")) return null;
        if (typeof provider.getConversationIdentity === "function") {
          return provider.getConversationIdentity(value);
        }
        const normalized = provider.normalizeUrl(value);
        return normalized ? { kind: "url", id: normalized } : null;
      } catch (_error) {
        return null;
      }
    }

    function sameConversation(provider, targetUrl, candidateUrl) {
      const target = conversationIdentity(provider, targetUrl);
      const candidate = conversationIdentity(provider, candidateUrl);
      return Boolean(target && candidate && target.kind === candidate.kind && target.id === candidate.id);
    }

    function isRootTarget(provider, value) {
      if (typeof provider.isRootTarget === "function") return provider.isRootTarget(value) === true;
      return conversationIdentity(provider, value)?.kind === "root";
    }

    async function findRequestedTab(provider, targetUrl, requestedId) {
      if (!Number.isInteger(requestedId)) return null;
      let tab;
      try {
        tab = await get(requestedId);
      } catch (_error) {
        return null;
      }
      if (!provider.matchesUrl(tab.url || "") || !sameConversation(provider, targetUrl, tab.url || "")) return null;
      return tab;
    }

    async function queryTabs() {
      if (typeof chrome.tabs?.query !== "function") return [];
      const tabs = await chrome.tabs.query({});
      return Array.isArray(tabs) ? tabs : [];
    }

    async function findConversationTab(provider, targetUrl) {
      const target = conversationIdentity(provider, targetUrl);
      if (!target || target.kind === "root") return null;
      const tabs = await queryTabs();
      return tabs.find((tab) => Number.isInteger(tab.id)
        && provider.matchesUrl(tab.url || "")
        && sameConversation(provider, targetUrl, tab.url || "")) || null;
    }

    async function findReusableRootTab(provider, targetUrl) {
      if (!isRootTarget(provider, targetUrl)) return null;
      const tabs = await queryTabs();
      return tabs.find((tab) => Number.isInteger(tab.id)
        && provider.matchesUrl(tab.url || "")
        && isRootTarget(provider, tab.url || "")) || null;
    }

    async function normalizeReloadError(error, tabId) {
      if (error?.code) return error;
      try {
        await chrome.tabs.get(tabId);
        return bridge.error("PAGE_NOT_READY", "The tab could not be reloaded", true);
      } catch (_getError) {
        return bridge.error("TAB_CLOSED", "The tab was closed while reloading", true);
      }
    }

    async function waitForReload(tabId) {
      const onUpdated = chrome.tabs?.onUpdated;
      const onRemoved = chrome.tabs?.onRemoved;
      if (!onUpdated?.addListener || !onRemoved?.addListener) {
        try {
          await chrome.tabs.reload(tabId);
        } catch (error) {
          throw await normalizeReloadError(error, tabId);
        }
        return;
      }

      await new Promise((resolve, reject) => {
        let settled = false;
        let seenLoading = false;
        let reloadReturned = false;
        let completeFallbackChecks = 0;
        let pollTimer = null;
        const timer = root.setTimeout(() => finishFailure(bridge.error("PAGE_NOT_READY", "The tab reload did not complete in time")), readyTimeoutMs);
        const cleanup = () => {
          root.clearTimeout(timer);
          if (pollTimer !== null) root.clearTimeout(pollTimer);
          onUpdated.removeListener(handleUpdated);
          onRemoved.removeListener(handleRemoved);
        };
        const finishSuccess = () => {
          if (settled) return;
          settled = true;
          cleanup();
          resolve();
        };
        const finishFailure = (error) => {
          if (settled) return;
          settled = true;
          cleanup();
          reject(error);
        };
        const handleUpdated = (updatedId, changeInfo) => {
          if (updatedId !== tabId) return;
          if (changeInfo?.status === "loading") {
            seenLoading = true;
            return;
          }
          if (changeInfo?.status === "complete" && seenLoading) finishSuccess();
        };
        const handleRemoved = (removedId) => {
          if (removedId === tabId) finishFailure(bridge.error("TAB_CLOSED", "The tab was closed while reloading", true));
        };
        const inspectCurrentState = async () => {
          if (settled || !reloadReturned) return;
          try {
            const current = await get(tabId);
            if (current.status === "loading") {
              seenLoading = true;
              completeFallbackChecks = 0;
            } else if (current.status === "complete") {
              if (seenLoading) {
                finishSuccess();
                return;
              }
              // A few Chrome versions do not emit loading for reload. Require
              // two post-reload complete observations so a stale event cannot
              // finish the wait in the same turn as reload().
              completeFallbackChecks += 1;
              if (completeFallbackChecks >= 2) {
                finishSuccess();
                return;
              }
            }
            if (!settled) {
              pollTimer = root.setTimeout(() => {
                pollTimer = null;
                inspectCurrentState();
              }, retryIntervalMs);
            }
          } catch (error) {
            finishFailure(normalizeReloadError(error, tabId));
          }
        };
        onUpdated.addListener(handleUpdated);
        onRemoved.addListener(handleRemoved);
        (async () => {
          try {
            await chrome.tabs.reload(tabId);
            reloadReturned = true;
            await inspectCurrentState();
          } catch (error) {
            finishFailure(await normalizeReloadError(error, tabId));
          }
        })();
      });
    }

    async function reloadAndWait(tabId) {
      await waitForReload(tabId);
      await waitForContent(tabId);
    }

    async function attachExistingTab(tab, fallbackUrl, ready = false) {
      if (!ready) await waitForContent(tab.id);
      const current = await get(tab.id);
      return { tab_id: current.id, url: current.url || fallbackUrl, provider: tab.provider };
    }

    async function createTab(provider, url) {
      const tab = await chrome.tabs.create({ url, active: true });
      if (!Number.isInteger(tab?.id)) throw bridge.error("PAGE_NOT_READY", "Unable to create a tab");
      const current = await get(tab.id);
      await waitForContent(tab.id);
      return { tab_id: current.id, url: (await get(tab.id)).url || url, provider: provider.id };
    }

    async function attach(params) {
      const provider = bridge.getProvider(params?.provider);
      if (!provider) throw bridge.error("PROVIDER_NOT_FOUND", "The requested provider is not registered");
      const url = typeof params?.url === "string" ? params.url : provider.defaultUrl;
      if (typeof url !== "string" || !provider.matchesUrl(url)) throw bridge.error("INVALID_URL", "The URL is not supported by this provider");

      // new=true is deliberately an unconditional create and skips every reuse level.
      if (params?.new === true) return createTab(provider, url);

      const requested = await findRequestedTab(provider, url, params?.tab_id);
      if (requested) return attachExistingTab({ ...requested, provider: provider.id }, url);

      const conversation = await findConversationTab(provider, url);
      if (conversation) {
        await reloadAndWait(conversation.id);
        return attachExistingTab({ ...conversation, provider: provider.id }, url, true);
      }

      const rootTab = await findReusableRootTab(provider, url);
      if (rootTab) return attachExistingTab({ ...rootTab, provider: provider.id }, url);

      return createTab(provider, url);
    }

    async function request(method, params) {
      const tabId = params?.tab_id;
      const requested = bridge.getProvider(params?.provider);
      if (!requested) throw bridge.error("PROVIDER_NOT_FOUND", "The requested provider is not registered");
      const tab = await get(tabId);
      const provider = bridge.detectProvider(tab.url || "");
      if (!provider || provider.id !== requested.id) throw bridge.error("INVALID_URL", "The tab does not match the requested provider");
      await waitForContent(tabId);
      const dispatched = method === "chat";
      try {
        const message = { method, request_id: params?.request_id };
        if (method === "chat") message.text = params?.text;
        else if (method === "get_messages") { message.limit = params?.limit; message.full = params?.full === true; }
        else if (method === "get_artifact") message.artifact = params?.artifact;
        const response = await chrome.tabs.sendMessage(tabId, message);
        if (!response?.ok) {
          const error = response?.error || {};
          throw bridge.error(error.code || "CONTENT_SCRIPT_UNAVAILABLE", error.message || "The content script returned an invalid response");
        }
        return { ...(response.result || {}), url: (await get(tabId)).url || "", provider: provider.id, tab_id: tabId };
      } catch (error) {
        const normalized = error?.code ? error : bridge.error("CONTENT_SCRIPT_UNAVAILABLE", "Unable to message the content script");
        if (dispatched && ["TAB_CLOSED", "CONTENT_SCRIPT_UNAVAILABLE", "EXTENSION_NOT_CONNECTED"].includes(normalized.code)) {
          throw bridge.error("CHAT_STATE_UNKNOWN", "The message may have been submitted, but its final state cannot be confirmed", false);
        }
        throw normalized;
      }
    }

    return { attach, request, get, close, waitForContent, reloadAndWait };
  };
})(globalThis);
