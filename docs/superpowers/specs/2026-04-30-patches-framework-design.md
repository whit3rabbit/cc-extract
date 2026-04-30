# Patches framework and tiered test harness

Date: 2026-04-30
Status: Draft (awaiting user review)

## Goals

1. Establish a uniform per-file patch module layout under `cc_extractor/patches/<id>.py`, with metadata-driven version compatibility.
2. Migrate the 11 existing tweaks from `cc_extractor/variants/tweaks.py` into that layout, behind a backwards-compatible shim.
3. Ship a tiered test framework so we can answer "does patch X still work against Claude Code version Y" before porting any of the ~30 remaining tweakcc patches.

## Non-goals

- Porting more patches beyond the existing 11. Deferred until the framework lands and we validate it against the existing set.
- Changing the workspace patch-package format (`.cc-extractor/patches/packages/<id>/<version>/patch.json`). That is the binary-operation manifest layer; this work is the regex/JS-rewrite layer.
- Re-architecting `cc_extractor/variants/`, `cc_extractor/binary_patcher/`, or the TUI.

## Background

`vendor/tweakcc/src/patches/` contains ~45 TypeScript patches that rewrite the minified `cli.js` shipped inside Claude Code. Today, 11 of those have Python ports living as functions in `cc_extractor/variants/tweaks.py` (themes, prompt-overlays, show-more-items, model-customizations, hide-startup-banner, hide-startup-clawd, hide-ctrl-g, suppress-line-numbers, auto-accept-plan-mode, allow-custom-agent-models, patches-applied-indication; plus three env-backed tweaks: context-limit, file-read-limit, subagent-model).

The current setup has three problems:

1. **No version awareness.** Anchor regexes break across Claude Code releases; today there is no way to declare which versions a patch was tested against, and no warning when a patch is applied to an untested version.
2. **No regression coverage against real binaries.** `tests/test_variant_tweaks.py` uses synthetic snippets that pass even if the regex would never match a real `cli.js`.
3. **The single `tweaks.py` file does not scale.** At 309 lines for 11 patches, adding 30 more would push it past 2000 lines.

Decision: build the framework first, validate it against the existing 11, then port new patches incrementally using it.

## Architecture

### Module layout

```
cc_extractor/
  patches/
    __init__.py            # Patch dataclass, PatchContext, PatchOutcome, exceptions, apply_patches
    _registry.py           # explicit list of (id -> Patch) imports + lookups
    _helpers.py            # ports of vendor/tweakcc/src/patches/helpers.ts (find React var, etc.)
    _versions.py           # SemVer range parser, version-match logic, warning emitter
    system_prompts.py      # pre-existing; not adopted into Patch interface in this work (out of scope, separate feature)
    themes.py              # adapter over binary_patcher/theme.py
    prompt_overlays.py     # adapter over binary_patcher/prompts.apply_prompts
    show_more_items.py
    model_customizations.py
    hide_startup_banner.py
    hide_startup_clawd.py
    hide_ctrl_g.py
    suppress_line_numbers.py
    auto_accept_plan_mode.py
    allow_custom_agent_models.py
    patches_applied_indication.py
    # env-backed tweaks (context-limit, file-read-limit, subagent-model) stay in variants/tweaks.py;
    # they do not rewrite JS so they do not need a Patch module.

  variants/
    tweaks.py              # ~50-line compatibility shim:
                           #   - re-exports DEFAULT_TWEAK_IDS, ENV_TWEAK_IDS, CURATED_TWEAK_IDS
                           #   - re-exports apply_variant_tweaks (now delegates to apply_patches)
                           #   - keeps env_for_tweaks, normalize_tweak_ids
                           #   - keeps TweakPatchError as an alias of PatchAnchorMissError

tests/
  patches/                 # NEW: L1 + L2 unit tests, per patch
    conftest.py            # fixtures: cli_js_real, cli_js_synthetic, parse_js
    _pinned.py             # PINNED_VERSIONS = ("2.0.40", "2.1.123")
    fixtures/synthetic.py  # hand-crafted JS snippets per patch
    test_registry.py       # cross-patch invariants
    test_themes.py
    test_hide_startup_banner.py
    ...
  patches_smoke/           # NEW: L3 - gated by CC_EXTRACTOR_REAL_BINARY=1
    test_variant_smoke.py
  patches_behavioral/      # NEW: L4 - gated by CC_EXTRACTOR_TUI_MCP=1
    conftest.py            # variant_factory fixture, one variant per test
    test_<patch_id>.py     # Python tests for flow-driven patches
    snapshots/<patch_id>.txt
```

