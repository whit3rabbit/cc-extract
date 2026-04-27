"""Shared constants for Bun standalone binary parsing."""

TRAILER = b"\n---- Bun! ----\n"
OFFSETS_SIZE = 32

# Mach-O and ELF prefix their Bun section payload with an 8-byte u64 size.
MACHO_SECTION_HEADER_SIZE = 8

MODULE_SIZE_V36 = 36
MODULE_SIZE_V52 = 52
MODULE_SIZES = (MODULE_SIZE_V52, MODULE_SIZE_V36)
FLAG_OFFSETS_BY_SIZE = {
    MODULE_SIZE_V36: 32,
    MODULE_SIZE_V52: 48,
}

TRAILER_SEARCH_WINDOW = 4 * 1024 * 1024
MACHO_HEADER_SCAN_BYTES = 8192

MACHO_MAGIC_64 = 0xFEEDFACF
MACHO_MAGIC_64_BE = 0xCFFAEDFE
MACHO_MAGIC_FAT = 0xCAFEBABE
MACHO_MAGIC_FAT_LE = 0xBEBAFECA

ELF_MAGIC_BYTES = b"\x7fELF"

PE_DOS_MAGIC = 0x5A4D
PE_NT_SIGNATURE = 0x00004550

ENCODING_NAMES = {
    0: "binary",
    1: "latin1",
    2: "utf8",
}

FORMAT_NAMES = {
    0: "none",
    1: "esm",
    2: "cjs",
}

LOADER_NAMES = {
    0: "file",
    1: "js",
    9: "wasm",
    10: "napi",
}

BUNFS_PATH_PREFIXES = ["/$bunfs/root/", "$bunfs/root/"]
