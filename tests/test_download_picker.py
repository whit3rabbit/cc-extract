import pytest

from cc_extractor.download_picker import _select_with_prompt


def test_select_with_prompt_returns_latest_on_blank(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt: "")

    assert _select_with_prompt(["2.1.116", "2.1.115"], "2.1.116", "Select") == "2.1.116"


def test_select_with_prompt_raises_runtime_error_on_cancel(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt: "q")

    with pytest.raises(RuntimeError, match="Download selection cancelled"):
        _select_with_prompt(["2.1.116", "2.1.115"], "2.1.116", "Select")
