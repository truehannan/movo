// Functions injected into the active tab to observe and act on the page.
// These run in the PAGE context (via chrome.scripting.executeScript), so they
// must be self-contained. The side panel calls them through pageDriver.ts.
//
// Observation mirrors the Python snapshot.js: a compact, indexed table of
// visible interactive elements with a code-owned identity kept on window.

/* eslint-disable @typescript-eslint/no-explicit-any */

// --- snapshot (runs in page) ------------------------------------------------
export function pageSnapshot(): string {
  const MAX_ELEMENTS = 250;
  const w = window as any;
  const g = (w.__jevAgent = w.__jevAgent || { nodes: {}, seq: 0 });
  g.nodes = {};

  const EDITABLE = new Set(["text", "search", "email", "url", "tel", "password", "number", "", undefined]);
  const NON_EDIT = new Set(["checkbox", "radio", "button", "submit", "reset", "file", "image", "range", "color"]);

  function visible(el: Element): boolean {
    const r = (el as HTMLElement).getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) return false;
    const s = getComputedStyle(el as HTMLElement);
    if (s.visibility === "hidden" || s.display === "none" || s.opacity === "0") return false;
    if (r.bottom < 0 || r.top > (window.innerHeight || 0) * 2) return false;
    return true;
  }
  function name(el: Element): string {
    const e = el as HTMLElement;
    const aria = e.getAttribute("aria-label");
    if (aria && aria.trim()) return aria.trim();
    if (e.id) {
      const lab = document.querySelector(`label[for="${CSS.escape(e.id)}"]`);
      if (lab && lab.textContent?.trim()) return lab.textContent.trim();
    }
    const wrap = e.closest("label");
    if (wrap && wrap.textContent?.trim()) return wrap.textContent.trim();
    if (e.getAttribute("placeholder")) return e.getAttribute("placeholder")!.trim();
    if (e.getAttribute("title")) return e.getAttribute("title")!.trim();
    if (e.getAttribute("name")) return e.getAttribute("name")!.trim();
    return (e.textContent || "").trim().replace(/\s+/g, " ").slice(0, 120);
  }
  function role(el: Element): string {
    const e = el as HTMLElement;
    const explicit = e.getAttribute("role");
    if (explicit) return explicit.toLowerCase();
    const tag = e.tagName.toLowerCase();
    if (tag === "a" && e.hasAttribute("href")) return "link";
    if (tag === "button") return "button";
    if (tag === "select") return "combobox";
    if (tag === "textarea") return "textbox";
    if (tag === "input") {
      const t = ((e as HTMLInputElement).getAttribute("type") || "text").toLowerCase();
      if (t === "checkbox") return "checkbox";
      if (t === "radio") return "radio";
      if (t === "submit" || t === "button" || t === "reset") return "button";
      return "textbox";
    }
    return tag;
  }

  const out: any[] = [];
  const fp: string[] = [];
  const all = document.querySelectorAll("a[href], button, input, textarea, select, [role], [tabindex], [contenteditable]");
  for (const el of Array.from(all)) {
    if (out.length >= MAX_ELEMENTS) break;
    if (!visible(el)) continue;
    const e = el as HTMLElement;
    const r = role(el);
    const tag = e.tagName.toLowerCase();
    const disabled = e.hasAttribute("disabled");
    let canClick = false, canType = false, canSelect = false;
    if (["link", "button", "tab", "menuitem", "checkbox", "radio", "option"].includes(r)) canClick = true;
    if (r === "textbox" || (e as any).isContentEditable) canType = true;
    if (tag === "input") {
      const t = ((e as HTMLInputElement).getAttribute("type") || "text").toLowerCase();
      if (NON_EDIT.has(t)) { canType = false; canClick = true; }
      else if (EDITABLE.has(t)) canType = true;
    }
    if (tag === "select") canSelect = true;
    if (!canClick && !canType && !canSelect) continue;

    const index = g.seq++;
    g.nodes[index] = el;
    const value = "value" in e && typeof (e as any).value === "string" ? (e as any).value : null;
    let checked: boolean | null = null;
    if ((e as HTMLInputElement).type === "checkbox" || (e as HTMLInputElement).type === "radio" || r === "checkbox" || r === "radio")
      checked = !!(e as HTMLInputElement).checked;
    let options: string[] = [];
    if (tag === "select") options = Array.from((e as HTMLSelectElement).options).map((o) => (o.textContent || "").trim());
    const nm = name(el);
    out.push({ index, role: r, name: nm, value, checked, disabled, editable: canType, can_click: canClick, can_type: canType, can_select: canSelect, options });
    fp.push(`${r}:${nm}:${value ?? ""}:${checked ?? ""}`);
  }
  const fingerprint = `${location.href}|${document.title}|${out.length}|${fp.slice(0, 40).join("|")}`;
  return JSON.stringify({ url: location.href, title: document.title, fingerprint, elements: out });
}

// --- actions (run in page); each takes the element index ---
export function pageClick(index: number): boolean {
  const n = (window as any).__jevAgent?.nodes?.[index];
  if (!n) return false;
  n.scrollIntoView({ block: "center" });
  n.click();
  return true;
}
export function pageType(index: number, text: string): boolean {
  const n = (window as any).__jevAgent?.nodes?.[index];
  if (!n) return false;
  n.focus();
  if (typeof n.select === "function") n.select();
  n.value = text;
  n.dispatchEvent(new Event("input", { bubbles: true }));
  n.dispatchEvent(new Event("change", { bubbles: true }));
  return true;
}
export function pageSelect(index: number, optionIndex: number): boolean {
  const n = (window as any).__jevAgent?.nodes?.[index];
  if (!n) return false;
  n.selectedIndex = optionIndex;
  n.dispatchEvent(new Event("change", { bubbles: true }));
  return true;
}
export function pageScroll(dy: number): boolean {
  window.scrollBy(0, dy);
  return true;
}
export function pageHighlight(index: number): boolean {
  const n = (window as any).__jevAgent?.nodes?.[index] as HTMLElement | undefined;
  if (!n) return false;
  const prev = n.style.outline;
  n.style.outline = "2px solid #5b8cff";
  setTimeout(() => { n.style.outline = prev; }, 500);
  return true;
}
