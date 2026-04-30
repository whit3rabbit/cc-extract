"""Data types for Bun binary parsing results."""

from dataclasses import dataclass
from typing import List, Literal, Optional, Union


ScalarName = Union[int, str]


@dataclass
class BunModule:
    index: int
    name: str
    cont_off: int
    cont_len: int
    smap_off: int
    smap_len: int
    bc_off: int
    bc_len: int
    encoding: ScalarName
    loader: ScalarName
    format: ScalarName
    side: str
    is_entry: bool


@dataclass
class BunBinaryInfo:
    platform: Literal["macho", "elf", "pe"]
    data_start: int
    trailer_offset: int
    byte_count: int
    module_size: int
    modules: List[BunModule]
    entry_point_id: int
    flags: int
    section_offset: Optional[int] = None
    section_size: Optional[int] = None
    has_code_signature: bool = False
    bun_version_hint: str = ""


class BunFormatError(Exception):
    """Raised when a Bun standalone binary cannot be parsed."""


class ModuleNotFound(Exception):
    """Raised when a requested Bun module is not present."""


class SizeMismatch(Exception):
    """Raised when replacement bytes do not match the target module size."""
