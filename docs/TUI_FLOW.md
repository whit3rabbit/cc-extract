# TUI Flow Reference

This document is the working reference for the TUI user workflow. It separates the flow that exists today from the proposed two-mode flow we want next.

Terminology matters here: an existing named isolated Claude Code setup is a `variant` under `.cc-extractor/variants`. Patch packages are build inputs, not existing setups.

## Current Flow

Today the TUI starts on Dashboard, refreshes workspace state, and exposes variant lifecycle pieces across separate tabs. Existing variants can be checked from the Variants tab and tweaked from the Tweaks tab. Upgrade and uninstall exist in the backend and CLI, but are not wired into the TUI.

```mermaid
flowchart TD
    A["Run app: python -m cc_extractor"] --> B["run_tui()"]
    B --> C["Create TuiState"]
    C --> D["TuiState.refresh()"]

    D --> D1["scan_native_downloads()"]
    D --> D2["scan_npm_downloads()"]
    D --> D3["scan_extractions()"]
    D --> D4["scan_patch_packages()"]
    D --> D5["scan_dashboard_tweak_profiles()"]
    D --> D6["scan_variants()"]
    D --> D7["list_variant_providers()"]
    D --> D8["load_download_index()"]

    D --> E["Initial mode: Dashboard"]

    E --> F["Dashboard wizard"]
    F --> F1["Choose source"]
    F1 --> F2["Choose tweak patches"]
    F2 --> F3["Manage tweak profile"]
    F3 --> F4["Review"]
    F4 --> F5["Run dashboard build"]
    F5 --> F6["apply_patch_packages_to_native()"]

    E --> G["Variants tab"]
    G --> G1{"Existing variants?"}
    G1 -->|Yes| G2["List existing variants"]
    G2 --> G3["Select variant"]
    G3 --> G4["doctor_variant() only"]
    G1 -->|No| G5["List provider presets"]
    G5 --> G6["Provider wizard"]
    G6 --> G7["Name"]
    G7 --> G8["Credentials"]
    G8 --> G9["Models"]
    G9 --> G10["Tweaks"]
    G10 --> G11["Review"]
    G11 --> G12["create_variant()"]

    E --> H["Tweaks tab"]
    H --> H1{"Existing variants?"}
    H1 -->|No| H2["Show: create one first"]
    H1 -->|Yes| H3["Pick variant"]
    H3 --> H4["Toggle curated tweaks"]
    H4 --> H5["Apply changes"]
    H5 --> H6["Persist manifest tweaks"]
    H6 --> H7["apply_variant() rebuild"]

    I["Backend and CLI only"] --> I1["update_variants() via variant update"]
    I --> I2["remove_variant() via variant remove --yes"]
```

## Proposed Flow

The proposed TUI should detect whether any variants already exist and route the user into one of two modes:

- New setup mode: no variants found, say that clearly, then guide the user through provider setup.
- Manage existing setup mode: variants found, show existing setups first and offer upgrade, tweak, uninstall, and health actions.

```mermaid
flowchart TD
    A["Launch TUI"] --> B["Refresh workspace state"]
    B --> C["scan_variants()"]
    C --> D{"Any variants under .cc-extractor/variants?"}

    D -->|No| E["New setup mode"]
    E --> E1["Show: no existing setups found"]
    E1 --> E2["Choose provider profile"]
    E2 --> E3["Provider registry presets"]
    E3 --> E4["zai, deepseek, minimax, ollama, ccrouter, openrouter, vercel, custom, etc."]
    E4 --> E5["Confirm name, credential env, model mapping, tweaks"]
    E5 --> E6["create_variant()"]
    E6 --> E7["Show wrapper path and next run command"]

    D -->|Yes| F["Manage existing setup mode"]
    F --> F1["List variants with provider, source version, wrapper, health summary"]
    F1 --> F2{"Choose action"}

    F2 -->|Upgrade| G["Upgrade selected variant"]
    G --> G1["Choose latest or specific Claude Code version"]
    G1 --> G2["update_variants(name, claude_version=...)"]
    G2 --> G3["Show rebuilt wrapper and patch results"]

    F2 -->|Tweak| H["Tweak selected variant"]
    H --> H1["Load current manifest tweaks"]
    H1 --> H2["Toggle add/remove curated tweaks"]
    H2 --> H3["Persist manifest"]
    H3 --> H4["apply_variant()"]
    H4 --> H5["Show added and removed tweak count"]

    F2 -->|Uninstall| I["Uninstall selected variant"]
    I --> I1["Require explicit confirmation"]
    I1 --> I2["remove_variant(name, yes=True)"]
    I2 --> I3["Remove wrapper and variant directory"]

    F2 -->|Health| J["Health check selected variant"]
    J --> J1["doctor_variant(name)"]
    J1 --> J2["Show wrapper, settings, binary, secrets checks"]
```

## Provider Profiles

The provider registry already includes presets such as `zai`, `deepseek`, `minimax`, `ollama`, `ccrouter`, `openrouter`, `vercel`, `kimi`, `nanogpt`, `poe`, `alibaba`, `cerebras`, `gatewayz`, `mirror`, and `custom`.

Current defaults are provider registry values plus `DEFAULT_TWEAK_IDS`:

- `themes`
- `prompt-overlays`
- `patches-applied-indication`

These are not saved workspace profiles today. Future default profiles should be a UX layer over provider presets unless we intentionally add seeded profile files and migration rules.

## Implementation Notes

- Use `scan_variants()` as the setup detection source of truth.
- Treat `.cc-extractor/variants/<variant-id>/variant.json` as the existing setup record.
- Keep Dashboard patch-package flows separate from named variants.
- Reuse existing backend operations before adding new lifecycle code:
  - `create_variant()` for new setup.
  - `update_variants()` for upgrade.
  - `apply_variant()` for rebuild after tweak changes.
  - `remove_variant()` for uninstall.
  - `doctor_variant()` for health.
- The current TUI already has create, doctor/status, and tweak rebuild pieces. Missing TUI wiring is upgrade/update and uninstall.

## Verification

This file is docs-only. No pytest is required for this step.

Verify the reference exists and contains both Mermaid flows plus the backend lifecycle markers:

```bash
rg -n "flowchart|Current Flow|Proposed Flow|scan_variants|update_variants|remove_variant" docs/TUI_FLOW.md
```
