"""Pytest bootstrap.

Ensures the repository root is on ``sys.path`` so tests can import both the
``agent`` package and the ``tests`` helper package (e.g. ``tests.mock_jev``)
regardless of how pytest is invoked. A root ``conftest.py`` is added to
``sys.path`` by pytest automatically, but we also insert it explicitly so CI
runs (which do not set PYTHONPATH) resolve ``tests`` as a package.
"""

from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
