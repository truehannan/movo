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

from PySide6.QtCore import (
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
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

# Dynamic-island geometry.
_PEEK = 6            # px of the island left visible when retracted
_TOP_MARGIN = 8     # px gap from the very top of the screen when revealed
_TRIGGER_H = 4      # px-thin hover strip pinned to the screen's top edge
_ANIM_MS = 420      # reveal animation duration (bounce)


class _TopEdgeTrigger(QWidget):
    """A thin, transparent, always-on-top strip across the screen's top-center.

    Hovering it asks the island to drop down; it exists so the reveal works even
    when the island is retracted almost entirely off-screen (and thus not itself
    hovering-detectable). It is click-through-ish: it only watches enter events.
    """

    def __init__(self, on_enter) -> None:
        super().__init__(None)
        self._on_enter = on_enter
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_AlwaysShowToolTips, False)

    def enterEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self._on_enter()
        super().enterEvent(event)


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

        # --- dynamic-island state ---
        self._revealed = False
        self._revealed_y = 0
        self._retracted_y = 0
        self._anim = QPropertyAnimation(self, b"pos")
        self._anim.setDuration(_ANIM_MS)
        self._retract_timer = QTimer(self)
        self._retract_timer.setSingleShot(True)
        self._retract_timer.setInterval(400)
        self._retract_timer.timeout.connect(self._maybe_retract)
        self._trigger = _TopEdgeTrigger(self._reveal)

        self._build()
        self._wire_signals()
        self._install_shortcuts()
        self._route_first_view()
        self._start_update_check()
        self._setup_island()

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
        self.model_view.open_terminal_requested.connect(self._on_open_laya_terminal)
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

    def _on_open_laya_terminal(self) -> None:
        opened = self._controller.open_laya_interactive_setup()
        if not opened:
            self.model_view.set_laya_status(
                "No terminal emulator found. Run:  movo --laya-setup"
            )

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

    # --- dynamic island (top-center, non-movable, hover to reveal) ------
    def _setup_island(self) -> None:
        """Compute retracted/revealed positions and show the top-edge trigger."""
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        self.adjustSize()
        x = geo.left() + (geo.width() - self.width()) // 2
        self._revealed_y = geo.top() + _TOP_MARGIN
        # Retracted: almost fully above the top edge, leaving a peek sliver.
        self._retracted_y = geo.top() - self.height() + _PEEK
        self.move(x, self._retracted_y)
        self._revealed = False

        # Thin hover strip across the top-center of the screen.
        tw = min(self.width(), 520)
        self._trigger.setGeometry(
            geo.left() + (geo.width() - tw) // 2, geo.top(), tw, _TRIGGER_H
        )
        self._trigger.show()

        # Greet the user: drop down on launch, then retract after a moment so
        # the auto-hide behaviour is discoverable.
        QTimer.singleShot(300, self._reveal)
        QTimer.singleShot(2600, self._retract_timer.start)

    def _reveal(self) -> None:
        if self._revealed:
            return
        self._revealed = True
        self._animate_to(self._revealed_y, bounce=True)

    def _retract(self) -> None:
        if not self._revealed:
            return
        self._revealed = False
        self._animate_to(self._retracted_y, bounce=False)

    def _animate_to(self, y: int, bounce: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self.pos())
        self._anim.setEndValue(QPoint(self.x(), y))
        self._anim.setEasingCurve(
            QEasingCurve.Type.OutBounce if bounce else QEasingCurve.Type.InCubic
        )
        self._anim.setDuration(_ANIM_MS if bounce else 220)
        self._anim.start()

    def _text_input_active(self) -> bool:
        """True while a text field is focused or the task input has content.

        Keeps the island open while the user is typing, even if the mouse
        leaves — so a run they are composing is never yanked away.
        """
        fw = self.focusWidget()
        if isinstance(fw, QLineEdit):
            return True
        try:
            if self.panel.input.text().strip():
                return True
        except Exception:
            pass
        return False

    def _maybe_retract(self) -> None:
        # Do not retract while typing, running, or the pointer is still over us.
        if self._text_input_active() or self._controller.running:
            self._retract_timer.start()
            return
        if self.underMouse():
            return
        self._retract()

    def enterEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self._retract_timer.stop()
        self._reveal()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 (Qt override)
        # Debounce so brief pointer exits (e.g. crossing a child border) don't
        # retract; the timer re-checks typing/running/hover state.
        self._retract_timer.start()
        super().leaveEvent(event)

    # The title bar is no longer a drag handle — the island is non-movable.
    def _bar_press(self, event) -> None:  # kept for layout wiring; no-op
        return None

    def _bar_move(self, event) -> None:
        return None

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self._trigger.close()
        self._controller.shutdown()
        self._overlay.close()
        super().closeEvent(event)
