import pytest

from cc_extractor.patches import PatchContext
from cc_extractor.patches.prompt_overlays import PATCH


def test_synthetic_applies(cli_js_synthetic):
    js = cli_js_synthetic("prompt-overlays")
    outcome = PATCH.apply(
        js,
        PatchContext(claude_version=None, overlays={"webfetch": "Use provider docs."}),
    )
    assert outcome.status == "applied"
    assert "Use provider docs." in outcome.js


def test_unknown_overlay_recorded_as_note(cli_js_synthetic):
    js = cli_js_synthetic("prompt-overlays")
    outcome = PATCH.apply(
        js,
        PatchContext(claude_version=None, overlays={"nonexistent_target": "x"}),
    )
    assert outcome.status in ("applied", "skipped", "missed")
    assert any("nonexistent_target" in note for note in outcome.notes)


def test_skipped_when_no_overlays(cli_js_synthetic):
    js = cli_js_synthetic("prompt-overlays")
    outcome = PATCH.apply(js, PatchContext(claude_version=None, overlays={}))
    assert outcome.status == "skipped"


def test_metadata_uses_warn_on_miss():
    assert PATCH.on_miss == "warn"
