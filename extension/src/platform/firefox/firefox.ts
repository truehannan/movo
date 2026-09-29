// Firefox adapter (PROMPT §4): tabs, storage, sidebar_action live here.

import type { BrowserPlatform, BrowserTab } from "../platform";

declare const browser: any;

export class FirefoxPlatform implements BrowserPlatform {
  readonly name = "firefox" as const;

  async getActiveTab(): Promise<BrowserTab> {
    const tabs = await browser.tabs.query({ active: true, currentWindow: true });
    const t = tabs && tabs[0];
    return { id: t?.id ?? null, url: t?.url ?? "", title: t?.title ?? "" };
  }

  async storageGet<T>(key: string, fallback: T): Promise<T> {
    const obj = await browser.storage.local.get(key);
    return (obj?.[key] as T) ?? fallback;
  }

  async storageSet<T>(key: string, value: T): Promise<void> {
    await browser.storage.local.set({ [key]: value });
  }

  async ensureHostAccess(): Promise<boolean> {
    try {
      const req = { origins: ["<all_urls>"] };
      if (await browser.permissions.contains(req)) return true;
      return await browser.permissions.request(req);
    } catch {
      return true;
    }
  }
}
