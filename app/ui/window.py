"""The frameless floating window (PROMPT sections 17, 19, 21, 22, 30).

Owns the title bar, status dot, the stacked panel/settings/welcome views, the
highlight overlay, and all wiring to :class:`TaskController`. Agent events
arrive on a worker thread and are marshalled onto the UI thread via a Qt signal
so widget updates are always thread-safe.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.agent.controller import TaskController
from app.agent.loop import AgentEvent, EventType, Outcome, TaskResult
from app.config.secrets import SecretStore
from app.config.settings import Settings
from app.desktop.backend import Bounds, DesktopBackend
from app.diagnostics.capabilities import Capabilities
from app.safety.confirmation import CallbackConfirmer
from app.safety.emergency_stop import EmergencyStop
from app.ui import styles
from app.ui.overlay import HighlightOverlay
from app.ui.panel import Panel
from app.ui.resources import logo_path
from app.ui.settings import SettingsView

_PAGE_WELCOME = 0
_PAGE_PANEL = 1
_PAGE_SETTINGS = 2


class MainWindow(QWidget):
    """The single floating window."""

    _event_signal = Signal(object)
    _finished_signal = Signal(object)
    _highlight_signal = Signal(object, int)
    _conn_signal = Signal(bool, str)

    def __init__(
        self,
        backend: DesktopBackend,
        settings: Settings,
        secrets: SecretStore,
        capabilities: Capabilities,
    ) -> None:
        super().__init__()
        self._settings = settings
        self._secrets = secrets
        self._backend = backend
        self._caps = capabilities
        self._stop = EmergencyStop()
        self._drag_offset: QPoint | None = None

        self._controller = TaskController(
            backend=backend,
            settings=settings,
            secrets=secrets,
            stop=self._stop,
            confirmer=CallbackConfirmer(self._confirm_destructive),
        )

        self._overlay = HighlightOverlay()
        if hasattr(backend, "set_overlay_callback"):
            backend.set_overlay_callback(
                lambda bounds, ms: self._highlight_signal.emit(bounds, ms)
            )

        self._build()
        self._wire_signals()
        self._install_shortcuts()
        self._route_first_view()

    # --- construction ----------------------------------------------------
    def _build(self) -> None:
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedWidth(380)
        self.setMinimumHeight(420)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        root = QWidget()
        root.setObjectName("Root")
        outer.addWidget(root)
        root_l = QVBoxLayout(root)
        root_l.setContentsMargins(0, 0, 0, 0)
        root_l.setSpacing(0)

        root_l.addWidget(self._title_bar())

        self.stack = QStackedWidget()
        self.welcome = self._welcome_view()
        self.panel = Panel()
        self.settings_view = SettingsView(self._settings, self._secrets)
        self.stack.addWidget(self.welcome)       # 0
        self.stack.addWidget(self.panel)         # 1
        self.stack.addWidget(self.settings_view) # 2
        root_l.addWidget(self.stack, 1)

        self.setStyleSheet(styles.stylesheet())
        self._position_bottom_right()

    def _title_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("TitleBar")
        bar.setFixedHeight(40)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(14, 0, 8, 0)

        self.status_dot = QLabel("●")
        self.status_dot.setObjectName("StatusDot")
        self.status_dot.setStyleSheet(f"color: {styles.TEXT_FAINT};")

        logo = QLabel()
        _logo_path = logo_path()
        if _logo_path:
            from PySide6.QtGui import QPixmap

            pix = QPixmap(_logo_path).scaled(
                20,
                20,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            logo.setPixmap(pix)

        name = QLabel("Movo")
        name.setObjectName("AppName")
        lay.addWidget(self.status_dot)
        lay.addWidget(logo)
        lay.addWidget(name)
        lay.addStretch(1)

        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setObjectName("Ghost")
        self.settings_btn.clicked.connect(lambda: self.stack.setCurrentIndex(_PAGE_SETTINGS))
        close_btn = QPushButton("✕")
        close_btn.setObjectName("Ghost")
        close_btn.clicked.connect(self.close)
        lay.addWidget(self.settings_btn)
        lay.addWidget(close_btn)

        bar.mousePressEvent = self._bar_press
        bar.mouseMoveEvent = self._bar_move
        return bar

    def _welcome_view(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(20, 8, 20, 20)
        lay.setSpacing(10)

        # Centered brand header: logo above the name.
        _logo_path = logo_path()
        if _logo_path:
            from PySide6.QtGui import QPixmap

            brand = QLabel()
            brand.setPixmap(
                QPixmap(_logo_path).scaled(
                    64,
                    64,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            brand.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            lay.addSpacing(8)
            lay.addWidget(brand)

        title = QLabel("Movo")
        title.setObjectName("H1")
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(title)
        sub = QLabel("Control your Linux desktop with fast, typed AI decisions.")
        sub.setObjectName("Dim")
        sub.setWordWrap(True)
        sub.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(sub)

        # Capability diagnostics (PROMPT section 22).
        lay.addSpacing(6)
        caps_title = QLabel("System check")
        caps_title.setObjectName("Faint")
        lay.addWidget(caps_title)
        for label, ok in self._caps.as_rows():
            row = QLabel(f"{'✓' if ok else '✕'}  {label}")
            row.setStyleSheet(f"color: {styles.OK if ok else styles.ERR};")
            lay.addWidget(row)
        session = QLabel(f"session: {self._caps.session_type}")
        session.setObjectName("Faint")
        lay.addWidget(session)

        lay.addStretch(1)
        btn = QPushButton("Set up API key  →")
        btn.setObjectName("Primary")
        btn.clicked.connect(lambda: self.stack.setCurrentIndex(_PAGE_SETTINGS))
        lay.addWidget(btn)
        return w

    # --- wiring ----------------------------------------------------------
    def _wire_signals(self) -> None:
        self.panel.run_requested.connect(self._on_run)
        self.panel.stop_requested.connect(self._on_stop)
        self.settings_view.saved.connect(self._on_settings_saved)
        self.settings_view.test_requested.connect(self._on_test_connection)
        self.settings_view.back.connect(self._route_first_view)

        self._event_signal.connect(self._handle_event)
        self._finished_signal.connect(self._handle_finished)
        self._highlight_signal.connect(self._on_highlight)
        self._conn_signal.connect(self._on_conn_result)

    def _install_shortcuts(self) -> None:
        # ESC = emergency stop (PROMPT section 21).
        stop_sc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        stop_sc.activated.connect(self._on_stop)
        # Ctrl+Q closes.
        quit_sc = QShortcut(QKeySequence("Ctrl+Q"), self)
        quit_sc.activated.connect(self.close)

    def _route_first_view(self) -> None:
        if self._secrets.has_api_key():
            self.stack.setCurrentIndex(_PAGE_PANEL)
            self._set_status("connected", "Ready")
        else:
            self.stack.setCurrentIndex(_PAGE_WELCOME)

    # --- run/stop --------------------------------------------------------
    def _on_run(self, goal: str) -> None:
        if not self._secrets.has_api_key():
            self.stack.setCurrentIndex(_PAGE_SETTINGS)
            return
        self.panel.set_running()
        self._set_status("running", "Running")
        self.panel.set_step(0, self._settings.max_steps)
        self._controller.run_goal(
            goal,
            on_event=lambda e: self._event_signal.emit(e),
            on_finished=lambda r: self._finished_signal.emit(r),
        )

    def _on_stop(self) -> None:
        if self._controller.running:
            self._controller.stop()
            self._set_status("stopped", "Stopping…")

    # --- event handling (UI thread) -------------------------------------
    def _handle_event(self, event: AgentEvent) -> None:
        self.panel.set_step(event.step, self._settings.max_steps)
        if event.type is EventType.OBSERVED:
            self.panel.set_current_action("Observing…", event.message[:60])
        elif event.type is EventType.DECIDED and event.decision is not None:
            d = event.decision
            ctx = f"{event.app_name}"
            if event.target_label:
                ctx += f"  ·  {event.target_label}"
            self.panel.set_current_action(d.describe(), ctx)
            self.panel.set_confidence(d.confidence)
            self.panel.set_telemetry(0, d.input_tokens, d.latency_ms)
        elif event.type is EventType.ACTING:
            self._set_status("running", "Acting")
        elif event.type is EventType.VERIFIED:
            ok = bool(event.verified)
            mark = "✓ VERIFIED" if ok else "… unverified"
            color = styles.OK if ok else styles.WARN
            desc = event.decision.describe() if event.decision else event.message
            self.panel.add_history(f"{mark}  {desc}", color)
            self._set_status("verified" if ok else "retry", "Verified" if ok else "Retrying")
        elif event.type is EventType.CONFIRM:
            self.panel.add_history(f"⚠ confirm: {event.message}", styles.WARN)
        elif event.type is EventType.INFO:
            self.panel.add_history(event.message, styles.TEXT_DIM)

    def _handle_finished(self, result: TaskResult) -> None:
        self.panel.set_idle()
        tel = result.telemetry
        self.panel.set_telemetry(
            tel.get("jev_calls", 0), tel.get("input_tokens", 0), 0.0
        )
        color_key = {
            Outcome.DONE: "done",
            Outcome.BLOCKED: "blocked",
            Outcome.STOPPED: "stopped",
            Outcome.ERROR: "error",
        }.get(result.outcome, "idle")
        self.panel.set_current_action(result.outcome.value, result.detail)
        self._set_status(color_key, result.outcome.value.title())
        self.panel.add_history(f"— {result.outcome.value}: {result.detail}", styles.TEXT_DIM)

    def _on_highlight(self, bounds: Bounds, ms: int) -> None:
        self._overlay.flash(bounds, ms)

    # --- connection test -------------------------------------------------
    def _on_test_connection(self) -> None:
        import threading

        def worker() -> None:
            try:
                res = self._controller.test_connection()
                self._conn_signal.emit(res.ok, res.model or res.detail)
            except Exception as exc:
                self._conn_signal.emit(False, type(exc).__name__)

        threading.Thread(target=worker, daemon=True).start()

    def _on_conn_result(self, ok: bool, detail: str) -> None:
        if ok:
            self.settings_view.set_status(f"Jev connected · {detail}", styles.OK)
            self._set_status("connected", "Connected")
        else:
            self.settings_view.set_status(f"Connection failed: {detail}", styles.ERR)

    def _on_settings_saved(self) -> None:
        self._settings = Settings.load()
        self._route_first_view()

    # --- destructive confirmation (called from worker thread) -----------
    def _confirm_destructive(self, description: str, reason: str) -> bool:
        # QMessageBox must run on the UI thread; block the worker until answered.
        from PySide6.QtCore import QMetaObject, Qt as _Qt, Q_ARG  # noqa

        result: dict = {}
        import threading

        done = threading.Event()

        def ask() -> None:
            box = QMessageBox(self)
            box.setWindowTitle("Confirm action")
            box.setText(f"Allow this action?\n\n{description}")
            box.setInformativeText(reason)
            box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            box.setDefaultButton(QMessageBox.StandardButton.No)
            result["ok"] = box.exec() == QMessageBox.StandardButton.Yes
            done.set()

        from PySide6.QtCore import QTimer

        QTimer.singleShot(0, ask)
        done.wait(timeout=60)
        return result.get("ok", False)

    # --- status ----------------------------------------------------------
    def _set_status(self, key: str, tooltip: str = "") -> None:
        color = styles.STATUS_COLORS.get(key, styles.TEXT_FAINT)
        self.status_dot.setStyleSheet(f"color: {color};")
        if tooltip:
            self.status_dot.setToolTip(tooltip)

    # --- window drag & placement ----------------------------------------
    def _bar_press(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def _bar_move(self, event) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)

    def _position_bottom_right(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        self.adjustSize()
        self.move(geo.right() - self.width() - 24, geo.bottom() - self.height() - 24)

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self._controller.shutdown()
        self._overlay.close()
        super().closeEvent(event)
