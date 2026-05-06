"""Platform dispatcher that delegates to ELF, Mach-O, or PE repack."""

from dataclasses import dataclass

from .elf_resize import repack_elf
from .macho_resize import repack_macho
from .pe_resize import repack_pe


@dataclass
class RepackResult:
    buf: bytes
    signature_stripped: bool = False

    @property
    def data(self):
        return self.buf


def repack_binary(data, info, new_raw_bytes, new_offsets_struct):
    """Dispatch binary repack to the correct platform handler."""
    if info.platform == "elf":
        return RepackResult(
            buf=repack_elf(data, info, new_raw_bytes, new_offsets_struct),
            signature_stripped=False,
        )
    if info.platform == "macho":
        return repack_macho(data, info, new_raw_bytes, new_offsets_struct)
    if info.platform == "pe":
        return RepackResult(
            buf=repack_pe(data, info, new_raw_bytes, new_offsets_struct),
            signature_stripped=False,
        )
    raise ValueError(f"repack_binary: unhandled platform {info.platform!r}")
