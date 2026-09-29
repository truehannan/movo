"""Movo — Jev-powered desktop agent.

A floating Linux desktop computer-use agent powered by TypeSafe's Jev
System One decision model.

Architecture (see PROMPT sections 3 and 24):

    UI (PySide6)  ->  agent.controller  ->  agent.planner
                              |
                        agent.loop  (observe -> decide -> act -> verify)
                       /       |         \\
              desktop.*    jev.*        safety.*

Jev makes bounded typed decisions; application code owns the workflow and all
side effects.
"""

__version__ = "0.3.0"
