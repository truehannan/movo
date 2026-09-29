"""Settings view (PROMPT sections 20, 30).

Collects the API key (stored only via :class:`SecretStore`, never logged),
model id, and the tunable limits/toggles. Shows connection status and a Test
Connection button. The key field is masked and never echoed back in full.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.config.secrets import SecretStore, mask_key
from app.config.settings import Settings
from app.ui import styles


class SettingsView(QWidget):
    """Editable settings form. Emits ``saved`` and ``test_requested``."""

    saved = Signal()
    test_requested = Signal()
    back = Signal()

    def __init__(self, settings: Settings, secrets: SecretStore) -> None:
        super().__init__()
        self._settings = settings
        self._secrets = secrets
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 14)
        root.setSpacing(12)

        header = QHBoxLayout()
        back = QPushButton("‹ Back")
        back.setObjectName("Ghost")
        back.clicked.connect(self.back.emit)
        title = QLabel("Settings")
        title.setObjectName("H1")
        header.addWidget(back)
        header.addWidget(title)
        header.addStretch(1)
        root.addLayout(header)

        form = QFormLayout()
        form.setSpacing(9)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText("TypeSafe / Jev API key")
        if self._secrets.has_api_key():
            self.key_edit.setPlaceholderText(
                f"stored: {mask_key(self._secrets.get_api_key())} ({self._secrets.backend_name})"
            )
        form.addRow(self._dim("API key"), self.key_edit)

        self.model_edit = QLineEdit(self._settings.model)
        form.addRow(self._dim("Model"), self.model_edit)

        self.max_steps = QSpinBox()
        self.max_steps.setRange(1, 200)
        self.max_steps.setValue(self._settings.max_steps)
        form.addRow(self._dim("Max steps"), self.max_steps)

        self.action_timeout = QDoubleSpinBox()
        self.action_timeout.setRange(1.0, 60.0)
        self.action_timeout.setValue(self._settings.action_timeout_s)
        self.action_timeout.setSuffix(" s")
        form.addRow(self._dim("Action timeout"), self.action_timeout)

        self.confirm_mode = QCheckBox("Confirm destructive actions")
        self.confirm_mode.setChecked(self._settings.confirmation_mode)
        form.addRow("", self.confirm_mode)

        self.screenshot_fb = QCheckBox("Screenshot fallback")
        self.screenshot_fb.setChecked(self._settings.screenshot_fallback)
        form.addRow("", self.screenshot_fb)

        self.debug_log = QCheckBox("Debug logging")
        self.debug_log.setChecked(self._settings.debug_logging)
        form.addRow("", self.debug_log)

        root.addLayout(form)

        self.status = QLabel("")
        self.status.setObjectName("Faint")
        root.addWidget(self.status)

        buttons = QHBoxLayout()
        test = QPushButton("Test Connection")
        test.clicked.connect(self._on_test)
        save = QPushButton("Save")
        save.setObjectName("Primary")
        save.clicked.connect(self._on_save)
        buttons.addWidget(test)
        buttons.addStretch(1)
        buttons.addWidget(save)
        root.addLayout(buttons)

    @staticmethod
    def _dim(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("Dim")
        return lbl

    def set_status(self, text: str, color: str = styles.TEXT_DIM) -> None:
        self.status.setText(text)
        self.status.setStyleSheet(f"color: {color};")

    def _on_save(self) -> None:
        key = self.key_edit.text().strip()
        if key:
            self._secrets.set_api_key(key)
            self.key_edit.clear()
            self.key_edit.setPlaceholderText(
                f"stored: {mask_key(self._secrets.get_api_key())} ({self._secrets.backend_name})"
            )
        self._settings.model = self.model_edit.text().strip() or "jev-latest"
        self._settings.max_steps = self.max_steps.value()
        self._settings.action_timeout_s = self.action_timeout.value()
        self._settings.confirmation_mode = self.confirm_mode.isChecked()
        self._settings.screenshot_fallback = self.screenshot_fb.isChecked()
        self._settings.debug_logging = self.debug_log.isChecked()
        self._settings.save()
        self.set_status("Saved.", styles.OK)
        self.saved.emit()

    def _on_test(self) -> None:
        # Persist a freshly typed key first so the test uses it.
        key = self.key_edit.text().strip()
        if key:
            self._secrets.set_api_key(key)
            self.key_edit.clear()
        self.set_status("Testing…", styles.TEXT_DIM)
        self.test_requested.emit()

    def bind_test_runner(self, runner: Callable[[], None]) -> None:
        self._runner = runner
