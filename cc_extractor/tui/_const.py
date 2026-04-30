"""Constants and small data classes shared across the TUI subpackage.

Kept dependency-free so any TUI submodule can import from it without circular
risk.
"""

from dataclasses import dataclass


TABS = ["Dashboard", "Inspect", "Extract", "Patch", "Variants"]
TAB_MODES = ["dashboard", "inspect", "extract", "patch-source", "variants"]
DASHBOARD_STEPS = ["Source", "Patches", "Profiles", "Review"]
VARIANT_STEPS = ["Provider", "Name", "Credentials", "Models", "Tweaks", "Review"]
VARIANT_MODEL_FIELDS = [
    ("opus", "Opus"),
    ("sonnet", "Sonnet"),
    ("haiku", "Haiku"),
    ("default", "Default"),
    ("small_fast", "Small-fast"),
    ("subagent", "Subagent"),
]
SOURCE_LATEST = "latest"
SOURCE_VERSION = "version"
SOURCE_ARTIFACT = "artifact"

DEFAULT_THEME_ID = "hacker-bbs"
THEME_ORDER = [DEFAULT_THEME_ID, "unicorn", "dark", "light"]


@dataclass
class MenuOption:
    kind: str
    label: str
    value: object = None
