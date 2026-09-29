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
  ├─ Desktop Observer   proven AT-SPI engine → windows, elements, roles, bounds
  ├─ Candidate Builder  filter + rank + serialize to 5–20 typed candidates
  ├─ Jev / Laya Engine  one call, typed questions:
  │      • operation   Choice   (CLICK / TYPE / PRESS_KEY / SCROLL / WAIT / DONE / BLOCKED / …)
  │      • target      Choice   (candidate id or NONE)
  │      • continue    Noul     (more steps needed?)
  │      • safe        Noul     (safe & grounded to execute?)
  ├─ Action Executor    real mouse / keyboard / scroll (xdotool, pynput fallback)
  └─ Verifier           re-observe and confirm the desktop actually changed
```

The desktop observation and control come from a proven, generic
computer-use engine (adapted from
[`tak-uukti/linux-computer-use`](https://github.com/tak-uukti/linux-computer-use),
MIT) — the **same** engine drives any accessible app, not per-application code.

**Proof of work.** The whole observe → decide → act → verify loop is proven on a
real app: `movo --selftest` launches gnome-calculator and computes `7 + 8`
through Movo's own backend and candidate translation (a deterministic decider
stands in for the model), then verifies the calculator's display reads `15`.
`scripts/proof_of_work.py` is the same proof, verbose.

Everything deterministic — visibility, enabled state, coordinate extraction,
candidate filtering, retries, loop detection, emergency stop, destructive-action
confirmation — is handled in code. The decision model is only asked the
semantic questions.

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
sudo apt install ./movo_0.3.0_all.deb
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

## Models

Open **Model** in the title bar and choose your decision provider:

* **Jev** (cloud) — TypeSafe's hosted System One model. Fast and calibrated;
  needs an API key. Get one at <https://console.typesafe.ai/keys>.
* **Laya** (local) — an open-weight System One model that runs entirely on your
  machine. Private, no key, works offline. Choosing Laya installs a small local
  runtime and downloads the model (~850 MB, one time) into the shared Hugging
  Face cache, then serves it on `127.0.0.1` behind the same wire API — so the
  agent loop is identical for both providers.

Movo keeps the decision space small (a handful of typed candidates and
operations per step), which suits Laya's strengths and avoids its known weak
spot with many-label choices.

Setting up Laya installs the `laya[serve]` package into Movo's per-user
virtualenv and downloads the checkpoint on first use. The **Set up Laya locally**
button streams the real install/download output into an in-app log (**Show
logs**), and **Open in terminal** runs the same setup in a terminal window with
live output. From the command line you can also run:

```sh
movo --laya-setup
```

## The window (Dynamic Island)

Movo lives as a **Dynamic Island** pinned to the top-center of the screen. It is
non-movable and stays out of the way: it retracts to a thin sliver at the top
edge, and **drops down with a bounce when you move the pointer to the top of the
screen** (or onto the island). It retracts again when the pointer leaves —
unless you are typing a task or a run is in progress, in which case it stays
open.

## Updates

Movo checks the GitHub Releases feed on launch. When a newer release exists, an
**Update** pill appears in the title bar; one click downloads that release's
`.deb` and installs it with a graphical permission prompt (`pkexec apt install`),
replacing the old version in place. The downloaded file is removed afterward, so
nothing is left behind.

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
bash packaging/validate_deb.sh dist/movo_0.3.0_all.deb
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

## Credits

* The computer-use engine is adapted from
  [`tak-uukti/linux-computer-use`](https://github.com/tak-uukti/linux-computer-use)
  (MIT) — AT-SPI translation + xdotool/scrot, verified end-to-end on real apps.
* **Laya** local model by [Convai Innovations](https://huggingface.co/convaiinnovations/laya)
  (Apache-2.0); **Jev** System One API by [TypeSafe AI](https://docs.typesafe.ai).
* Built on AT-SPI 2, xdotool, wmctrl, scrot, PySide6, and pynput/mss.
