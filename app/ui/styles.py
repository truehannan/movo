"""Visual design system (PROMPT section 18).

A restrained, modern developer-tool aesthetic: dark neutral background, one
accent, soft borders, small radius, strong typography hierarchy. No gradients,
no neon, no chatbot bubbles. All colours and the Qt stylesheet live here so the
rest of the UI stays free of hard-coded styling.
"""

from __future__ import annotations

# --- palette ---------------------------------------------------------------
BG = "#0f1115"          # window background
PANEL = "#171a21"       # panel surface
PANEL_HI = "#1e2230"  # slightly lighter surface
BORDER = "#272b34"
TEXT = "#e6e8ec"
TEXT_DIM = "#8b90a0"
TEXT_FAINT = "#5b606e"
ACCENT = "#5b8cff"      # restrained blue accent
ACCENT_DIM = "#33417a"
OK = "#3ecf8e"
WARN = "#e0a458"
ERR = "#e5605e"

RADIUS = 10
RADIUS_SM = 7

# --- status colours by state ----------------------------------------------
STATUS_COLORS = {
    "idle": TEXT_DIM,
    "connected": OK,
    "running": ACCENT,
    "verified": OK,
    "retry": WARN,
    "blocked": ERR,
    "stopped": ERR,
    "error": ERR,
    "done": OK,
}


def stylesheet() -> str:
    """The application-wide Qt stylesheet."""
    return f"""
    QWidget {{
        color: {TEXT};
        font-family: "Inter", "Segoe UI", "Cantarell", sans-serif;
        font-size: 13px;
    }}
    #Root {{
        background: {PANEL};
        border: 1px solid {BORDER};
        border-radius: {RADIUS}px;
    }}
    #TitleBar {{
        background: transparent;
    }}
    #AppName {{
        font-size: 13px;
        font-weight: 600;
        letter-spacing: 0.3px;
    }}
    #StatusDot {{
        font-size: 15px;
    }}
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
        background: {BG};
        border: 1px solid {BORDER};
        border-radius: {RADIUS_SM}px;
        padding: 7px 9px;
        selection-background-color: {ACCENT_DIM};
    }}
    QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
        border: 1px solid {ACCENT};
    }}
    QPushButton {{
        background: {PANEL_HI};
        border: 1px solid {BORDER};
        border-radius: {RADIUS_SM}px;
        padding: 8px 14px;
        font-weight: 600;
    }}
    QPushButton:hover {{ border: 1px solid {ACCENT_DIM}; }}
    QPushButton:disabled {{ color: {TEXT_FAINT}; }}
    QPushButton#Primary {{
        background: {ACCENT};
        border: 1px solid {ACCENT};
        color: #0b0e14;
    }}
    QPushButton#Primary:hover {{ background: #6f9bff; }}
    QPushButton#Danger {{
        background: transparent;
        border: 1px solid {ERR};
        color: {ERR};
    }}
    QPushButton#Ghost {{
        background: transparent;
        border: none;
        color: {TEXT_DIM};
        padding: 4px 8px;
    }}
    QPushButton#Ghost:hover {{ color: {TEXT}; }}
    QLabel#Dim {{ color: {TEXT_DIM}; }}
    QLabel#Faint {{ color: {TEXT_FAINT}; font-size: 12px; }}
    QLabel#H1 {{ font-size: 18px; font-weight: 700; }}
    QLabel#Metric {{ font-size: 12px; color: {TEXT_DIM}; }}
    QLabel#CurrentAction {{ font-size: 14px; font-weight: 600; }}
    #Card {{
        background: {BG};
        border: 1px solid {BORDER};
        border-radius: {RADIUS_SM}px;
    }}
    QListWidget {{
        background: {BG};
        border: 1px solid {BORDER};
        border-radius: {RADIUS_SM}px;
        padding: 4px;
    }}
    QListWidget::item {{ padding: 3px 4px; }}
    QScrollBar:vertical {{ background: transparent; width: 8px; }}
    QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 4px; }}
    QCheckBox {{ spacing: 8px; }}
    """
