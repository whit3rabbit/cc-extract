from typing import List, Dict, Any, Optional
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