### Module boundaries

- `patches/__init__.py` exports `Patch`, `PatchContext`, `PatchOutcome`, `AggregateResult`, `PatchAnchorMissError`, `PatchUnsupportedVersionError`, `PatchBlacklistedError`, `apply_patches(js, ids, ctx) -> AggregateResult`. No dependency on `variants/` or `binary_patcher/`.
- `patches/_registry.py` is the single source of truth for `id -> Patch`. Explicit imports (`from . import themes; REGISTRY = {themes.PATCH.id: themes.PATCH, ...}`). No auto-discovery: ordering and gating stay readable in one place.
- `patches/_helpers.py` is shared regex utilities (port of `vendor/tweakcc/src/patches/helpers.ts`). No dependency on individual patch modules.
- `variants/tweaks.py` becomes a thin compatibility shim. Existing `monkeypatch.setattr("cc_extractor.variants.tweaks.X", ...)` patterns keep working.

### Why this shape

- Mirrors `vendor/tweakcc/src/patches/` 1:1, so future ports are mechanical: open `<name>.ts`, write `<name>.py`.
- Each patch has one home for its code and its test (`tests/patches/test_<id>.py`).
- Test tiers live in their own directories, gated by env vars (matches existing `tests/test_integration_real_binary.py` pattern).
- The shim keeps the public surface stable: nothing outside `cc_extractor/patches/` and `cc_extractor/variants/tweaks.py` needs to change in this work.

## Data types

Defined in `cc_extractor/patches/__init__.py`.

```python
@dataclass(frozen=True)
class Patch:
    id: str
    name: str
    group: str                            # "ui" | "thinking" | "prompts" | "tools" | "system"
    versions_supported: str               # SemVer range, e.g. ">=2.0.20,<3"
    versions_tested: tuple[str, ...]      # exact versions in the matrix
    versions_blacklisted: tuple[str, ...] = ()
    on_miss: str = "fatal"                # "fatal" | "skip" | "warn"
    apply: Callable[[str, "PatchContext"], "PatchOutcome"]

@dataclass(frozen=True)
class PatchContext:
    claude_version: Optional[str]         # None when caller cannot supply it
    provider_label: str = "cc-extractor"
    config: Mapping[str, Any] = field(default_factory=dict)
    overlays: Mapping[str, str] = field(default_factory=dict)
    force: bool = False                   # bypass blacklist + unsupported-version refusal

@dataclass(frozen=True)
class PatchOutcome:
    js: str                               # patched JS (== input if skipped)
    status: str                           # "applied" | "skipped" | "missed"
    notes: tuple[str, ...] = ()           # e.g., per-target prompt overlay misses

@dataclass(frozen=True)
class AggregateResult:
    js: str
    applied: tuple[str, ...]
    skipped: tuple[str, ...]
    missed: tuple[str, ...]
    notes: tuple[str, ...]

class PatchAnchorMissError(ValueError): ...
class PatchUnsupportedVersionError(ValueError): ...
class PatchBlacklistedError(ValueError): ...
```

## Apply flow

`apply_patches(js, ids, ctx)` runs each requested patch in registry order:

