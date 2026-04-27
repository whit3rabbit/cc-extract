from .constants import ELF_MAGIC_BYTES, OFFSETS_SIZE


def is_elf(data):
    return len(data) >= len(ELF_MAGIC_BYTES) and data[: len(ELF_MAGIC_BYTES)] == ELF_MAGIC_BYTES


def elf_data_start(trailer_offset, byte_count):
    # byteCount excludes the Offsets struct and trailer, so subtract OFFSETS_SIZE.
    return trailer_offset - byte_count - OFFSETS_SIZE
