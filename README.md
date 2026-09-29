<p align="center">
  <img src="public/movo.png" alt="Movo" width="120" />
</p>

<h1 align="center">Movo</h1>

<p align="center">
  A compact, floating <strong>Linux desktop computer-use agent</strong> powered by
  <a href="https://docs.typesafe.ai">TypeSafe AI's <strong>Jev</strong> System One decision model</a>.
</p>

Jev is not a chatbot and this is not a "screenshot → giant prompt → instructions"
agent. Jev makes **bounded, typed decisions** with calibrated confidence, and
ordinary application code owns the workflow, the side effects, and the safety:

```
desktop → observation → structured state → candidate generation
       → Jev typed decision → executor → verification → next observation
```

> Jev is the fast decision-making brain; this software gives it eyes, hands, a
> memory of the current task, and safety.

## How it works

```
USER
  ↓  floating PySide6 panel
Task Controller  →  Planner (goal → text/key arguments, no Jev)
  ↓
Agent Loop:  observe → decide → act → verify
  │
  ├─ Desktop Observer   AT-SPI accessibility tree, active window, focus
  ├─ Candidate Builder  filter + rank + serialize to 5–20 typed candidates
  ├─ Jev Decision Engine  one call, typed questions:
  │      • operation   Choice   (CLICK / TYPE / PRESS_KEY / SCROLL / WAIT / DONE / BLOCKED / …)
  │      • target      Choice   (candidate id or NONE)
  │      • continue    Noul     (more steps needed?)
  │      • safe        Noul     (safe & grounded to execute?)
  ├─ Action Executor    real mouse / keyboard / scroll / drag (pynput, xdotool fallback)
  └─ Verifier           re-observe and confirm the desktop actually changed
```

Everything deterministic — visibility, enabled state, coordinate extraction,
candidate filtering, retries, loop detection, emergency stop, destructive-action
confirmation — is handled in code. Jev is only asked the semantic questions.

### Why this shape

* **One Jev call per step** carries several typed questions evaluated in
  parallel (operation, target, continue, safe), keeping latency and tokens low.
* **Compact state**: goal, current app/window, a serialized candidate block, and
  a short recent-action history — hundreds of tokens, not thousands.
* **The candidate id is the bridge**: Jev can only pick an id the local builder
  produced, so it can never hallucinate a target or generate coordinates.

## Install

Download the `.deb` from a release (or build it — see below) and install:

```sh
sudo apt install ./movo_0.1.0_all.deb
```

Then launch **Movo** from your app menu. On first run, open
Settings, paste your TypeSafe/Jev API key, and click **Test Connection**.

Get a key and free credit at <https://console.typesafe.ai/keys>.

> **First launch** downloads the Python UI/runtime dependencies (PySide6,
> typesafe-sdk, mss, pynput) into a per-user virtualenv at
> `~/.local/share/movo/venv`. This is done on first run — *not* during
> `apt install` — so the package manager never blocks on a network download,
> and it needs **no sudo** (it installs into your home, not the system path).
> If you are offline on first run, install them later with:
>
> ```sh
> movo --setup
> ```

### Requirements

* Linux with an **X11** session (Wayland support depends on the backend)
* AT-SPI accessibility enabled (`at-spi2-core`, `python3-gi`, `gir1.2-atspi-2.0`)
* Internet access on first launch for the isolated virtualenv
  (`PySide6`, `typesafe-sdk`, `mss`, `pynput`).

## Usage

Type a natural-language goal, for example:

* `Open Firefox and search for "Python 3.14"`
* `Open GitHub and find the Issues section`
* `Create a folder called Hackathon`
* `Open my project and find the README`

Watch the panel show each step: the observed app, Jev's chosen operation and
target, its confidence, a transient highlight over the real element, and a
`✓ VERIFIED` once the desktop changes.

**Safety**: press **Esc** at any time for an emergency stop, or click **Stop**.
Destructive actions (delete, shutdown, `sudo`, `rm -rf`, payments, …) are never
executed automatically — they require explicit confirmation.

## Development

```sh
python3 -m venv --system-site-packages .venv   # system-site for python3-gi (AT-SPI)
. .venv/bin/activate
pip install -e ".[dev]"
pip install PySide6-Essentials                  # for the UI

pytest -q            # deterministic tests: no real desktop, no network
ruff check app tests
```

The agent loop is fully testable without a real desktop or network: a
`MockDesktopBackend` scripts observations and a scripted Jev client returns
canned typed answers. See `tests/`.

### Layout

```
app/
  main.py            entry point
  ui/                window, panel, settings, overlay, styles  (PySide6)
  agent/             controller, planner, loop, verifier, history
  jev/               client, questions, schemas  (typesafe-sdk)
  desktop/           backend interface, x11_backend, candidates, mock_backend
  safety/            policy, confirmation, emergency_stop
  config/            settings, secrets  (keyring / restricted file)
  diagnostics/       capabilities, logging
packaging/deb/       Debian package tree + build/validate scripts
.github/workflows/   build.yml (test + package), release.yml
```

## Build the `.deb`

```sh
bash packaging/build_deb.sh dist
bash packaging/validate_deb.sh dist/movo_0.1.0_all.deb
```

CI builds and validates the package on every push (`.github/workflows/build.yml`)
and attaches it to tagged releases (`release.yml`).

## Security & privacy

* The API key is stored via the OS keyring when available, otherwise in a
  `0600` file under `~/.config/movo/`. It is **never** logged — a
  redacting log filter is a defence-in-depth backstop.
* Screenshots are used only for the visual overlay/debugging and are **never**
  sent to Jev. Jev receives compact structured state only.

## License

MIT — see [LICENSE](LICENSE).