1. **Pre-flight** per patch:
   - If `ctx.claude_version` is set:
     - In `versions_blacklisted`: raise `PatchBlacklistedError` (unless `ctx.force`).
     - Not satisfied by `versions_supported`: raise `PatchUnsupportedVersionError` (unless `ctx.force`).
     - Satisfied but not in `versions_tested`: emit `warnings.warn("patch X not tested against version Y; last tested Z")`. Apply.
   - If `ctx.claude_version` is None: skip pre-flight, log a debug-level note. Mirrors today's behavior where most callers do not pass a version.

2. **Apply.** Call `patch.apply(js, ctx)`. The function returns a `PatchOutcome`.

3. **Anchor-miss handling.** If `outcome.status == "missed"`:
   - `on_miss="fatal"`: raise `PatchAnchorMissError(patch.id)`.
   - `on_miss="warn"`: `warnings.warn(...)`, treat as skipped.
   - `on_miss="skip"`: record silently, treat as skipped.

4. **Aggregate.** Return `AggregateResult(js, applied=(...), skipped=(...), missed=(...), notes=(...))`. The shim in `variants/tweaks.py` adapts this into today's `TweakResult(js, applied, skipped, missing)`.

### SemVer range syntax

`_versions.py` implements a small, dedicated parser. Grammar:

- Comparators: `>=`, `>`, `<=`, `<`, `==`.
- AND: comma-separated within a clause: `>=2.0.20,<3`.
- OR: `||` between clauses: `>=2.0.20,<2.1 || >=2.1.10,<3`.
- Versions are dotted three-component numeric (no pre-release, no build metadata). Sufficient for Claude Code's `MAJOR.MINOR.PATCH` scheme.

Vendored, ~40 lines, no runtime dependency. Rationale: the project keeps its runtime stdlib-only. Adding `packaging` is over-spec for the grammar we need and its `Version` class is built around PEP 440, not SemVer.

### `claude_version` plumbing

The new `apply_patches` lives in `cc_extractor/patches/__init__.py`. It is distinct from the existing `cc_extractor.binary_patcher.index.apply_patches` (which is the workspace-patch-package apply layer and is unaffected by this work).

- `apply_variant_tweaks(...)` (the existing public surface in `variants/tweaks.py`) gains an optional `claude_version` parameter and forwards it into `PatchContext` when delegating to `cc_extractor.patches.apply_patches`.
- Callers in `variant_actions.py` and `patch_workflow.py` pass it through when known.
- Existing callers that do not pass it get `None` and preserve current behavior (no version checks run, no warnings).
- New CLI handlers populate `claude_version` from the binary metadata when available.

## Test framework

### L1 + L2 (fast, runs under default `pytest`)

**Layout:**
```
tests/patches/
  conftest.py
  _pinned.py
  fixtures/synthetic.py
  test_registry.py
  test_<patch_id>.py
```

**Per-patch test file pattern:**
```python
@pytest.mark.parametrize("version", PINNED_VERSIONS)
def test_themes_l1_anchor_matches(cli_js_real, version):
    js = cli_js_real(version)
    outcome = themes.PATCH.apply(js, PatchContext(claude_version=version, config=...))
    assert outcome.status == "applied"

@pytest.mark.parametrize("version", PINNED_VERSIONS)
def test_themes_l2_patched_js_parses(cli_js_real, version, parse_js):
    js = cli_js_real(version)
    outcome = themes.PATCH.apply(js, PatchContext(claude_version=version, config=...))
    parse_js(outcome.js)   # raises on syntax error

def test_themes_synthetic_minimal(cli_js_synthetic):
    js = cli_js_synthetic("themes")
    outcome = themes.PATCH.apply(js, PatchContext(claude_version=None, config=...))
    assert outcome.status == "applied"
```

**Fixtures:**

