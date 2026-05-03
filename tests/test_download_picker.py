import pytest

from cc_extractor import download_picker
from cc_extractor.download_picker import _select_with_prompt


def test_select_with_prompt_returns_latest_on_blank(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt: "")

    assert _select_with_prompt(["2.1.116", "2.1.115"], "2.1.116", "Select") == "2.1.116"


def test_select_with_prompt_raises_runtime_error_on_cancel(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt: "q")

    with pytest.raises(RuntimeError, match="Download selection cancelled"):
        _select_with_prompt(["2.1.116", "2.1.115"], "2.1.116", "Select")


def test_select_version_tui_does_not_clear_every_frame(monkeypatch):
    import ratatui_py

    captured = {}

    class Tty:
        def isatty(self):
            return True

    class FakeApp:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def run(self, state):
            state.cancelled = True

    monkeypatch.setattr(download_picker.sys, "stdin", Tty())
    monkeypatch.setattr(download_picker.sys, "stdout", Tty())
    monkeypatch.setattr(ratatui_py, "App", FakeApp)

    with pytest.raises(RuntimeError, match="Download selection cancelled"):
        download_picker.select_version(["2.1.116"], "2.1.116", "Select")

    assert captured["clear_each_frame"] is False
