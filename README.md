# Jev Browser Agent

A **Chromium + Firefox side-panel browser agent** powered by TypeSafe's **Jev**
System-One decision model. You type a natural-language goal for the current page;
the agent reads the page, asks Jev for **one operation + one target** at a time,
executes it, verifies, and repeats — until the goal is done, blocked, or stopped.

It is built on the proven `browser-use/jev-ultrafast` decision architecture:

```
goal → observe page → indexed interactive elements → Jev (operation + target)
     → execute → verify/wait → observe again → next single action → …
```

Jev is the fast System-1 decision layer. It never receives the whole DOM, giant
histories, or screenshots, and it never generates selectors, JavaScript,
coordinates, or a full plan. The runtime holds the goal and repeatedly gives Jev
only the current page's indexed elements.

## Architecture

```
Browser Extension  (Chrome side panel / Firefox sidebar, shared React UI)
        │  loopback WebSocket + HTTP, token-authenticated
        ▼
Local Agent Service  (FastAPI, 127.0.0.1 only)
        │
        ├── Jev decision engine   one operation + per-operation target per cycle
        ├── Text helper model      generates the string for TYPE_TEXT (separate)
        ├── Browser control (CDP)  snapshot.js observation + guarded execution
        ├── Verification           independent of the model's DONE
        └── Safety policy          consequential actions require confirmation
```

Secrets (Jev key, text-model key) live **only** in the local service, never in
the extension. The extension is treated as an untrusted client: every call
carries a per-run token and an allowed origin, and the service binds loopback.

## Why Jev

Jev returns typed, calibrated decisions in ~100 ms instead of generating text.
Selecting "which operation, which element" from a bounded, indexed action space
is exactly a System-One decision, so the loop stays fast and cheap. (Benchmark
figures belong to upstream Jev/`jev-ultrafast`; this project makes no universal
performance claim of its own.)

## Browser support

* **Chromium** (Chrome, Chromium, and compatible) — Manifest V3, `sidePanel`.
* **Firefox** — Manifest V3, `sidebar_action`.

Both present a **persistent side panel/sidebar**, never a popup. X11/Wayland is
irrelevant here — this drives the browser page, not the OS.

## Install (from a release)

Download the artifacts from a GitHub Release:

* `extension.zip` — Chrome/Chromium
* `extension.xpi` — Firefox

### Chrome / Chromium

1. Unzip `extension.zip`.
2. Open `chrome://extensions` → enable **Developer mode** → **Load unpacked** →
   select the unzipped folder.
3. Click the toolbar icon (or `Ctrl+Shift+J`) to open the side panel.

### Firefox

1. Open `about:debugging` → **This Firefox** → **Load Temporary Add-on** → select
   `extension.xpi` (or the `manifest.json` inside the built folder).
2. Open the sidebar (`Ctrl+Shift+J`), or View → Sidebar → Jev Agent.

## Local backend setup

The agent service runs on your machine and holds the API keys.

```bash
git clone https://github.com/truehannan/movo
cd movo

python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env      # fill in your keys (see below)
jev-agent                 # or: python -m agent.main
```

On start it prints a URL and a **request token**. Paste both into the
extension's Settings to connect.

To control a real page, run Chrome with remote debugging so the service can
attach over CDP:

```bash
google-chrome --remote-debugging-port=9222
```

## API keys

Set these in `.env` (used only by the local service — never in the extension):

```
TYPESAFE_API_KEY=      # Jev decision model (get one at console.typesafe.ai/keys)
TEXT_MODEL_API_KEY=    # OpenAI-compatible model for TYPE_TEXT values
TEXT_MODEL=
TEXT_MODEL_BASE_URL=
AGENT_HOST=127.0.0.1
AGENT_PORT=8766
```

To run Jev locally instead of the cloud, point `TYPESAFE_BASE_URL` at a local
Laya server (same wire API).

## Development

```bash
npm install
npm run dev            # Vite dev server for the panel UI
npm run typecheck
npm test               # vitest (extension)

pytest -q              # agent tests (deterministic, no browser/network)
ruff check agent tests scripts
```

Prove the loop without a browser or key:

```bash
PYTHONPATH=. python scripts/proof_of_work.py
```

It runs the real observe→decide→act→verify loop against a scripted page with a
deterministic decider standing in for Jev, and verifies success independently.

## Testing

* **Unit** (`tests/agent`, `tests/protocol`): decision parsing, dynamic target
  filtering, stale-target rejection, safety policy, verification, task limits,
  text validation, the API protocol, and manifest generation.
* **Browser** (`tests/browser`, `tests/pages`): snapshot translation and a full
  multi-step loop against a deterministic local test page.
* **Extension** (`tests/extension`): the API client, token auth, and reconnection.

## Building & packaging

```bash
node scripts/build-extension.mjs chrome
node scripts/build-extension.mjs firefox
node scripts/package-chrome.mjs     # -> dist/chrome/extension.zip
node scripts/package-firefox.mjs    # -> dist/firefox/extension.xpi
```

## GitHub Actions

* **ci.yml** — on every push/PR: Python lint + tests, TypeScript typecheck +
  tests, build both extensions, validate both manifests, package, upload
  artifacts.
* **release.yml** — on a `v*` tag: run everything, build/package both
  extensions, and attach `extension.zip` + `extension.xpi` to a GitHub Release.
  There is **no store auto-publish** — download the artifacts and upload them to
  the Chrome Web Store / Firefox Add-ons yourself.

Cut a release:

```bash
git tag v0.1.0
git push origin v0.1.0
```

## Required GitHub secrets

None for building or releasing — the release only attaches the packaged files.
The runtime keys (`TYPESAFE_API_KEY`, `TEXT_MODEL_API_KEY`) belong in your local
`.env`, not in CI or the extension.

## Security model

* API secrets stay server-side; the extension never sees them.
* The service binds `127.0.0.1` by default and checks Host/Origin plus a random
  per-run token on every request.
* Consequential actions (buy, delete, send, submit, …) pause for confirmation.
* Stale targets are rejected: a mutation is never executed against a page that
  changed since the decision was made, and mutations are never blindly retried.
* The model never emits JavaScript, shell, selectors, or coordinates — only a
  bounded operation, an element index, and (for TYPE_TEXT) a validated string.
* `DONE` is not trusted; task success is verified independently.

## Known limitations

* Needs the local agent service running, and Chrome started with
  `--remote-debugging-port` for real-page control.
* Shadow DOM, cross-origin frames, canvas, uploads, and complex keyboard
  interactions can block progress.
* Element naming covers common labels/ARIA/text, not the browser's full
  accessibility algorithm.
* A valid action can still be the wrong action; independent verification, not the
  model's confidence, decides success.

## License

MIT — see [LICENSE](LICENSE). Decision architecture follows
[`browser-use/jev-ultrafast`](https://github.com/browser-use/jev-ultrafast).
Jev by [TypeSafe AI](https://docs.typesafe.ai).
