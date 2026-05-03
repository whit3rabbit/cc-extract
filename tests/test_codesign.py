import subprocess

from cc_extractor.binary_patcher.codesign import try_adhoc_sign


def test_try_adhoc_sign_non_darwin_returns_no_codesign(monkeypatch):
    monkeypatch.setattr("cc_extractor.binary_patcher.codesign.platform.system", lambda: "Linux")

    result = try_adhoc_sign("/some/path")

    assert result.signed is False
    assert result.reason == "no-codesign"


def test_try_adhoc_sign_darwin_handles_missing_codesign(monkeypatch):
    monkeypatch.setattr("cc_extractor.binary_patcher.codesign.platform.system", lambda: "Darwin")

    def missing(*args, **kwargs):
        raise FileNotFoundError("codesign")

    monkeypatch.setattr("cc_extractor.binary_patcher.codesign.subprocess.run", missing)

    result = try_adhoc_sign("/some/path")

    assert result.signed is False
    assert result.reason == "no-codesign"


def test_try_adhoc_sign_darwin_handles_failed_codesign(monkeypatch):
    monkeypatch.setattr("cc_extractor.binary_patcher.codesign.platform.system", lambda: "Darwin")

    def failed(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 1, stdout="", stderr="not a Mach-O")

    monkeypatch.setattr("cc_extractor.binary_patcher.codesign.subprocess.run", failed)

    result = try_adhoc_sign("/some/path")

    assert result.signed is False
    assert result.reason == "failed"


def test_try_adhoc_sign_terminates_options_before_binary_path(monkeypatch):
    monkeypatch.setattr("cc_extractor.binary_patcher.codesign.platform.system", lambda: "Darwin")
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr("cc_extractor.binary_patcher.codesign.subprocess.run", fake_run)

    result = try_adhoc_sign("-looks-like-a-flag")

    assert result.signed is True
    assert calls == [["codesign", "--force", "--sign", "-", "--", "-looks-like-a-flag"]]
