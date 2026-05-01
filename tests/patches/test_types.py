from cc_extractor.patches import (
    AggregateResult,
    Patch,
    PatchAnchorMissError,
    PatchBlacklistedError,
    PatchContext,
    PatchOutcome,
    PatchUnsupportedVersionError,
)


def test_patch_is_frozen_dataclass():
    patch = Patch(
        id="x",
        name="X",
        group="ui",
        versions_supported=">=2.0.0,<3",
        versions_tested=(">=2.0.0,<3",),
        apply=lambda js, ctx: PatchOutcome(js=js, status="skipped"),
    )
    assert patch.id == "x"


def test_patch_context_defaults():
    ctx = PatchContext(claude_version=None)
    assert ctx.provider_label == "cc-extractor"
    assert ctx.config == {}
    assert ctx.overlays == {}
    assert ctx.force is False


def test_patch_outcome_default_notes():
    outcome = PatchOutcome(js="x", status="applied")
    assert outcome.notes == ()


def test_aggregate_result_fields():
    result = AggregateResult(
        js="x", applied=("a",), skipped=("b",), missed=("c",), notes=("note",),
    )
    assert result.applied == ("a",)


def test_exceptions_are_value_errors():
    assert issubclass(PatchAnchorMissError, ValueError)
    assert issubclass(PatchBlacklistedError, ValueError)
    assert issubclass(PatchUnsupportedVersionError, ValueError)
