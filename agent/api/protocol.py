"""Typed protocol between the extension and the local agent service (PROMPT §24).

Pydantic models define the request/response and the server event shapes. The
same field names are mirrored in the extension's generated TypeScript types
(scripts/gen-protocol) so the schema is never duplicated by hand.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# --- client → server -------------------------------------------------------
class BrowserContextIn(BaseModel):
    tab_id: int | None = None
    url: str = ""
    title: str = ""


class StartTaskRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=2000)
    context: BrowserContextIn = BrowserContextIn()
    max_steps: int = 50
    max_runtime_ms: int = 5 * 60 * 1000
    max_failures: int = 3


class ConfirmRequest(BaseModel):
    approved: bool


# --- server → client -------------------------------------------------------
class TaskInfo(BaseModel):
    id: str
    goal: str
    status: str
    step_count: int
    url: str = ""
    title: str = ""


class StartTaskResponse(BaseModel):
    task: TaskInfo
    ws: str  # relative WebSocket path for the event stream


class SimpleOk(BaseModel):
    ok: bool = True
    detail: str = ""


class ServerEvent(BaseModel):
    """Mirror of AgentEvent on the wire (agent.core.events)."""

    type: str
    task_id: str = ""
    step: int = 0
    message: str = ""
    status: str | None = None
    operation: str | None = None
    target: str | None = None
    verified: bool | None = None
    outcome: str | None = None
    ts: float = 0.0


HealthStatus = Literal["ok"]


class Health(BaseModel):
    status: HealthStatus = "ok"
    version: str
    has_jev_key: bool
    has_text_model: bool
