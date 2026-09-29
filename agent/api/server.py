"""The local agent service (PROMPT §19, §20, §24, §47).

FastAPI app exposing:
    POST /tasks              start a task (returns task + ws path)
    GET  /tasks/{id}         task status
    POST /tasks/{id}/stop    stop
    POST /tasks/{id}/pause   pause
    POST /tasks/{id}/resume  resume
    POST /tasks/{id}/confirm approve/deny a consequential action
    GET  /health             health + capability flags
    WS   /events/{id}        real-time event stream

Security: binds loopback-only by default; every HTTP/WS request must present the
per-run token (header ``X-Agent-Token`` or ``?token=``) and an allowed Origin.
Secrets stay server-side and are never returned.
"""

from __future__ import annotations

import asyncio
import threading
from queue import Empty as _QueueEmpty

from fastapi import FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect

from agent import __version__
from agent.api.config import Config
from agent.api.protocol import (
    ConfirmRequest,
    Health,
    SimpleOk,
    StartTaskRequest,
    StartTaskResponse,
    TaskInfo,
)
from agent.api.websocket import EventHub
from agent.browser.browser import BrowserSession
from agent.core.agent import AgentRuntime
from agent.core.events import AgentEvent
from agent.core.task import BrowserContext, TaskContext
from agent.model.jev import DecisionEngine

# Origins a browser extension legitimately uses.
_ALLOWED_ORIGIN_PREFIXES = ("chrome-extension://", "moz-extension://", "http://127.0.0.1", "http://localhost")

# Statuses that end the event stream so the WS closes cleanly.
_TERMINAL_STATUS = {"success", "blocked", "error", "stopped"}


class _RunningTask:
    def __init__(self, task: TaskContext, runtime: AgentRuntime) -> None:
        self.task = task
        self.runtime = runtime
        self.thread: threading.Thread | None = None
        self._confirm_event = threading.Event()
        self._confirm_result = False

    def request_confirm(self, description: str, reason: str) -> bool:
        self._confirm_event.clear()
        # Block the worker until the UI answers (or a stop is requested).
        self._confirm_event.wait(timeout=120)
        return self._confirm_result

    def answer_confirm(self, approved: bool) -> None:
        self._confirm_result = approved
        self._confirm_event.set()


def create_app(
    config: Config,
    browser_factory,           # () -> BrowserSession, bound to the active tab
    engine_factory=None,       # () -> DecisionEngine (defaults to real Jev client)
) -> FastAPI:
    app = FastAPI(title="Jev Browser Agent", version=__version__)
    hub = EventHub()
    tasks: dict[str, _RunningTask] = {}

    def _check_auth(token: str | None, origin: str | None) -> None:
        if token != config.request_token:
            raise HTTPException(status_code=401, detail="bad token")
        if origin is not None and not any(origin.startswith(p) for p in _ALLOWED_ORIGIN_PREFIXES):
            raise HTTPException(status_code=403, detail="bad origin")

    def _make_engine() -> DecisionEngine:
        if engine_factory is not None:
            return engine_factory()
        from agent.model.jev import JevClient

        client = JevClient(
            api_key=config.jev_api_key or "local",
            model=config.jev_model,
            base_url=config.jev_base_url or None,
        )
        return DecisionEngine(client)

    @app.get("/health", response_model=Health)
    async def health() -> Health:
        return Health(
            version=__version__,
            has_jev_key=config.has_jev_key,
            has_text_model=config.has_text_model,
        )

    @app.post("/tasks", response_model=StartTaskResponse)
    async def start_task(
        req: StartTaskRequest,
        x_agent_token: str | None = Header(default=None),
        origin: str | None = Header(default=None),
    ) -> StartTaskResponse:
        _check_auth(x_agent_token, origin)
        task = TaskContext(
            goal=req.goal,
            browser=BrowserContext(tab_id=req.context.tab_id, url=req.context.url, title=req.context.title),
            max_steps=req.max_steps,
            max_runtime_ms=req.max_runtime_ms,
            max_failures=req.max_failures,
        )
        browser: BrowserSession = browser_factory()
        engine = _make_engine()

        running = _RunningTask(task, None)  # runtime set below

        def on_event(ev: AgentEvent) -> None:
            hub.publish_threadsafe(ev)

        runtime = AgentRuntime(
            browser=browser,
            engine=engine,
            on_event=on_event,
            confirmer=running.request_confirm,
        )
        running.runtime = runtime
        tasks[task.id] = running

        def worker() -> None:
            runtime.run(task)

        running.thread = threading.Thread(target=worker, name=f"task-{task.id}", daemon=True)
        running.thread.start()

        return StartTaskResponse(task=_info(task), ws=f"/events/{task.id}")

    def _info(task: TaskContext) -> TaskInfo:
        return TaskInfo(
            id=task.id, goal=task.goal, status=task.status.value,
            step_count=task.step_count, url=task.browser.url, title=task.browser.title,
        )

    def _require(task_id: str) -> _RunningTask:
        rt = tasks.get(task_id)
        if rt is None:
            raise HTTPException(status_code=404, detail="unknown task")
        return rt

    @app.get("/tasks/{task_id}", response_model=TaskInfo)
    async def get_task(task_id: str, x_agent_token: str | None = Header(default=None)) -> TaskInfo:
        _check_auth(x_agent_token, None)
        return _info(_require(task_id).task)

    @app.post("/tasks/{task_id}/stop", response_model=SimpleOk)
    async def stop_task(task_id: str, x_agent_token: str | None = Header(default=None)) -> SimpleOk:
        _check_auth(x_agent_token, None)
        _require(task_id).runtime.stop()
        return SimpleOk(detail="stopping")

    @app.post("/tasks/{task_id}/pause", response_model=SimpleOk)
    async def pause_task(task_id: str, x_agent_token: str | None = Header(default=None)) -> SimpleOk:
        _check_auth(x_agent_token, None)
        _require(task_id).runtime.pause()
        return SimpleOk(detail="paused")

    @app.post("/tasks/{task_id}/resume", response_model=SimpleOk)
    async def resume_task(task_id: str, x_agent_token: str | None = Header(default=None)) -> SimpleOk:
        _check_auth(x_agent_token, None)
        _require(task_id).runtime.resume()
        return SimpleOk(detail="resumed")

    @app.post("/tasks/{task_id}/confirm", response_model=SimpleOk)
    async def confirm_task(task_id: str, req: ConfirmRequest, x_agent_token: str | None = Header(default=None)) -> SimpleOk:
        _check_auth(x_agent_token, None)
        _require(task_id).answer_confirm(req.approved)
        return SimpleOk(detail="approved" if req.approved else "denied")

    @app.websocket("/events/{task_id}")
    async def events(ws: WebSocket, task_id: str, token: str | None = Query(default=None)) -> None:
        origin = ws.headers.get("origin")
        if token != config.request_token or (
            origin is not None and not any(origin.startswith(p) for p in _ALLOWED_ORIGIN_PREFIXES)
        ):
            await ws.close(code=4401)
            return
        await ws.accept()
        q = hub.subscribe(task_id)
        try:
            while True:
                try:
                    wire = q.get_nowait()
                except _QueueEmpty:
                    await asyncio.sleep(0.05)
                    continue
                await ws.send_json(wire)
                if wire.get("type") == "agent.completed" or wire.get("status") in _TERMINAL_STATUS:
                    break
        except WebSocketDisconnect:
            pass
        finally:
            hub.unsubscribe(task_id, q)

    app.state.hub = hub
    app.state.tasks = tasks
    app.state.config = config
    return app
