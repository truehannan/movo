#!/usr/bin/env python3
"""Proof of work: the REAL agent loop drives gnome-calculator.

This does not hand-code clicks. It runs Movo's actual pipeline —
observe (proven AT-SPI translation) -> build candidates -> a decider picks a
candidate by its translated name -> execute -> re-observe -> verify — and checks
the calculator's own display reaches 15 after "7 + 8 =".

The decider here is a deterministic stand-in for the model (no API key needed):
it selects the candidate whose translated name matches the next token. This
proves the translate->decide->act->verify plumbing end-to-end; swapping in Jev
or Laya changes only who picks the candidate id.

Run:  PYTHONPATH=. python scripts/proof_of_work.py
"""

from __future__ import annotations

import subprocess
import sys
import time

from app.desktop import lcu_engine as eng
from app.desktop.candidates import build_candidates, serialize_candidates
from app.desktop.lcu_backend import LcuBackend


def _display(backend) -> str:
    obs = backend.get_ui_tree()
    # gnome-calculator exposes the result as an editable/text element; also scan
    # names for a numeric readout.
    vals = [e.value for e in obs.elements if e.value]
    return " | ".join(v for v in vals if v)


def main() -> int:
    print("== Movo proof of work — REAL translate→decide→act loop ==\n")
    print("engine capabilities:", eng.capabilities(), "\n")

    proc = subprocess.Popen(["gnome-calculator"])
    time.sleep(3.5)

    backend = LcuBackend()
    backend.screenshot("/tmp/movo_pow_before.png")

    obs = backend.get_ui_tree()
    cands = build_candidates(obs, max_candidates=60)
    print(f"[observe] window={obs.window.title!r} elements={len(obs.elements)} "
          f"candidates={len(cands)}")
    print("[translate] candidate block the model would receive:")
    print("  " + serialize_candidates(cands)[:600].replace("\n", "\n  "))

    # The sequence a decision model would choose, one token per step.
    plan = ["7", "+", "8", "="]

    def decide(cands, token):
        """Stand-in decider: pick the candidate whose translated name == token."""
        for c in cands:
            if c.name.strip() == token:
                return c
        return None

    print("\n[loop] goal = compute 7 + 8 (expect 15)")
    for token in plan:
        obs = backend.get_ui_tree()                 # observe
        cands = build_candidates(obs, max_candidates=60)  # translate
        target = decide(cands, token)               # decide (by translation)
        if target is None:
            print(f"  token {token!r}: NO candidate matched — translation missing it")
            continue
        print(f"  decide CLICK #{target.id} {target.role.value} {target.name!r} "
              f"@ {target.element.bounds.center}")
        backend.click(target.element)               # act
        time.sleep(0.4)

    time.sleep(0.6)
    after = _display(backend)                        # verify
    backend.screenshot("/tmp/movo_pow_after.png")
    got_15 = "15" in after
    print(f"\n[verify] calculator display now: {after!r}")
    print("PROOF OF WORK:", "PASS ✅ (real loop computed 15)" if got_15 else "FAIL ❌")

    try:
        proc.terminate()
    except Exception:
        pass
    backend.close()
    return 0 if got_15 else 1


if __name__ == "__main__":
    sys.exit(main())
