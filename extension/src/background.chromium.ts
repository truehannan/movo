// Chromium background service worker: open the side panel on toolbar click and
// keep it available while navigating (PROMPT §3).
/* global chrome */
chrome.runtime.onInstalled.addListener(() => {
  if (chrome.sidePanel?.setPanelBehavior) {
    chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => {});
  }
});
chrome.action?.onClicked.addListener(async (tab) => {
  try {
    if (tab.windowId != null && chrome.sidePanel?.open) {
      await chrome.sidePanel.open({ windowId: tab.windowId });
    }
  } catch {
    /* ignore */
  }
});