- `cli_js_real(version)`: extracts the entry JS from a Claude Code binary in `downloads/`. If absent, downloads it via `cc_extractor.downloader` and caches. First run on a fresh checkout pulls each pinned binary (~30s each); subsequent runs are seconds. Cache location is the existing `downloads/` directory; gitignored.
- `parse_js(js)`: shells out to `node --check -`. Asserts exit code 0. Skip-with-message (not fail) if Node is not on PATH so L1 stays runnable on minimal envs while still catching parse errors when Node is available. CI has Node.
- `cli_js_synthetic(patch_id)`: returns a small handcrafted snippet from `fixtures/synthetic.py`. One snippet per patch, kept minimal. Goal: "anchor regex still matches the shape" for fast iteration during a port.

**Pinned versions** live in `tests/patches/_pinned.py`:
```python
PINNED_VERSIONS = ("2.0.40", "2.1.123")
```
Adjustable in one place. Rationale for these picks: latest stable on the 2.1 line plus an older 2.0.x to catch range drift.

**Registry-level tests** (`tests/patches/test_registry.py`):

- Every registered patch has non-empty `versions_tested`.
- Every entry in `versions_tested` satisfies `versions_supported`.
- No entry in `versions_tested` is also in `versions_blacklisted`.
- Registry has no duplicate ids.
- Each `versions_supported` parses cleanly.

### L3 (gated, real binary smoke)

`tests/patches_smoke/test_variant_smoke.py`. Skipped unless `CC_EXTRACTOR_REAL_BINARY=1`. Builds a variant with the default tweak set against each pinned version, launches the binary with a probe argument (`--version` or `--help`, whichever short-circuits Bun init), asserts exit code 0 and a known string in stdout. Mirrors the existing `tests/test_integration_real_binary.py` pattern.

### L4 (gated, TUI MCP behavioral)

`tests/patches_behavioral/`. Skipped unless `CC_EXTRACTOR_TUI_MCP=1`. **One variant per test** (clean isolation, ~10s setup each). The conftest fixture builds, runs, and tears down a fresh variant per test function.

Two test styles:

1. **Snapshot tests** for visibility-toggle patches. Launch variant, send a fixed key sequence, capture rendered screen, diff against `snapshots/<patch_id>.txt`. Update workflow: re-run with `CC_EXTRACTOR_UPDATE_SNAPSHOTS=1` to regenerate. Use case: hide-startup-banner, hide-startup-clawd, patches-applied-indication, suppress-line-numbers.
2. **Flow tests** for patches with branching/conditional checks. Python test that drives the variant through a multi-step interaction with assertions between steps. Use case: auto-accept-plan-mode, model-customizations.

Skip-by-default when TUI MCP is not reachable. Pytest collects the tests and prints `SKIPPED [reason: TUI MCP not available]` so the suite stays informational on machines without the MCP wired up.

### Test ergonomics

- `pytest -q` runs L1 + L2 only. Fast, no network unless fixtures need to download.
- `pytest -q tests/patches/test_themes.py` runs one patch's tests.
- `CC_EXTRACTOR_REAL_BINARY=1 pytest -q tests/patches_smoke` runs L3.
- `CC_EXTRACTOR_TUI_MCP=1 pytest -q tests/patches_behavioral` runs L4.
- `tests/run_all.sh` runs the full ladder for someone who wants the works.

## Errors and observability

| Situation | Default behavior | Override |
|---|---|---|
| Patch anchor not found | Raise `PatchAnchorMissError` (per `on_miss="fatal"`) | Patch declares `on_miss="warn"` (e.g., prompt overlays) or `"skip"` |
| Version blacklisted | Raise `PatchBlacklistedError` | `PatchContext.force=True` |
| Version not in `versions_supported` | Raise `PatchUnsupportedVersionError` | `PatchContext.force=True` |
| Version not in `versions_tested` (but supported) | `warnings.warn(...)`, apply | None - informational |
| `claude_version` is None | Skip pre-flight, debug log | None - preserves today's behavior |
| Patched JS fails to parse (L2 only) | Test fails | None - this is a bug |
| Node unavailable for L2 | Test skipped with reason | None |

The shim in `variants/tweaks.py` catches the new errors and re-raises as `TweakPatchError(patch_id, detail)` so existing callers do not change.

