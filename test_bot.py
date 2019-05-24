import pytest


def test_everything_is_ok():
    assert "A" == "A"


def test_which_is_broken():
    assert "A" == "B"
