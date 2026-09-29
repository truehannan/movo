// Firefox background: the sidebar is opened by the browser action / command.
// A minimal script keeps a place for future messaging without duplicating the
// authoritative browser-control path (that lives in the local agent service).
/* global browser */
browser.runtime.onInstalled.addListener(() => {
  // no-op; sidebar_action + command handle opening the sidebar.
});
