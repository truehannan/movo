"""Application entry point (PROMPT sections 30, 36 Phase 1).

Wires configuration, secrets, diagnostics, the real X11 desktop backend, and
the floating window, then runs the Qt event loop. Falls back gracefully if the
desktop backend cannot initialise (the UI still opens and reports the missing
capability).
"""

from __future__ import annotations

import sys


def _build_backend():
    """Construct the real desktop backend, or a safe stub if it cannot load."""
    try:
        from app.desktop.x11_backend import X11DesktopBackend

        return X11DesktopBackend()
    except Exception:
        # As a last resort, present an empty observation so the UI still runs.
        from app.desktop.backend import DesktopBackend, Observation, UIElement, WindowInfo

        class _NullBackend(DesktopBackend):
            def get_active_window(self) -> WindowInfo:
                return WindowInfo()

            def get_ui_tree(self) -> Observation:
                return Observation(window=WindowInfo(), accessibility_ok=False)

            def screenshot(self, path=None):
                return None

            def click(self, element: UIElement, button="left", double=False) -> bool:
                return False

            def type_text(self, text: str) -> bool:
                return False

            def press_key(self, key: str) -> bool:
                return False

            def scroll(self, dx: int, dy: int, element=None) -> bool:
                return False

            def drag(self, source, target, duration=0.4) -> bool:
                return False

        return _NullBackend()


def main() -> int:
    from PySide6.QtWidgets import QApplication

    from app.config.secrets import SecretStore
    from app.config.settings import Settings
    from app.diagnostics.capabilities import check_capabilities
    from app.diagnostics.logging import configure_logging
    from app.ui.window import MainWindow

    settings = Settings.load()
    configure_logging(debug=settings.debug_logging)
    secrets = SecretStore(prefer_keyring=settings.prefer_keyring)
    capabilities = check_capabilities()

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Jev Desktop Agent")
    app.setDesktopFileName("jev-desktop-agent")

    backend = _build_backend()
    window = MainWindow(backend, settings, secrets, capabilities)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
