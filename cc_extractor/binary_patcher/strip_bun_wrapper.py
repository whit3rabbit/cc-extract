"""Strip the Bun IIFE wrapper from entry JS source."""

import re


class BunWrapperNotFound(Exception):
    def __init__(self, anchor):
        self.anchor = anchor
        super().__init__(f"strip-bun-wrapper: {anchor} anchor not found")


WRAPPER_OPEN = re.compile(r"^// @bun[^\n]*\n\(function\([^)]*\) \{")


def strip_bun_wrapper(source):
    match = WRAPPER_OPEN.match(source)
    if match is None:
        if not source.startswith("// @bun"):
            return source
        raise BunWrapperNotFound("open")

    end = len(source)
    while end > 0 and (source[end - 1].isspace() or source[end - 1] == ";"):
        end -= 1
    if end < 2 or source[end - 2 : end] != "})":
        raise BunWrapperNotFound("close")

    return source[match.end() : end - 2]
