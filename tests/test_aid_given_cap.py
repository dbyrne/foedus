"""Tests for the aid_given cap (Patron remediation)."""
from dataclasses import replace

import pytest

from foedus.core import AidSpend, GameConfig


def test_default_cap_is_3():
    cfg = GameConfig()
    assert cfg.aid_given_cap == 3


def test_cap_is_configurable():
    cfg = GameConfig(aid_given_cap=5)
    assert cfg.aid_given_cap == 5
