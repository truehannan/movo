"""The frameless floating window (PROMPT sections 17, 19, 21, 22, 30).

Owns the title bar, status dot, the stacked views (welcome / panel / model /
settings), the highlight overlay, the auto-update affordance, and all wiring to
:class:`TaskController`. Agent events arrive on a worker thread and are
marshalled onto the UI thread via Qt signals so widget updates stay thread-safe.

Window shape (per product spec): a **wide, short, rounded** panel, horizontally
centered and placed a little **above** the vertical center of the screen.
Palette is near-pitch-black with white as the secondary/interface colour.
"""

from __future__ import annotations

import threading

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

from app import __version__
from app.agent.controller import TaskController
from app.agent.loop import AgentEvent, EventType, Outcome, TaskResult
from app.config.secrets import SecretStore
from app.config.settings import Settings
from app.desktop.backend import Bounds, DesktopBackend
from app.diagnostics import updater
from app.diagnostics.capabilities import Capabilities
from app.safety.confirmation import CallbackConfirmer
from app.safety.emergency_stop import EmergencyStop
from app.ui import styles
from app.ui.model_view import ModelView
from app.ui.overlay import HighlightOverlay
from app.ui.panel import Panel
from app.ui.resources import logo_path
from app.ui.settings import SettingsView

_PAGE_WELCOME = 0
_PAGE_PANEL = 1
_PAGE_MODEL = 2
_PAGE_SETTINGS = 3

_WIN_W = 720
_WIN_H = 360


