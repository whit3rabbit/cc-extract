"""CLI parser builders and per-subcommand handlers for ``cc_extractor``.

The ``main`` entry point and variant dispatcher live in
``cc_extractor.__main__`` so that test fixtures can monkey-patch
variant helpers on that module.
"""

from .handlers import inspect_binary
from .parsers import build_parser

__all__ = ["build_parser", "inspect_binary"]
