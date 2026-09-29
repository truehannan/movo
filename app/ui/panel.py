"""The main operational panel (PROMPT sections 17, 19, 27).

Shows connection status, the task input, run/stop controls, the live current
action, current app, targeted element, confidence, verification status, a step
counter, and the action history. Debug telemetry (Jev calls, tokens, latency)
is available but understated by default.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from app.ui import styles


class Panel(QWidget):
    """The run surface. Emits ``run_requested`` / ``stop_requested``."""

    run_requested = Signal(str)
    stop_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._build()
        self.set_idle()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 6, 16, 14)
        root.setSpacing(11)

        # Prompt line.
        prompt = QLabel("What should I do?")
        prompt.setObjectName("Dim")
        root.addWidget(prompt)

        self.input = QLineEdit()
        self.input.setPlaceholderText('e.g. Open Firefox and search for "Python 3.14"')
        self.input.returnPressed.connect(self._emit_run)
        root.addWidget(self.input)

        # Run / Stop row.
        controls = QHBoxLayout()
        from PySide6.QtWidgets import QPushButton

        self.run_btn = QPushButton("Run")
        self.run_btn.setObjectName("Primary")
        self.run_btn.clicked.connect(self._emit_run)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setObjectName("Danger")
        self.stop_btn.clicked.connect(self.stop_requested.emit)
        self.stop_btn.setEnabled(False)
        controls.addWidget(self.run_btn)
        controls.addWidget(self.stop_btn)
        controls.addStretch(1)
        self.step_label = QLabel("")
        self.step_label.setObjectName("Faint")
        controls.addWidget(self.step_label)
        root.addLayout(controls)

        # Live current-action card.
        card = QWidget()
        card.setObjectName("Card")
        card_l = QVBoxLayout(card)
        card_l.setContentsMargins(12, 10, 12, 10)
        card_l.setSpacing(4)
        self.current_action = QLabel("Idle")
        self.current_action.setObjectName("CurrentAction")
        card_l.addWidget(self.current_action)
        self.context_line = QLabel("")
        self.context_line.setObjectName("Faint")
        card_l.addWidget(self.context_line)

        self.confidence = QProgressBar()
        self.confidence.setRange(0, 100)
        self.confidence.setTextVisible(False)
        self.confidence.setFixedHeight(4)
        self.confidence.setStyleSheet(
            f"QProgressBar {{ background: {styles.BORDER}; border-radius: 2px; }}"
            f"QProgressBar::chunk {{ background: {styles.ACCENT}; border-radius: 2px; }}"
        )
        card_l.addWidget(self.confidence)
        root.addWidget(card)

        # History.
        hist_label = QLabel("Action history")
        hist_label.setObjectName("Faint")
        root.addWidget(hist_label)
        self.history = QListWidget()
        self.history.setMinimumHeight(120)
        root.addWidget(self.history, 1)

        # Understated telemetry footer.
        self.telemetry = QLabel("")
        self.telemetry.setObjectName("Faint")
        root.addWidget(self.telemetry)

    # --- state helpers ---------------------------------------------------
    def _emit_run(self) -> None:
        text = self.input.text().strip()
        if text:
            self.run_requested.emit(text)

    def set_idle(self) -> None:
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.input.setEnabled(True)

    def set_running(self) -> None:
        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.input.setEnabled(False)
        self.history.clear()
        self.set_current_action("Starting…", "")

    def set_current_action(self, text: str, context: str = "") -> None:
        self.current_action.setText(text)
        if context:
            self.context_line.setText(context)

    def set_confidence(self, value: float) -> None:
        self.confidence.setValue(int(max(0.0, min(1.0, value)) * 100))

    def set_step(self, step: int, max_steps: int) -> None:
        self.step_label.setText(f"step {step}/{max_steps}")

    def add_history(self, text: str, color: str = styles.TEXT) -> None:
        item = QListWidgetItem(text)
        from PySide6.QtGui import QColor

        item.setForeground(QColor(color))
        self.history.addItem(item)
        self.history.scrollToBottom()

    def set_telemetry(self, calls: int, tokens: int, latency_ms: float) -> None:
        self.telemetry.setText(
            f"{calls} Jev calls · {tokens} input tokens · {latency_ms:.0f} ms last decision"
        )
