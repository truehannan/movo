"""Model-selection view: choose Jev (cloud) or Laya (local).

Two cards. Choosing **Jev** reveals the API-key field (cloud, calibrated, needs
a key). Choosing **Laya** provisions a local, private model — installing the
runtime and downloading the checkpoint on demand with a visible progress bar,
then running it entirely on the user's machine with no key.

The heavy work (install/download/start) runs off the UI thread; this view only
emits intent and renders progress pushed back to it.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.config.secrets import SecretStore, mask_key
from app.config.settings import Settings
from app.ui import styles


class _ModelCard(QWidget):
    clicked = Signal()

    def __init__(self, title: str, subtitle: str, tag: str) -> None:
        super().__init__()
        self.setObjectName("ModelCard")
        self.setProperty("selected", False)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(4)
        top = QHBoxLayout()
        name = QLabel(title)
        name.setStyleSheet("font-size: 15px; font-weight: 700; letter-spacing: -0.2px;")
        badge = QLabel(tag)
        badge.setObjectName("Faint")
        top.addWidget(name)
        top.addStretch(1)
        top.addWidget(badge)
        lay.addLayout(top)
        sub = QLabel(subtitle)
        sub.setObjectName("Dim")
        sub.setWordWrap(True)
        lay.addWidget(sub)

    def set_selected(self, on: bool) -> None:
        self.setProperty("selected", on)
        # Re-polish so the [selected] stylesheet rule re-applies.
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()


class ModelView(QWidget):
    """Lets the user pick and provision a decision provider."""

    back = Signal()
    provider_chosen = Signal(str)  # "jev" | "laya"
    provision_laya_requested = Signal()
    save_key_requested = Signal(str)
    test_requested = Signal()

    def __init__(self, settings: Settings, secrets: SecretStore) -> None:
        super().__init__()
        self._settings = settings
        self._secrets = secrets
        self._provider = settings.provider
        self._build()
        self._reflect_selection()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 12, 18, 16)
        root.setSpacing(12)

        header = QHBoxLayout()
        back = QPushButton("‹ Back")
        back.setObjectName("Ghost")
        back.clicked.connect(self.back.emit)
        title = QLabel("Model")
        title.setObjectName("H1")
        header.addWidget(back)
        header.addWidget(title)
        header.addStretch(1)
        root.addLayout(header)

        cards = QHBoxLayout()
        cards.setSpacing(12)
        self.jev_card = _ModelCard(
            "Jev", "Hosted decision model. Fast, calibrated. Needs an API key.", "cloud"
        )
        self.laya_card = _ModelCard(
            "Laya", "Open-weight model that runs on this machine. Private, no key.", "local"
        )
        self.jev_card.clicked.connect(lambda: self._choose("jev"))
        self.laya_card.clicked.connect(lambda: self._choose("laya"))
        cards.addWidget(self.jev_card)
        cards.addWidget(self.laya_card)
        root.addLayout(cards)

        # Jev key row (shown when Jev is selected).
        self.key_row = QWidget()
        krl = QVBoxLayout(self.key_row)
        krl.setContentsMargins(0, 0, 0, 0)
        krl.setSpacing(8)
        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText("TypeSafe / Jev API key")
        if self._secrets.has_api_key():
            self.key_edit.setPlaceholderText(
                f"stored: {mask_key(self._secrets.get_api_key())}"
            )
        krow = QHBoxLayout()
        test_btn = QPushButton("Test")
        test_btn.clicked.connect(self._on_test)
        save_btn = QPushButton("Save key")
        save_btn.setObjectName("Primary")
        save_btn.clicked.connect(self._on_save_key)
        krow.addWidget(test_btn)
        krow.addStretch(1)
        krow.addWidget(save_btn)
        krl.addWidget(self.key_edit)
        krl.addLayout(krow)
        root.addWidget(self.key_row)

        # Laya provisioning row (shown when Laya is selected).
        self.laya_row = QWidget()
        lrl = QVBoxLayout(self.laya_row)
        lrl.setContentsMargins(0, 0, 0, 0)
        lrl.setSpacing(8)
        self.laya_status = QLabel("")
        self.laya_status.setObjectName("Faint")
        self.laya_status.setWordWrap(True)
        self.laya_progress = QProgressBar()
        self.laya_progress.setRange(0, 0)  # indeterminate while working
        self.laya_progress.setTextVisible(False)
        self.laya_progress.setFixedHeight(4)
        self.laya_progress.hide()
        self.provision_btn = QPushButton("Set up Laya locally")
        self.provision_btn.setObjectName("Primary")
        self.provision_btn.clicked.connect(self._on_provision)
        lrl.addWidget(self.laya_status)
        lrl.addWidget(self.laya_progress)
        lrl.addWidget(self.provision_btn)
        root.addWidget(self.laya_row)

        root.addStretch(1)
        self.status = QLabel("")
        self.status.setObjectName("Faint")
        root.addWidget(self.status)

    # --- selection -------------------------------------------------------
    def _choose(self, provider: str) -> None:
        self._provider = provider
        self._settings.provider = provider
        self._settings.save()
        self._reflect_selection()
        self.provider_chosen.emit(provider)

    def _reflect_selection(self) -> None:
        is_jev = self._provider == "jev"
        self.jev_card.set_selected(is_jev)
        self.laya_card.set_selected(not is_jev)
        self.key_row.setVisible(is_jev)
        self.laya_row.setVisible(not is_jev)

    # --- jev key ---------------------------------------------------------
    def _on_save_key(self) -> None:
        key = self.key_edit.text().strip()
        if key:
            self.save_key_requested.emit(key)
            self.key_edit.clear()
            self.key_edit.setPlaceholderText(f"stored: {mask_key(key)}")
            self.set_status("Key saved.", styles.OK)

    def _on_test(self) -> None:
        key = self.key_edit.text().strip()
        if key:
            self.save_key_requested.emit(key)
            self.key_edit.clear()
        self.set_status("Testing…", styles.WHITE_MUTED)
        self.test_requested.emit()

    # --- laya ------------------------------------------------------------
    def _on_provision(self) -> None:
        self.provision_btn.setEnabled(False)
        self.laya_progress.show()
        self.set_laya_status("Starting setup…")
        self.provision_laya_requested.emit()

    def set_laya_status(self, text: str) -> None:
        self.laya_status.setText(text)

    def set_laya_done(self, ok: bool) -> None:
        self.laya_progress.hide()
        self.provision_btn.setEnabled(True)
        if ok:
            self.provision_btn.setText("Laya is ready ✓")
            self.set_laya_status("Laya is installed and running locally.")
        else:
            self.provision_btn.setText("Retry Laya setup")

    def reflect_laya_status(self, status) -> None:
        """Update the button/label from a LayaStatus snapshot."""
        if status.running:
            self.provision_btn.setText("Laya is ready ✓")
            self.set_laya_status("Laya is installed and running locally.")
        elif status.installed and status.checkpoint_present:
            self.provision_btn.setText("Start Laya")
            self.set_laya_status("Installed. Click to start the local server.")
        elif status.installed:
            self.provision_btn.setText("Download model & start")
            self.set_laya_status("Runtime installed; the model still needs downloading.")
        else:
            self.provision_btn.setText("Set up Laya locally")
            self.set_laya_status("One-time setup downloads ~850 MB and runs fully offline after.")

    def set_status(self, text: str, color: str = styles.WHITE_MUTED) -> None:
        self.status.setText(text)
        self.status.setStyleSheet(f"color: {color};")
