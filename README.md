# Jev Agent — browser extension

A **self-contained Chromium + Firefox side-panel browser agent** powered by
TypeSafe's **Jev** System-One decision model. You type a natural-language goal
for the current page; the agent reads the page, asks Jev for **one operation +
one target** at a time, executes it on the page, verifies, and repeats — until
the goal is done, blocked, or stopped.

No backend, no self-hosting. The extension talks to the **official Jev API**
directly using your API key, and drives the current tab itself.

```
goal → observe page → indexed interactive elements → Jev (operation + target)
     → execute on the tab → verify → observe again → next single action → …
```

Jev is the fast System-1 decision layer: it never receives the whole DOM, giant
histories, or screenshots, and never generates selectors, JavaScript, or
coordinates. The panel holds the goal and repeatedly gives Jev only the current
page's indexed elements; it picks one bounded operation and one element index.

## How it works

* **Settings** — your Jev API key, endpoint (default `https://api.typesafe.ai`),
  and model (`jev-latest`), with a **Test connection** button. Stored in the
  browser's extension storage; nothing is sent anywhere except the Jev endpoint.
* **Observation** — a content function runs in the page (via `chrome.scripting`)
  and returns a compact, indexed table of visible interactive elements (role,
  name, value, state) with a code-owned identity kept on `window`.
* **Decision** — one Jev request = an `operation` Choice (CLICK / TYPE_TEXT /
  SELECT / SCROLL_UP / SCROLL_DOWN / WAIT / DONE / BLOCKED) plus a per-operation
  `target` Choice over the current element indices. Only the target head for the
  chosen operation is used.
* **Execution** — the panel resolves the chosen index against a fresh snapshot,
  rejects stale targets, then clicks / types / selects / scrolls in the tab.
* **Verification** — the agent re-observes and checks the page actually changed
  in a way consistent with the action; `DONE` is not trusted blindly.
* **Safety** — consequential actions (buy, delete, send, submit, …) pause for
  confirmation, and **Stop** halts immediately.

## Browser support

* **Chromium** (Chrome, Chromium, Edge) — MV3 `sidePanel` (docks on the right).
* **Firefox** — MV3 `sidebar_action` (docks per Firefox's sidebar).

## Install (from a release)

Download from a GitHub Release:

* `extension.zip` — Chrome/Chromium
* `extension.xpi` — Firefox

### Chrome / Chromium

1. Unzip `extension.zip`.
2. `chrome://extensions` → **Developer mode** → **Load unpacked** → select the folder.
3. Click the toolbar icon (or `Ctrl+Shift+J`) to open the side panel on the right.
4. Open **Settings** (⚙), paste your Jev API key, click **Test connection**, Save.

### Firefox

1. `about:debugging` → **This Firefox** → **Load Temporary Add-on** → select the
   `manifest.json` inside the built folder (or the `.xpi`).
2. Open the sidebar (`Ctrl+Shift+J`), add your key in Settings, test, save.

## Get a key

Create a Jev API key at <https://console.typesafe.ai/keys>. It is used only by
your browser to call the Jev endpoint you configure.

## Development

```bash
npm install
npm run dev             # Vite dev server for the panel UI
npm run typecheck
npm test                # vitest (Jev client, decision engine, manifests)

npm run build:chrome    # extension/dist/chromium
npm run build:firefox   # extension/dist/firefox
npm run package:chrome  # dist/chrome/extension.zip
npm run package:firefox # dist/firefox/extension.xpi
```

## GitHub Actions

* **ci.yml** — typecheck, test, build both targets, validate manifests, package,
  upload artifacts.
* **release.yml** — on a `v*` tag: build/package and attach `extension.zip` +
  `extension.xpi` to a GitHub Release. No store auto-publish — download the
  artifacts and upload them to the Chrome Web Store / Firefox Add-ons yourself.

Cut a release:

```bash
git tag v1.1.0 && git push origin v1.1.0
```

## Security & privacy

* The Jev API key lives in the browser's extension storage and is sent only to
  the Jev endpoint you configure. It is never logged or bundled into the build.
* The model never emits JavaScript, selectors, or coordinates — only a bounded
  operation, an element index, and (for TYPE_TEXT) a plain string derived from
  your goal.
* Stale targets are rejected; mutations are not blindly retried.
* Consequential actions require confirmation; **Stop** halts immediately.
* `DONE` is verified against observable page state, not trusted on its own.

## Known limitations

* Firefox requires v140+ (for the data-collection manifest declaration).
* Shadow DOM, cross-origin frames, canvas, uploads, and complex keyboard
  interactions can block progress.
* Element naming covers common labels/ARIA/text, not the full accessibility tree.
* A valid action can still be the wrong action; verification, not the model's
  confidence, decides success.

## License

MIT — see [LICENSE](LICENSE). Decision architecture follows
[`browser-use/jev-ultrafast`](https://github.com/browser-use/jev-ultrafast).
Jev by [TypeSafe AI](https://docs.typesafe.ai).
