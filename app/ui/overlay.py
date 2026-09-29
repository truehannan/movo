"""Transient element-highlight overlay (PROMPT section 19).

A frameless, transparent, click-through top-level window that draws a rounded
accent rectangle over the element Jev selected on the *real* desktop, then
fades away. This makes the invisible decision visible during a demo.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from app.desktop.backend import Bounds
from app.ui import styles


class HighlightOverlay(QWidget):
    """A screen-space highlight that shows briefly and disappears."""

    def __init__(self) -> None:
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self._rect = QRect()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def flash(self, bounds: Bounds, duration_ms: int = 600) -> None:
        if bounds is None or bounds.is_empty():
            return
        pad = 4
        self.setGeometry(
            bounds.x - pad,
            bounds.y - pad,
            bounds.width + pad * 2,
            bounds.height + pad * 2,
        )
        self._rect = QRect(0, 0, self.width(), self.height())
        self.show()
        self.raise_()
        self._timer.start(max(150, duration_ms))

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt override)
        if self._rect.isEmpty():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        accent = QColor(styles.ACCENT)
        # Soft fill.
        fill = QColor(accent)
        fill.setAlpha(38)
        painter.setBrush(fill)
        pen = QPen(accent)
        pen.setWidth(2)
        painter.setPen(pen)
        r = self._rect.adjusted(1, 1, -1, -1)
        painter.drawRoundedRect(r, 6, 6)
