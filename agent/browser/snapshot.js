// snapshot.js — the browser-side DOM observation (PROMPT §10, §13).
//
// Adapted from browser-use/jev-ultrafast's snapshot approach: one pass over the
// document produces a compact, indexed table of *visible, interactive* elements
// with common HTML/ARIA roles, accessible names, values and state. A WeakMap
// gives each live node a stable, code-owned identity (NOT a CDP backend id);
// a plain object maps that identity to the live node for execution. Replaced
// nodes get new identities and disconnected ones are pruned on each call.
//
// It returns JSON: { url, title, fingerprint, elements: [...] }.
// It never returns raw HTML, scripts, styles, or hidden/irrelevant content.

(() => {
  const MAX_ELEMENTS = 250;

  // Persistent identity + live-node registry across snapshots for this page.
  const g = window.__jevAgent || (window.__jevAgent = {
    ids: new WeakMap(),
    nodes: {},      // index -> live node (rebuilt each snapshot)
    seq: 0,
  });
  g.nodes = {};

  const EDITABLE_TYPES = new Set([
    "text", "search", "email", "url", "tel", "password", "number", "", undefined,
  ]);
  const NON_EDITABLE_INPUT = new Set([
    "checkbox", "radio", "button", "submit", "reset", "file", "image", "range", "color",
  ]);

  function visible(el) {
    const r = el.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) return false;
    const s = getComputedStyle(el);
    if (s.visibility === "hidden" || s.display === "none" || s.opacity === "0") return false;
    // Must intersect the viewport (allow just-below-fold within a screen).
    if (r.bottom < 0 || r.top > (window.innerHeight || 0) + window.innerHeight) return false;
    return true;
  }

  function accessibleName(el) {
    const aria = el.getAttribute("aria-label");
    if (aria && aria.trim()) return aria.trim();
    const labelledby = el.getAttribute("aria-labelledby");
    if (labelledby) {
      const parts = labelledby.split(/\s+/).map((id) => {
        const n = document.getElementById(id);
        return n ? n.textContent.trim() : "";
      });
      const joined = parts.filter(Boolean).join(" ").trim();
      if (joined) return joined;
    }
    if (el.id) {
      const lab = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (lab && lab.textContent.trim()) return lab.textContent.trim();
    }
    const wrapLabel = el.closest("label");
    if (wrapLabel && wrapLabel.textContent.trim()) return wrapLabel.textContent.trim();
    if (el.getAttribute("placeholder")) return el.getAttribute("placeholder").trim();
    if (el.getAttribute("title")) return el.getAttribute("title").trim();
    if (el.getAttribute("name")) return el.getAttribute("name").trim();
    const txt = (el.textContent || "").trim().replace(/\s+/g, " ");
    return txt.slice(0, 120);
  }

  function roleOf(el) {
    const explicit = el.getAttribute("role");
    if (explicit) return explicit.toLowerCase();
    const tag = el.tagName.toLowerCase();
    if (tag === "a" && el.hasAttribute("href")) return "link";
    if (tag === "button") return "button";
    if (tag === "select") return "combobox";
    if (tag === "textarea") return "textbox";
    if (tag === "input") {
      const t = (el.getAttribute("type") || "text").toLowerCase();
      if (t === "checkbox") return "checkbox";
      if (t === "radio") return "radio";
      if (t === "submit" || t === "button" || t === "reset") return "button";
      return "textbox";
    }
    return tag;
  }

  function isInteractive(el, role) {
    if (el.hasAttribute("disabled")) return { click: false, type: false, select: false, disabled: true };
    const tag = el.tagName.toLowerCase();
    const tabbable = el.tabIndex >= 0;
    let click = false, type = false, select = false;
    if (role === "link" || role === "button" || role === "tab" || role === "menuitem" ||
        role === "checkbox" || role === "radio" || role === "option") {
      click = true;
    }
    if (role === "textbox" || el.isContentEditable) {
      type = true;
    }
    if (tag === "input") {
      const t = (el.getAttribute("type") || "text").toLowerCase();
      if (NON_EDITABLE_INPUT.has(t)) { type = false; click = true; }
      else if (EDITABLE_TYPES.has(t)) { type = true; }
    }
    if (tag === "select") { select = true; }
    if (role === "combobox" && (el.getAttribute("aria-autocomplete") || el.isContentEditable)) {
      type = true;
    }
    if (!click && !type && !select && (el.onclick || tabbable) &&
        (tag === "div" || tag === "span" || role === "button")) {
      click = true;
    }
    return { click, type, select, disabled: false };
  }

  const results = [];
  const all = document.querySelectorAll(
    "a[href], button, input, textarea, select, [role], [tabindex], [contenteditable]"
  );
  const fp = [];
  for (const el of all) {
    if (results.length >= MAX_ELEMENTS) break;
    if (!visible(el)) continue;
    const role = roleOf(el);
    const caps = isInteractive(el, role);
    if (!caps.click && !caps.type && !caps.select) continue;

    const index = g.seq++;
    g.ids.set(el, index);
    g.nodes[index] = el;

    let value = null;
    if ("value" in el && typeof el.value === "string") value = el.value;
    let checked = null;
    if (el.type === "checkbox" || el.type === "radio" || role === "checkbox" || role === "radio") {
      checked = !!el.checked;
    }
    let options = [];
    let selected = null;
    if (el.tagName.toLowerCase() === "select") {
      options = Array.from(el.options).map((o) => (o.textContent || "").trim());
      selected = el.selectedIndex;
    }
    const name = accessibleName(el);
    results.push({
      index, role, name,
      value, checked, selected, options,
      editable: caps.type,
      disabled: caps.disabled,
      can_click: caps.click, can_type: caps.type, can_select: caps.select,
    });
    fp.push(`${role}:${name}:${value ?? ""}:${checked ?? ""}`);
  }

  const fingerprint = `${location.href}|${document.title}|${results.length}|` +
    fp.slice(0, 40).join("|");

  return JSON.stringify({
    url: location.href,
    title: document.title,
    fingerprint,
    elements: results,
  });
})();
