"""Entry point for the local agent service (PROMPT §43).

Usage:
    uv run jev-agent            # or: python -m agent.main
Reads .env / environment for keys and bind address, prints the per-run request
token the extension needs, and serves the FastAPI app on 127.0.0.1 by default.
"""

from __future__ import annotations

import os
import sys


def _load_dotenv() -> None:
    """Minimal .env loader (no extra dependency)."""
    path = os.path.join(os.getcwd(), ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())


def main() -> int:
    _load_dotenv()
    import uvicorn

    from agent.api.config import Config
    from agent.api.server import create_app
    from agent.browser.cdp import connect_active_tab_factory

    config = Config.from_env()

    if not config.is_loopback():
        print(f"WARNING: binding to non-loopback host {config.host} — this exposes the agent.", file=sys.stderr)

    app = create_app(config, browser_factory=connect_active_tab_factory(config))

    print("Jev Browser Agent — local service")
    print(f"  URL   : http://{config.host}:{config.port}")
    print(f"  Token : {config.request_token}")
    print(f"  Jev   : {'configured' if config.has_jev_key else 'NOT configured (set TYPESAFE_API_KEY)'}")
    print(f"  Text  : {'configured' if config.has_text_model else 'not configured (TYPE_TEXT disabled)'}")
    print("  Paste the token into the extension settings to connect.")

    uvicorn.run(app, host=config.host, port=config.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