class MainWindow(QWidget):
    """The single floating window."""

    _event_signal = Signal(object)
    _finished_signal = Signal(object)
    _highlight_signal = Signal(object, int)
    _conn_signal = Signal(bool, str)
    _laya_progress_signal = Signal(str)
    _laya_done_signal = Signal(bool)
    _update_signal = Signal(object)  # UpdateCheck
    _update_progress_signal = Signal(str)

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
        self._pending_release = None  # updater.ReleaseInfo when an update exists

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
        self._start_update_check()

    # --- construction ----------------------------------------------------
    def _build(self) -> None:
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedWidth(_WIN_W)
        self.setMinimumHeight(_WIN_H)

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
        self.model_view = ModelView(self._settings, self._secrets)
        self.settings_view = SettingsView(self._settings, self._secrets)
        self.stack.addWidget(self.welcome)        # 0
        self.stack.addWidget(self.panel)          # 1
        self.stack.addWidget(self.model_view)     # 2
        self.stack.addWidget(self.settings_view)  # 3
        root_l.addWidget(self.stack, 1)

        self.setStyleSheet(styles.stylesheet())
        self._position_centered_above()

    def _title_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("TitleBar")
        bar.setFixedHeight(44)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 0, 10, 0)
        lay.setSpacing(8)

        self.status_dot = QLabel("●")
        self.status_dot.setObjectName("StatusDot")
        self.status_dot.setStyleSheet(f"color: {styles.TEXT_FAINT};")

        logo = QLabel()
        _logo_path = logo_path()
        if _logo_path:
            from PySide6.QtGui import QPixmap

            pix = QPixmap(_logo_path).scaled(
                22, 22, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            logo.setPixmap(pix)

        name = QLabel("Movo")
        name.setObjectName("AppName")
        lay.addWidget(self.status_dot)
        lay.addWidget(logo)
        lay.addWidget(name)
        lay.addStretch(1)

        # Update pill (hidden until an update is found).
        self.update_pill = QPushButton("Update available")
        self.update_pill.setObjectName("UpdatePill")
        self.update_pill.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update_pill.clicked.connect(self._on_update_clicked)
        self.update_pill.hide()
        lay.addWidget(self.update_pill)

        self.model_btn = QPushButton("Model")
        self.model_btn.setObjectName("Ghost")
        self.model_btn.clicked.connect(lambda: self.stack.setCurrentIndex(_PAGE_MODEL))
        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setObjectName("Ghost")
        self.settings_btn.clicked.connect(lambda: self.stack.setCurrentIndex(_PAGE_SETTINGS))
        close_btn = QPushButton("✕")
        close_btn.setObjectName("Ghost")
        close_btn.clicked.connect(self.close)
        lay.addWidget(self.model_btn)
        lay.addWidget(self.settings_btn)
        lay.addWidget(close_btn)

        bar.mousePressEvent = self._bar_press
        bar.mouseMoveEvent = self._bar_move
        return bar

    def _welcome_view(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(28, 10, 28, 22)
        lay.setSpacing(8)

        _logo_path = logo_path()
        if _logo_path:
            from PySide6.QtGui import QPixmap

            brand = QLabel()
            brand.setPixmap(
                QPixmap(_logo_path).scaled(
                    56, 56, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
                )
            )
            brand.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            lay.addWidget(brand)

        title = QLabel("Movo")
        title.setObjectName("H1")
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(title)
        sub = QLabel("Control your Linux desktop with fast, typed AI decisions.")
        sub.setObjectName("Dim")
        sub.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(sub)

        # Capability check in a compact horizontal strip.
        lay.addSpacing(6)
        caps_row = QHBoxLayout()
        caps_row.setSpacing(14)
        caps_row.addStretch(1)
        for label, ok in self._caps.as_rows():
            chip = QLabel(f"{'✓' if ok else '✕'} {label}")
            chip.setStyleSheet(
                f"color: {styles.OK if ok else styles.ERR}; font-size: 12px;"
            )
            caps_row.addWidget(chip)
        caps_row.addStretch(1)
        lay.addLayout(caps_row)

        lay.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)
        choose = QPushButton("Choose a model  →")
        choose.setObjectName("Primary")
        choose.clicked.connect(lambda: self.stack.setCurrentIndex(_PAGE_MODEL))
        row.addWidget(choose)
        row.addStretch(1)
        lay.addLayout(row)
        return w

    # --- wiring ----------------------------------------------------------
    def _wire_signals(self) -> None:
        self.panel.run_requested.connect(self._on_run)
        self.panel.stop_requested.connect(self._on_stop)
        self.settings_view.saved.connect(self._on_settings_saved)
        self.settings_view.test_requested.connect(self._on_test_connection)
        self.settings_view.back.connect(self._route_first_view)

        self.model_view.back.connect(self._route_first_view)
        self.model_view.provider_chosen.connect(self._on_provider_chosen)
        self.model_view.provision_laya_requested.connect(self._on_provision_laya)
        self.model_view.save_key_requested.connect(self._on_save_key)
        self.model_view.test_requested.connect(self._on_test_connection)

        self._event_signal.connect(self._handle_event)
        self._finished_signal.connect(self._handle_finished)
        self._highlight_signal.connect(self._on_highlight)
        self._conn_signal.connect(self._on_conn_result)
        self._laya_progress_signal.connect(self.model_view.set_laya_status)
        self._laya_done_signal.connect(self._on_laya_done)
        self._update_signal.connect(self._on_update_result)
        self._update_progress_signal.connect(self._on_update_progress)

    def _install_shortcuts(self) -> None:
        stop_sc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        stop_sc.activated.connect(self._on_stop)
        quit_sc = QShortcut(QKeySequence("Ctrl+Q"), self)
        quit_sc.activated.connect(self.close)

    def _provider_ready(self) -> bool:
        """Whether the configured provider is usable for a run."""
        if self._settings.is_local:
            return True  # the model panel provisions; run_goal starts if needed
        return self._secrets.has_api_key()

    def _route_first_view(self) -> None:
        # Reflect current Laya status on the model view whenever we route.
        try:
            self.model_view.reflect_laya_status(self._controller.laya_status())
        except Exception:
            pass
        if self._provider_ready():
            self.stack.setCurrentIndex(_PAGE_PANEL)
            self._set_status("connected", "Ready")
        else:
            self.stack.setCurrentIndex(_PAGE_WELCOME)

    # --- provider / model panel -----------------------------------------
    def _on_provider_chosen(self, provider: str) -> None:
        self._settings = Settings.load()
        self._controller._settings = self._settings  # keep controller in sync
        if provider == "laya":
            self.model_view.reflect_laya_status(self._controller.laya_status())

    def _on_provision_laya(self) -> None:
        def worker() -> None:
            ok = self._controller.provision_laya(
                progress=lambda m: self._laya_progress_signal.emit(m)
            )
            self._laya_done_signal.emit(ok)

        threading.Thread(target=worker, daemon=True).start()

    def _on_laya_done(self, ok: bool) -> None:
        self.model_view.set_laya_done(ok)
        if ok:
            self._set_status("connected", "Laya ready")

    def _on_save_key(self, key: str) -> None:
        self._secrets.set_api_key(key)

    # --- run/stop --------------------------------------------------------
    def _on_run(self, goal: str) -> None:
        if not self._provider_ready():
            self.stack.setCurrentIndex(_PAGE_MODEL)
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
            self.panel.set_current_action("Observing…", event.message[:70])
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
        self.panel.set_telemetry(tel.get("jev_calls", 0), tel.get("input_tokens", 0), 0.0)
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
        def worker() -> None:
            try:
                res = self._controller.test_connection()
                self._conn_signal.emit(res.ok, res.model or res.detail)
            except Exception as exc:
                self._conn_signal.emit(False, type(exc).__name__)

        threading.Thread(target=worker, daemon=True).start()

    def _on_conn_result(self, ok: bool, detail: str) -> None:
        target = self.model_view if self.stack.currentIndex() == _PAGE_MODEL else self.settings_view
        if ok:
            target.set_status(f"Connected · {detail}", styles.OK)
            self._set_status("connected", "Connected")
        else:
            target.set_status(f"Connection failed: {detail}", styles.ERR)

    def _on_settings_saved(self) -> None:
        self._settings = Settings.load()
        self._controller._settings = self._settings
        self._route_first_view()

    # --- auto-update -----------------------------------------------------
    def _start_update_check(self) -> None:
        def worker() -> None:
            check = updater.check_for_update(__version__)
            self._update_signal.emit(check)

        threading.Thread(target=worker, daemon=True).start()

    def _on_update_result(self, check) -> None:
        if check.update_available and check.latest is not None:
            self._pending_release = check.latest
            self.update_pill.setText(f"Update {check.latest.version} →")
            self.update_pill.show()

    def _on_update_clicked(self) -> None:
        rel = self._pending_release
        if rel is None:
            return
        if not rel.has_asset:
            QMessageBox.information(
                self, "Update", f"Release {rel.version} is available at:\n{rel.html_url}"
            )
            return
        self.update_pill.setText("Updating…")
        self.update_pill.setEnabled(False)

        def worker() -> None:
            ok = updater.download_and_install(
                rel, progress=lambda m: self._update_progress_signal.emit(m)
            )
            self._update_progress_signal.emit(
                "Update installed — restart Movo." if ok else "Update failed."
            )

        threading.Thread(target=worker, daemon=True).start()

    def _on_update_progress(self, message: str) -> None:
        self.status_dot.setToolTip(message)
        self.update_pill.setText(message[:22])

    # --- destructive confirmation (worker thread) -----------------------
    def _confirm_destructive(self, description: str, reason: str) -> bool:
        result: dict = {}
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

    def _position_centered_above(self) -> None:
        """Horizontally centered, a little above the vertical center."""
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        self.adjustSize()
        x = geo.left() + (geo.width() - self.width()) // 2
        # Vertical: between the top and the center — ~30% down from the top,
        # which reads as "higher than screen, lower than the centre point".
        center_y = geo.top() + geo.height() // 2
        y = geo.top() + int(geo.height() * 0.30)
        y = min(y, center_y - self.height() // 2)
        self.move(x, max(geo.top() + 20, y))

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self._controller.shutdown()
        self._overlay.close()
        super().closeEvent(event)
