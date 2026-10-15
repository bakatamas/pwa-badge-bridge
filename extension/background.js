// PWA Badge Bridge — reads unread counts from tab titles of configured sites
// and forwards them to the native host, which sets the KDE taskbar badge.

const HOST = "hu.celest.pwa_badge_bridge";
const ZERO_DELAY_MS = 3000; // ignore brief title changes (e.g. "X sent a message")

let port = null;
let sites = [];            // [{host, desktop, regex: RegExp}]
let tabCounts = {};        // desktop -> {tabId: count}
let tabDesktop = {};       // tabId -> desktop it is counted under
let lastSent = {};         // desktop -> count last sent to the host
let zeroTimers = {};       // tabId -> timeout

function resetState() {
  Object.values(zeroTimers).forEach(clearTimeout);
  tabCounts = {};
  tabDesktop = {};
  lastSent = {};  // a new host process starts with no badges, so resend everything
  zeroTimers = {};
}

function connect() {
  port = chrome.runtime.connectNative(HOST);
  port.onMessage.addListener((msg) => {
    if (msg.type === "config") {
      resetState();
      sites = [];
      for (const s of msg.sites) {
        try {
          sites.push({ ...s, regex: new RegExp(s.regex || "^\\((\\d+)\\)") });
        } catch (e) {
          console.warn(`Skipping ${s.host}: invalid regex`, e);
        }
      }
      scanAllTabs();
    }
  });
  port.onDisconnect.addListener(() => {
    console.warn("Native host disconnected:", chrome.runtime.lastError?.message);
    port = null;
    setTimeout(connect, 5000);
  });
  port.postMessage({ type: "hello" });
}

function siteFor(url) {
  try {
    const h = new URL(url).hostname;
    return sites.find((s) => h === s.host || h.endsWith("." + s.host));
  } catch {
    return null;
  }
}

function publish(desktop) {
  const counts = Object.values(tabCounts[desktop] || {});
  const count = counts.length ? Math.max(...counts) : 0;
  if (lastSent[desktop] === count || !port) return;
  lastSent[desktop] = count;
  port.postMessage({ type: "count", desktop, count });
}

function removeTab(tabId) {
  clearTimeout(zeroTimers[tabId]);
  delete zeroTimers[tabId];
  const desktop = tabDesktop[tabId];
  if (desktop === undefined) return;
  delete tabDesktop[tabId];
  delete tabCounts[desktop][tabId];
  publish(desktop);
}

function setTabCount(tabId, site, count) {
  if (tabDesktop[tabId] !== site.desktop) removeTab(tabId); // tab moved to another site
  tabDesktop[tabId] = site.desktop;
  (tabCounts[site.desktop] ??= {})[tabId] = count;
  publish(site.desktop);
}

function handleTab(tab) {
  const site = tab.url ? siteFor(tab.url) : null;
  if (!site) {
    removeTab(tab.id);
    return;
  }
  const m = (tab.title || "").match(site.regex);
  clearTimeout(zeroTimers[tab.id]);
  if (m) {
    setTabCount(tab.id, site, parseInt(m[1], 10) || 0);
  } else {
    zeroTimers[tab.id] = setTimeout(() => setTabCount(tab.id, site, 0), ZERO_DELAY_MS);
  }
}

async function scanAllTabs() {
  for (const tab of await chrome.tabs.query({})) handleTab(tab);
}

chrome.tabs.onUpdated.addListener((tabId, info, tab) => {
  if (info.title !== undefined || info.url !== undefined) handleTab(tab);
});
chrome.tabs.onRemoved.addListener(removeTab);
// Chrome can swap a tab's id (e.g. after prerendering); drop the old id's count.
chrome.tabs.onReplaced.addListener((addedTabId, removedTabId) => removeTab(removedTabId));
// Makes sure the service worker starts with the browser.
chrome.runtime.onStartup.addListener(() => {});

connect();
