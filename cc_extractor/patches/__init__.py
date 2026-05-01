from typing import List
import re
import hashlib

class PatchResult:
    def __init__(self, id: str, name: str, group: str, applied: bool, failed: bool = False, skipped: bool = False, details: str = ""):
        self.id = id
        self.name = name
        self.group = group
        self.applied = applied
        self.failed = failed
        self.skipped = skipped
        self.details = details

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "group": self.group,
            "applied": self.applied,
            "failed": self.failed,
            "skipped": self.skipped,
            "details": self.details
        }

def compute_md5(text: str) -> str:
    return hashlib.md5(text.encode('utf-8')).hexdigest()

def escape_regex(text: str) -> str:
    return re.escape(text)

def build_regex_from_pieces(pieces: List[str]) -> str:
    pattern = ""
    for i, piece in enumerate(pieces):
        pattern += re.escape(piece)
        if i < len(pieces) - 1:
            pattern += r'([\s\S]*?)'
    return pattern


from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional, Tuple


@dataclass(frozen=True)
class PatchContext:
    claude_version: Optional[str] = None
    provider_label: str = "cc-extractor"
    config: Mapping[str, Any] = field(default_factory=dict)
    overlays: Mapping[str, str] = field(default_factory=dict)
    force: bool = False


@dataclass(frozen=True)
class PatchOutcome:
    js: str
    status: str  # "applied" | "skipped" | "missed"
    notes: Tuple[str, ...] = ()


@dataclass(frozen=True)
class AggregateResult:
    js: str
    applied: Tuple[str, ...]
    skipped: Tuple[str, ...]
    missed: Tuple[str, ...]
    notes: Tuple[str, ...]


@dataclass(frozen=True)
class Patch:
    id: str
    name: str
    group: str  # "ui" | "thinking" | "prompts" | "tools" | "system"
    versions_supported: str  # SemVer range
    versions_tested: Tuple[str, ...]  # tuple of SemVer ranges, one per matrix bucket
    apply: Callable[[str, "PatchContext"], "PatchOutcome"] = field(repr=False)
    versions_blacklisted: Tuple[str, ...] = ()
    on_miss: str = "fatal"  # "fatal" | "skip" | "warn"


class PatchAnchorMissError(ValueError):
    def __init__(self, patch_id: str, detail: str = ""):
        self.patch_id = patch_id
        self.detail = detail
        super().__init__(f"{patch_id}: anchor not found{(': ' + detail) if detail else ''}")


class PatchUnsupportedVersionError(ValueError):
    def __init__(self, patch_id: str, version: str, supported: str):
        self.patch_id = patch_id
        self.version = version
        self.supported = supported
        super().__init__(f"{patch_id}: version {version} not in supported range {supported!r}")


class PatchBlacklistedError(ValueError):
    def __init__(self, patch_id: str, version: str):
        self.patch_id = patch_id
        self.version = version
        super().__init__(f"{patch_id}: version {version} is blacklisted")
