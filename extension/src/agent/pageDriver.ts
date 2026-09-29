// Page driver: runs the in-page observe/act functions in the active tab via
// chrome.scripting.executeScript. This is the extension's execution layer
// (no local backend). Firefox exposes the same API under `browser.scripting`.

import type { Observation } from "./engine";
import { pageClick, pageHighlight, pageScroll, pageSelect, pageSnapshot, pageType } from "./inpage";

/* eslint-disable @typescript-eslint/no-explicit-any */
function scripting(): any {
  const g = globalThis as any;
  return g.browser?.scripting ?? g.chrome?.scripting;
}

async function exec<Args extends any[], R>(
  tabId: number,
  fn: (...args: Args) => R,
  args: Args,
): Promise<R | undefined> {
  const results = await scripting().executeScript({
    target: { tabId },
    func: fn as any,
    args: args as any,
    world: "MAIN", // run in the page's world so our window.__jevAgent persists
  });
  return results?.[0]?.result as R | undefined;
}

export class PageDriver {
  constructor(private tabId: number) {}

  async observe(): Promise<Observation> {
    const raw = await exec(this.tabId, pageSnapshot, []);
    return raw ? (JSON.parse(raw) as Observation) : { url: "", title: "", fingerprint: "", elements: [] };
  }
  async click(index: number): Promise<boolean> {
    return (await exec(this.tabId, pageClick, [index])) ?? false;
  }
  async type(index: number, text: string): Promise<boolean> {
    return (await exec(this.tabId, pageType, [index, text])) ?? false;
  }
  async select(index: number, optionIndex: number): Promise<boolean> {
    return (await exec(this.tabId, pageSelect, [index, optionIndex])) ?? false;
  }
  async scroll(dy: number): Promise<boolean> {
    return (await exec(this.tabId, pageScroll, [dy])) ?? false;
  }
  async highlight(index: number): Promise<void> {
    await exec(this.tabId, pageHighlight, [index]);
  }
}
