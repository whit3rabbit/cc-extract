"""Same-size or grow entry JS replacement with pointer relocation."""

import struct
from dataclasses import dataclass

from cc_extractor.bun_extract.constants import OFFSETS_SIZE
from cc_extractor.bun_extract.types import BunFormatError

from .repack import repack_binary


@dataclass
class ReplaceEntryResult:
    buf: bytes
    signature_invalidated: bool
    signature_stripped: bool
    delta: int

    @property
    def data(self):
        return self.buf


def replace_entry_js(data, info, new_content):
    """Replace entry JS with pointer relocation and platform-specific repack."""
    if info.entry_point_id < 0 or info.entry_point_id >= len(info.modules):
        raise BunFormatError(
            f"Entry module id {info.entry_point_id} out of range (have {len(info.modules)} modules)"
        )

    new_content = bytes(new_content)
    entry = info.modules[info.entry_point_id]
    old_entry_len = entry.cont_len
    delta = len(new_content) - old_entry_len
    cut = entry.cont_off + old_entry_len

    offsets_start = info.trailer_offset - OFFSETS_SIZE
    old_modules_off = struct.unpack_from("<I", data, offsets_start + 8)[0]
    old_modules_len = struct.unpack_from("<I", data, offsets_start + 12)[0]

    old_raw_bytes = data[info.data_start : info.data_start + info.byte_count]
    new_raw_bytes = bytearray(
        old_raw_bytes[: entry.cont_off]
        + new_content
        + old_raw_bytes[entry.cont_off + old_entry_len :]
    )

    new_modules_off = old_modules_off + delta if old_modules_off >= cut else old_modules_off
    for index in range(len(info.modules)):
        base = new_modules_off + index * info.module_size
        for slot in (0, 8, 16, 24):
            ptr_off = struct.unpack_from("<I", new_raw_bytes, base + slot)[0]
            ptr_len = struct.unpack_from("<I", new_raw_bytes, base + slot + 4)[0]
            if ptr_len != 0 and ptr_off >= cut:
                struct.pack_into("<I", new_raw_bytes, base + slot, ptr_off + delta)
        if index == info.entry_point_id:
            struct.pack_into("<I", new_raw_bytes, base + 12, len(new_content))

    new_offsets = bytearray(OFFSETS_SIZE)
    struct.pack_into("<Q", new_offsets, 0, len(new_raw_bytes))
    struct.pack_into("<I", new_offsets, 8, new_modules_off)
    struct.pack_into("<I", new_offsets, 12, old_modules_len)
    struct.pack_into("<I", new_offsets, 16, info.entry_point_id)
    new_offsets[20:28] = data[offsets_start + 20 : offsets_start + 28]
    struct.pack_into("<I", new_offsets, 28, info.flags)

    repacked = repack_binary(data, info, bytes(new_raw_bytes), bytes(new_offsets))
    return ReplaceEntryResult(
        buf=repacked.buf,
        signature_invalidated=info.platform == "macho" and info.has_code_signature,
        signature_stripped=repacked.signature_stripped,
        delta=delta,
    )