### Observability

- `apply_patches` returns `AggregateResult` with `applied`, `skipped`, `missed`, `notes`. CLI handlers that already log applied/skipped (e.g., `cmd_apply_binary`) gain the new fields.
- New CLI flag on `apply-binary` and `variant create`: `--patches-report <path>` writes the full `AggregateResult` as JSON for post-mortem. Optional, off by default.
- `warnings.warn` for untested-version cases lets users see the warning once per (patch, version) pair without log spam.

## Migration plan

Each step is independently reviewable and leaves the test suite green.

1. **Scaffold the framework.** Add `cc_extractor/patches/__init__.py` types, `_registry.py` (initially empty), `_helpers.py`, `_versions.py`. Add `tests/patches/test_registry.py` with a placeholder that passes against an empty registry. No behavior change.

2. **Migrate one patch as a worked example.** `hide_startup_banner.py`: move the function out of `variants/tweaks.py`, wrap in `Patch`, register it. Update the shim in `tweaks.py` to delegate this id to the registry while keeping the rest in place. Add `tests/patches/test_hide_startup_banner.py` (L1 + L2). Run the full existing test suite; should pass unchanged.

3. **Migrate the remaining 8 simple patches** in one or two commits, same pattern: show-more-items, model-customizations, hide-startup-clawd, hide-ctrl-g, suppress-line-numbers, auto-accept-plan-mode, allow-custom-agent-models, patches-applied-indication. Each gets `tests/patches/test_<id>.py`.

4. **Migrate themes and prompt-overlays.** These are special: they wrap `binary_patcher/theme.py` and `binary_patcher/prompts.py`. The patch module is a thin adapter. Existing tests for `binary_patcher/theme.py` etc. stay where they are; the new `tests/patches/test_themes.py` and `test_prompt_overlays.py` cover the adapter.

5. **Add L3 smoke harness.** One parametrized test that builds a default-tweak variant against each pinned version, runs the binary with a probe arg, asserts clean exit. Gated by `CC_EXTRACTOR_REAL_BINARY=1`.

6. **Add L4 harness skeleton + one snapshot test.** `hide_startup_banner` is the simplest case (banner appears or does not). Gated by `CC_EXTRACTOR_TUI_MCP=1`. Subsequent L4 coverage is incremental and not blocking framework completion.

7. **Document.** A short `docs/patches.md`: how to add a patch, the metadata fields, how to run each test tier, how to update snapshots.

After step 4, `variants/tweaks.py` is a ~50-line shim and the existing test suite passes unchanged thanks to the shim's compatibility surface.

## Risks and mitigations

- **Shim drift.** If `apply_variant_tweaks` semantics drift between the registry and the shim, downstream callers misbehave. Mitigation: the shim is exercised by the existing `tests/test_variant_tweaks.py` suite, which stays as the contract test for the public surface.
- **First-run download cost in CI.** `cli_js_real` downloads two binaries on first run (~30s each). Mitigation: cache under `downloads/` is reusable across CI runs that share a workspace; for ephemeral runners, document the cost upfront and consider a CI cache key.
- **Snapshot churn.** L4 snapshot tests can flake if the unrelated terminal layout shifts (e.g., width). Mitigation: pin terminal dimensions in the variant launch fixture; capture only the relevant screen region per patch where possible.
- **`packaging` vs vendored SemVer.** A vendored parser can fall behind real SemVer edge cases. Mitigation: scope is intentionally small (numeric major.minor.patch); if we ever need pre-release/build metadata we revisit and may switch to `packaging`.

## Open questions

- **Pinned versions.** Proposal: `("2.0.40", "2.1.123")`. Confirm or adjust before step 1.
- **Prompt overlays anchor-miss policy.** `binary_patcher/prompts.py` records misses non-fatally today. The new `prompt_overlays.py` will declare `on_miss="warn"` to match. Re-confirm during migration.
