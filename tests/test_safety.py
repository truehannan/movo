"""Tests for the safety policy (PROMPT sections 21, 25)."""

from __future__ import annotations

from app.jev.schemas import Operation
from app.safety.policy import classify


def test_plain_click_is_safe():
    v = classify(Operation.CLICK, "Search", None)
    assert v.allowed and not v.destructive


def test_delete_button_needs_confirmation():
    v = classify(Operation.CLICK, "Delete account", None)
    assert not v.allowed and v.destructive


def test_rm_rf_typing_blocked():
    v = classify(Operation.TYPE, None, "rm -rf /home/user")
    assert not v.allowed and v.destructive


def test_sudo_typing_blocked():
    v = classify(Operation.TYPE, None, "sudo apt-get install foo")
    assert not v.allowed


def test_typing_normal_text_is_safe():
    v = classify(Operation.TYPE, None, "python 3.14 release notes")
    assert v.allowed and not v.destructive


def test_payment_button_needs_confirmation():
    assert not classify(Operation.CLICK, "Confirm payment", None).allowed


def test_shutdown_command_blocked():
    assert not classify(Operation.PRESS_KEY, None, "shutdown now").allowed


def test_fork_bomb_blocked():
    assert not classify(Operation.TYPE, None, ":(){ :|:& };:").allowed
