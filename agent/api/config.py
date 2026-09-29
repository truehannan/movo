"""Runtime configuration loaded from the environment (PROMPT §19, §41, §42, §47).

Secrets (Jev key, text-model key) live only in the local process environment,
never in the extension. A per-run request token gates extension→backend calls,
and the service binds loopback-only by default.
"""

from __future__ import annotations

import os
import secrets as _secrets
from dataclasses import dataclass, field


@dataclass
class Config:
    host: str = "127.0.0.1"
    port: int = 8766
    jev_api_key: str = ""
    jev_model: str = "jev-latest"
    jev_base_url: str = ""  # set to a local Laya server URL to run locally
    text_model_api_key: str = ""
    text_model: str = ""
    text_model_base_url: str = ""
    # A random token the extension must present (Host/Origin + token check).
    request_token: str = field(default_factory=lambda: _secrets.token_urlsafe(24))

    @classmethod
    def from_env(cls) -> Config:
        return cls(
            host=os.environ.get("AGENT_HOST", "127.0.0.1"),
            port=int(os.environ.get("AGENT_PORT", "8766")),
            jev_api_key=os.environ.get("TYPESAFE_API_KEY", "").strip(),
            jev_model=os.environ.get("JEV_MODEL", "jev-latest").strip() or "jev-latest",
            jev_base_url=os.environ.get("TYPESAFE_BASE_URL", "").strip(),
            text_model_api_key=os.environ.get("TEXT_MODEL_API_KEY", "").strip(),
            text_model=os.environ.get("TEXT_MODEL", "").strip(),
            text_model_base_url=os.environ.get("TEXT_MODEL_BASE_URL", "").strip(),
        )

    @property
    def has_jev_key(self) -> bool:
        return bool(self.jev_api_key) or bool(self.jev_base_url)

    @property
    def has_text_model(self) -> bool:
        return bool(self.text_model and self.text_model_base_url)

    def is_loopback(self) -> bool:
        return self.host in ("127.0.0.1", "localhost", "::1")
