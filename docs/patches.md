# Patches

Patches rewrite Claude Code's bundled JS to add custom behavior. Each
patch lives in `cc_extractor/patches/<id>.py` and is registered in
`cc_extractor/patches/_registry.py`.

## Authoring a new patch

1. Find the upstream tweakcc patch in `vendor/tweakcc/src/patches/<name>.ts`.
2. Create `cc_extractor/patches/<id>.py` with a `_apply(js, ctx)` function
   and a `PATCH = Patch(...)` constant. Mirror the regex shape from the
   tweakcc TS file. Use `[$\w]+` not `\w+` for identifiers.
3. Add a synthetic snippet for `<id>` to `tests/patches/fixtures/synthetic.py`.
4. Add `tests/patches/test_<id>.py` covering synthetic + real fixtures.
5. Register in `cc_extractor/patches/_registry.py`.
6. Run `pytest -q tests/patches/test_<id>.py` until green.

## Patch metadata fields

| Field | Type | Purpose |
|---|---|---|
| `id` | str | Stable kebab-case identifier |
| `name` | str | Human-readable label |
| `group` | str | One of: ui, thinking, prompts, tools, system |
| `versions_supported` | SemVer range | Versions where the patch is allowed |
| `versions_tested` | tuple of SemVer ranges | Each entry = one test matrix bucket |
| `versions_blacklisted` | tuple of exact versions | Known-broken versions |
| `on_miss` | "fatal" \| "skip" \| "warn" | What happens if anchor not found |
| `apply` | callable | `(js, ctx) -> PatchOutcome` |

## Test tiers

- **L1 (anchor):** regex matches expected pattern. Run via `pytest tests/patches/`.
- **L2 (parse):** patched JS parses cleanly under `node --check`. Same command; skipped if Node missing.
- **L3 (boot smoke):** built variant binary boots and exits cleanly.
  Run with `CC_EXTRACTOR_REAL_BINARY=1 pytest tests/patches_smoke/`.
- **L4 (behavioral):** TUI MCP drives the variant, screen state captured
  and diffed against snapshots.
  Run with `CC_EXTRACTOR_TUI_MCP=1 pytest tests/patches_behavioral/`.

## Updating L4 snapshots

```bash
CC_EXTRACTOR_TUI_MCP=1 CC_EXTRACTOR_UPDATE_SNAPSHOTS=1 \
  pytest tests/patches_behavioral/test_<id>_snapshot.py
```

## Running everything

```bash
CC_EXTRACTOR_REAL_BINARY=1 CC_EXTRACTOR_TUI_MCP=1 \
  .venv/bin/python -m pytest -q
```
