"""Visual design system for Movo.

Adapted from the DESIGN.md guidance (Apple-style: one quiet accent, tight
typography, generous whitespace, minimal chrome, a single soft product shadow)
to Movo's palette: **primary near-pitch-black, secondary white**. The window is
one dark surface; white carries the interface; a single restrained accent marks
the live/action state. No gradients, no neon, no bubbles.
"""

from __future__ import annotations

# --- palette (black primary / white secondary) ----------------------------
INK = "#050506"          # near-pitch-black — the primary surface
INK_RAISED = "#0d0d10"   # slightly raised cards/inputs on the black
INK_HAIRLINE = "#1c1c20"  # hairline borders (rgba white ~0.08 equivalent)
WHITE = "#ffffff"         # secondary — all primary text and the action fill
WHITE_MUTED = "#a1a1a6"   # secondary copy
WHITE_FAINT = "#6e6e73"   # captions, disabled, legal
ACCENT = "#2997ff"        # the single on-dark action/live accent (DESIGN sky-blue)
OK = "#30d158"
WARN = "#ffd60a"
ERR = "#ff453a"

# radius scale from DESIGN.md
R_SM = 8
R_MD = 11
R_LG = 18
R_PILL = 9999

# Back-compat aliases used elsewhere in the codebase.
BG = INK
PANEL = INK
PANEL_HI = INK_RAISED
BORDER = INK_HAIRLINE
TEXT = WHITE
TEXT_DIM = WHITE_MUTED
TEXT_FAINT = WHITE_FAINT
ACCENT_DIM = "#1b4a7a"
RADIUS = R_LG
RADIUS_SM = R_SM

STATUS_COLORS = {
    "idle": WHITE_FAINT,
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
        color: {WHITE};
        font-family: "SF Pro Text", "Inter", "Segoe UI", "Cantarell", sans-serif;
        font-size: 13px;
    }}
    #Root {{
        background: {INK};
        border: 1px solid {INK_HAIRLINE};
        border-radius: {R_LG}px;
    }}
    #TitleBar {{ background: transparent; }}
    #Scroll {{ background: transparent; border: none; }}
    #AppName {{
        font-size: 14px;
        font-weight: 600;
        letter-spacing: -0.2px;
    }}
    #StatusDot {{ font-size: 13px; }}

    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
        background: {INK_RAISED};
        border: 1px solid {INK_HAIRLINE};
        border-radius: {R_SM}px;
        padding: 9px 12px;
        color: {WHITE};
        selection-background-color: {ACCENT};
    }}
    QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{ border: 1px solid {WHITE_MUTED}; }}
    QLineEdit::placeholder {{ color: {WHITE_FAINT}; }}

    /* Primary action: white pill on black (secondary colour carries the action). */
    QPushButton {{
        background: {INK_RAISED};
        border: 1px solid {INK_HAIRLINE};
        border-radius: {R_PILL}px;
        padding: 9px 18px;
        font-weight: 600;
        color: {WHITE};
    }}
    QPushButton:hover {{ border: 1px solid {WHITE_MUTED}; }}
    QPushButton:pressed {{ padding-top: 10px; padding-bottom: 8px; }}
    QPushButton:disabled {{ color: {WHITE_FAINT}; border-color: {INK_HAIRLINE}; }}
    QPushButton#Primary {{
        background: {WHITE};
        border: 1px solid {WHITE};
        color: {INK};
    }}
    QPushButton#Primary:hover {{ background: #f0f0f2; }}
    QPushButton#Primary:disabled {{ background: {INK_HAIRLINE}; color: {WHITE_FAINT}; border-color: {INK_HAIRLINE}; }}
    QPushButton#Danger {{
        background: transparent;
        border: 1px solid {ERR};
        color: {ERR};
    }}
    QPushButton#Ghost {{
        background: transparent; border: none; color: {WHITE_MUTED};
        padding: 4px 8px; border-radius: {R_SM}px;
    }}
    QPushButton#Ghost:hover {{ color: {WHITE}; }}

    QLabel#Dim {{ color: {WHITE_MUTED}; }}
    QLabel#Faint {{ color: {WHITE_FAINT}; font-size: 12px; }}
    QLabel#H1 {{ font-size: 22px; font-weight: 700; letter-spacing: -0.4px; }}
    QLabel#CurrentAction {{ font-size: 15px; font-weight: 600; letter-spacing: -0.2px; }}
    QLabel#UpdatePill {{
        background: {ACCENT}; color: {INK};
        border-radius: {R_PILL}px; padding: 3px 10px; font-size: 12px; font-weight: 600;
    }}

    #Card {{
        background: {INK_RAISED};
        border: 1px solid {INK_HAIRLINE};
        border-radius: {R_MD}px;
    }}
    /* Selectable model cards. */
    #ModelCard {{
        background: {INK_RAISED};
        border: 1px solid {INK_HAIRLINE};
        border-radius: {R_LG}px;
    }}
    #ModelCard[selected="true"] {{ border: 2px solid {WHITE}; }}

    QListWidget {{
        background: {INK_RAISED};
        border: 1px solid {INK_HAIRLINE};
        border-radius: {R_SM}px;
        padding: 4px;
    }}
    #LogView {{
        background: #000000;
        border: 1px solid {INK_HAIRLINE};
        border-radius: {R_SM}px;
        color: {WHITE_MUTED};
        font-family: "SF Mono", "DejaVu Sans Mono", "Consolas", monospace;
        font-size: 11px;
    }}
    QListWidget::item {{ padding: 3px 4px; }}
    QScrollBar:vertical {{ background: transparent; width: 8px; }}
    QScrollBar::handle:vertical {{ background: {INK_HAIRLINE}; border-radius: 4px; }}
    QCheckBox {{ spacing: 8px; }}
    QProgressBar {{ background: {INK_HAIRLINE}; border: none; border-radius: 2px; }}
    QProgressBar::chunk {{ background: {ACCENT}; border-radius: 2px; }}
    """
