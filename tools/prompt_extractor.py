#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

try:
    from tree_sitter import Language, Parser
    import tree_sitter_javascript
except ImportError:  # pragma: no cover - exercised only without dev deps.
    Language = None
    Parser = None
    tree_sitter_javascript = None


Prompt = Dict[str, Any]
IdentifierRange = Tuple[str, int, int]

_IDENTIFIER_RE = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")
_JS_KEYWORDS = {
    "as",
    "async",
    "await",
    "break",
    "case",
    "catch",
    "class",
    "const",
    "continue",
    "debugger",
    "default",
    "delete",
    "do",
    "else",
    "export",
    "extends",
    "false",
    "finally",
    "for",
    "from",
    "function",
    "if",
    "import",
    "in",
    "instanceof",
    "let",
    "new",
    "null",
    "of",
    "return",
    "static",
    "super",
    "switch",
    "this",
    "throw",
    "true",
    "try",
    "typeof",
    "undefined",
    "var",
    "void",
    "while",
    "with",
    "yield",
}
_REGEX_PREFIX_CHARS = set("([{=,:;!&|?+-*~^<>")
_REGEX_PREFIX_WORDS = {
    "await",
    "case",
    "delete",
    "do",
    "else",
    "in",
    "instanceof",
    "new",
    "return",
    "throw",
    "typeof",
    "void",
    "yield",
}


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return re.sub(r"^-+|-+$", "", text)


def validate_input(text: str, min_length: int = 500) -> bool:
    if not text or not isinstance(text, str):
        return False

    if text.startswith("This is the git status"):
        return True
    if "Whenever you read a file, you should consider whether it" in text:
        return True
    if "IMPORTANT: Assist with authorized security testing" in text:
        return True

    if '.dim("Note:' in text:
        return False
    if text.startswith("Add an MCP server to Claude Code."):
        return False
    if "Cannot install keybindings from a remote" in text:
        return False

    if len(text) < min_length:
        return False

    first_10 = text[:10]
    if first_10.startswith("AGFzbQ") or re.match(r"^[A-Z0-9+/=]{10}$", first_10):
        return False

    sample = text[:500]
    words = [word for word in sample.split() if word]
    if not words:
        return False

    uppercase_words = [word for word in words if word == word.upper() and re.search(r"[A-Z]", word)]
    if len(uppercase_words) / len(words) > 0.6:
        return False

    lower_text = text.lower()
    has_you = "you" in lower_text
    has_ai = "ai" in lower_text or "assistant" in lower_text
    has_instruction = any(word in lower_text for word in ("must", "should", "always"))

    if not has_you and not has_ai and not has_instruction:
        return False

    if not re.search(r"[.!?]\s+[A-Z\(]", text):
        return False

    avg_word_length = sum(len(word) for word in words) / len(words)
    if avg_word_length > 15:
        return False

    if len(re.findall(r"\s", sample)) / len(sample) < 0.1:
        return False

    return True


def replace_version_in_string(value: str, version: Optional[str]) -> str:
    if not version:
        return value
    return re.sub(re.escape(version), "<<CCVERSION>>", value)


def replace_build_time_in_string(value: str) -> str:
    return re.sub(
        r'BUILD_TIME:"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)"',
        'BUILD_TIME:"<<BUILD_TIME>>"',
        value,
    )


def _apply_placeholders(value: str, version: Optional[str]) -> str:
    return replace_version_in_string(replace_build_time_in_string(value), version)


def _is_escaped(text: str, index: int) -> bool:
    slash_count = 0
    cursor = index - 1
    while cursor >= 0 and text[cursor] == "\\":
        slash_count += 1
        cursor -= 1
    return slash_count % 2 == 1


def _skip_quoted(text: str, start: int) -> int:
    quote = text[start]
    cursor = start + 1
    while cursor < len(text):
        char = text[cursor]
        if char == "\\":
            cursor += 2
            continue
        if char == quote:
            return cursor + 1
        cursor += 1
    return len(text)


def _decode_js_string(raw: str) -> str:
    result: List[str] = []
    cursor = 0

    while cursor < len(raw):
        char = raw[cursor]
        if char != "\\":
            result.append(char)
            cursor += 1
            continue

        cursor += 1
        if cursor >= len(raw):
            result.append("\\")
            break

        escaped = raw[cursor]
        cursor += 1

        if escaped in ("'", '"', "\\"):
            result.append(escaped)
        elif escaped == "n":
            result.append("\n")
        elif escaped == "r":
            result.append("\r")
        elif escaped == "t":
            result.append("\t")
        elif escaped == "b":
            result.append("\b")
        elif escaped == "f":
            result.append("\f")
        elif escaped == "v":
            result.append("\v")
        elif escaped == "0":
            result.append("\0")
        elif escaped == "\n":
            continue
        elif escaped == "\r":
            if cursor < len(raw) and raw[cursor] == "\n":
                cursor += 1
        elif escaped == "x" and cursor + 2 <= len(raw):
            result.append(chr(int(raw[cursor : cursor + 2], 16)))
            cursor += 2
        elif escaped == "u" and cursor < len(raw) and raw[cursor] == "{":
            end = raw.find("}", cursor + 1)
            if end == -1:
                result.append("\\u{")
            else:
                result.append(chr(int(raw[cursor + 1 : end], 16)))
                cursor = end + 1
        elif escaped == "u" and cursor + 4 <= len(raw):
            code_point = int(raw[cursor : cursor + 4], 16)
            cursor += 4
            if (
                0xD800 <= code_point <= 0xDBFF
                and cursor + 6 <= len(raw)
                and raw[cursor : cursor + 2] == "\\u"
            ):
                low_surrogate = int(raw[cursor + 2 : cursor + 6], 16)
                if 0xDC00 <= low_surrogate <= 0xDFFF:
                    code_point = 0x10000 + ((code_point - 0xD800) << 10)
                    code_point += low_surrogate - 0xDC00
                    cursor += 6
            result.append(chr(code_point))
        else:
            result.append(escaped)

    return "".join(result)


def _read_quoted_literal(code: str, start: int) -> Tuple[str, int]:
    end = _skip_quoted(code, start)
    closing = max(start + 1, end - 1)
    return _decode_js_string(code[start + 1 : closing]), end


def _skip_line_comment(text: str, start: int) -> int:
    newline = text.find("\n", start + 2)
    return len(text) if newline == -1 else newline + 1


def _skip_block_comment(text: str, start: int) -> int:
    end = text.find("*/", start + 2)
    return len(text) if end == -1 else end + 2


def _previous_token(text: str, index: int) -> str:
    cursor = index - 1
    while cursor >= 0 and text[cursor].isspace():
        cursor -= 1
    if cursor < 0:
        return ""
    if re.match(r"[A-Za-z0-9_$]", text[cursor]):
        end = cursor + 1
        while cursor >= 0 and re.match(r"[A-Za-z0-9_$]", text[cursor]):
            cursor -= 1
        return text[cursor + 1 : end]
    return text[cursor]


def _can_start_regex(text: str, index: int) -> bool:
    previous = _previous_token(text, index)
    return not previous or previous in _REGEX_PREFIX_CHARS or previous in _REGEX_PREFIX_WORDS


def _skip_regex_literal(text: str, start: int) -> int:
    cursor = start + 1
    in_class = False

    while cursor < len(text):
        char = text[cursor]
        if char == "\\":
            cursor += 2
            continue
        if char == "[":
            in_class = True
        elif char == "]":
            in_class = False
        elif char == "/" and not in_class:
            cursor += 1
            while cursor < len(text) and re.match(r"[A-Za-z]", text[cursor]):
                cursor += 1
            return cursor
        elif char in "\r\n":
            return start + 1
        cursor += 1

    return start + 1


def _skip_template_expression(text: str, open_brace: int) -> int:
    depth = 1
    cursor = open_brace + 1

    while cursor < len(text):
        if text.startswith("//", cursor):
            cursor = _skip_line_comment(text, cursor)
            continue
        if text.startswith("/*", cursor):
            cursor = _skip_block_comment(text, cursor)
            continue
        if text[cursor] == "/" and _can_start_regex(text, cursor):
            next_cursor = _skip_regex_literal(text, cursor)
            if next_cursor > cursor + 1:
                cursor = next_cursor
                continue

        char = text[cursor]
        if char in ("'", '"'):
            cursor = _skip_quoted(text, cursor)
            continue
        if char == "`":
            cursor = _skip_template_literal(text, cursor)
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return cursor + 1
        cursor += 1

    return len(text)


def _skip_template_literal(text: str, start: int) -> int:
    cursor = start + 1

    while cursor < len(text):
        if text[cursor] == "\\":
            cursor += 2
            continue
        if text.startswith("${", cursor) and not _is_escaped(text, cursor):
            cursor = _skip_template_expression(text, cursor + 1)
            continue
        if text[cursor] == "`":
            return cursor + 1
        cursor += 1

    return len(text)


def _read_template_literal(code: str, start: int) -> Tuple[str, int]:
    end = _skip_template_literal(code, start)
    closing = max(start + 1, end - 1)
    return code[start + 1 : closing], end


def _matching_template_brace(content: str, open_brace: int) -> int:
    return _skip_template_expression(content, open_brace) - 1


def _previous_significant(text: str, index: int) -> str:
    cursor = index - 1
    while cursor >= 0 and text[cursor].isspace():
        cursor -= 1
    return text[cursor] if cursor >= 0 else ""


def _next_significant(text: str, index: int) -> str:
    cursor = index
    while cursor < len(text) and text[cursor].isspace():
        cursor += 1
    return text[cursor] if cursor < len(text) else ""


def _identifier_tokens(expression: str, base: int) -> Iterable[Tuple[str, int, int]]:
    cursor = 0

    while cursor < len(expression):
        if expression.startswith("//", cursor):
            cursor = _skip_line_comment(expression, cursor)
            continue
        if expression.startswith("/*", cursor):
            cursor = _skip_block_comment(expression, cursor)
            continue
        if expression[cursor] == "/" and _can_start_regex(expression, cursor):
            next_cursor = _skip_regex_literal(expression, cursor)
            if next_cursor > cursor + 1:
                cursor = next_cursor
                continue

        char = expression[cursor]
        if char in ("'", '"'):
            cursor = _skip_quoted(expression, cursor)
            continue
        if char == "`":
            cursor = _skip_template_literal(expression, cursor)
            continue

        match = _IDENTIFIER_RE.match(expression, cursor)
        if not match:
            cursor += 1
            continue

        name = match.group(0)
        if name not in _JS_KEYWORDS:
            previous_char = _previous_significant(expression, match.start())
            next_char = _next_significant(expression, match.end())
            if previous_char != "." and next_char != ":":
                yield name, base + match.start(), base + match.end()

        cursor = match.end()


def _template_identifiers(content: str) -> List[Tuple[str, int, int]]:
    identifiers: List[Tuple[str, int, int]] = []
    cursor = 0

    while cursor < len(content):
        if content.startswith("${", cursor) and not _is_escaped(content, cursor):
            expr_start = cursor + 2
            expr_end = _matching_template_brace(content, cursor + 1)
            if expr_end < expr_start:
                break
            identifiers.extend(_identifier_tokens(content[expr_start:expr_end], expr_start))
            cursor = expr_end + 1
            continue
        cursor += 1

    return sorted(identifiers, key=lambda item: item[1])


def _label_encoded_prompt(
    pieces: List[str],
    identifier_names: List[str],
    start: int,
    end: int,
) -> Prompt:
    unique_names: List[str] = []
    for name in identifier_names:
        if name not in unique_names:
            unique_names.append(name)

    label_for_name = {name: index for index, name in enumerate(unique_names)}

    return {
        "name": "",
        "id": "",
        "description": "",
        "pieces": pieces,
        "identifiers": [label_for_name[name] for name in identifier_names],
        "identifierMap": {str(index): "" for index in range(len(unique_names))},
        "start": start,
        "end": end,
    }


def _build_template_prompt(
    content: str,
    start: int,
    end: int,
    version: Optional[str],
) -> Prompt:
    identifiers = _template_identifiers(content)
    pieces: List[str] = []
    identifier_names: List[str] = []
    cursor = 0

    for name, ident_start, ident_end in identifiers:
        pieces.append(_apply_placeholders(content[cursor:ident_start], version))
        identifier_names.append(name)
        cursor = ident_end

    pieces.append(_apply_placeholders(content[cursor:], version))

    return _label_encoded_prompt(pieces, identifier_names, start, end)


def _build_tree_template_prompt(
    content_bytes: bytes,
    identifiers: Sequence[IdentifierRange],
    start: int,
    end: int,
    version: Optional[str],
) -> Prompt:
    pieces: List[str] = []
    identifier_names: List[str] = []
    cursor = 0

    for name, ident_start, ident_end in identifiers:
        piece = content_bytes[cursor:ident_start].decode("utf-8")
        pieces.append(_apply_placeholders(piece, version))
        identifier_names.append(name)
        cursor = ident_end

    pieces.append(_apply_placeholders(content_bytes[cursor:].decode("utf-8"), version))
    return _label_encoded_prompt(pieces, identifier_names, start, end)


class _ScannerPromptExtractor:
    def extract_strings(
        self,
        filepath: str,
        min_length: int = 500,
        version: Optional[str] = None,
        include_all: bool = False,
    ) -> List[Prompt]:
        code = Path(filepath).read_text(encoding="utf-8")
        prompts: List[Prompt] = []
        cursor = 0

        while cursor < len(code):
            if code.startswith("//", cursor):
                cursor = _skip_line_comment(code, cursor)
                continue
            if code.startswith("/*", cursor):
                cursor = _skip_block_comment(code, cursor)
                continue
            if code[cursor] == "/" and _can_start_regex(code, cursor):
                next_cursor = _skip_regex_literal(code, cursor)
                if next_cursor > cursor + 1:
                    cursor = next_cursor
                    continue

            char = code[cursor]
            if char in ("'", '"'):
                value, end = _read_quoted_literal(code, cursor)
                if include_all or validate_input(value, min_length):
                    prompts.append(
                        {
                            "name": "",
                            "id": "",
                            "description": "",
                            "pieces": [_apply_placeholders(value, version)],
                            "identifiers": [],
                            "identifierMap": {},
                            "start": cursor,
                            "end": end,
                        }
                    )
                cursor = end
                continue

            if char == "`":
                content, end = _read_template_literal(code, cursor)
                if include_all or validate_input(content, min_length):
                    prompts.append(_build_template_prompt(content, cursor, end, version))
                cursor = end
                continue

            cursor += 1

        return _filter_nested_prompts(prompts)


class PromptExtractor:
    def __init__(self) -> None:
        self.parser = None
        if Parser is not None and Language is not None and tree_sitter_javascript is not None:
            self.parser = Parser(Language(tree_sitter_javascript.language()))

    def extract_strings(
        self,
        filepath: str,
        min_length: int = 500,
        version: Optional[str] = None,
        include_all: bool = False,
    ) -> List[Prompt]:
        if self.parser is None:
            return _ScannerPromptExtractor().extract_strings(
                filepath,
                min_length,
                version,
                include_all=include_all,
            )

        code_bytes = Path(filepath).read_bytes()
        tree = self.parser.parse(code_bytes)
        prompts: List[Prompt] = []

        def text(node: Any) -> str:
            return code_bytes[node.start_byte : node.end_byte].decode("utf-8")

        def expression_identifiers(
            node: Any,
            content_start: int,
            is_top_level: bool = True,
        ) -> List[IdentifierRange]:
            if node.type in ("identifier", "property_identifier") and is_top_level:
                return [
                    (
                        text(node),
                        node.start_byte - content_start,
                        node.end_byte - content_start,
                    )
                ]

            if node.type == "call_expression":
                identifiers: List[IdentifierRange] = []
                for child in node.named_children:
                    identifiers.extend(expression_identifiers(child, content_start, True))
                return identifiers

            if node.type == "member_expression":
                if any(child.type == "optional_chain" for child in node.children):
                    identifiers: List[IdentifierRange] = []
                    for child in node.named_children:
                        identifiers.extend(expression_identifiers(child, content_start, True))
                    return identifiers

                target = node.child_by_field_name("object")
                if target is None and node.named_children:
                    target = node.named_children[0]
                if target is None:
                    return []
                return expression_identifiers(target, content_start, True)

            if node.type == "subscript_expression":
                target = node.child_by_field_name("object")
                if target is None and node.named_children:
                    target = node.named_children[0]
                if target is None:
                    return []
                return expression_identifiers(target, content_start, True)

            if node.type == "template_string":
                identifiers: List[IdentifierRange] = []
                for child in node.named_children:
                    if child.type == "template_substitution":
                        identifiers.extend(substitution_identifiers(child, content_start))
                return identifiers

            if node.type == "object":
                return []

            identifiers = []
            for child in node.named_children:
                identifiers.extend(expression_identifiers(child, content_start, True))
            return identifiers

        def substitution_identifiers(node: Any, content_start: int) -> List[IdentifierRange]:
            identifiers: List[IdentifierRange] = []
            for child in node.named_children:
                identifiers.extend(expression_identifiers(child, content_start, True))
            return identifiers

        def traverse(node: Any) -> None:
            if node.type == "string":
                raw = code_bytes[node.start_byte + 1 : node.end_byte - 1].decode("utf-8")
                value = _decode_js_string(raw)
                if include_all or validate_input(value, min_length):
                    prompts.append(
                        {
                            "name": "",
                            "id": "",
                            "description": "",
                            "pieces": [_apply_placeholders(value, version)],
                            "identifiers": [],
                            "identifierMap": {},
                            "start": node.start_byte,
                            "end": node.end_byte,
                        }
                    )

            elif node.type == "template_string":
                content_start = node.start_byte + 1
                content_end = node.end_byte - 1
                content_bytes = code_bytes[content_start:content_end]
                content = content_bytes.decode("utf-8")

                if include_all or validate_input(content, min_length):
                    identifiers: List[IdentifierRange] = []
                    for child in node.named_children:
                        if child.type == "template_substitution":
                            identifiers.extend(substitution_identifiers(child, content_start))
                    identifiers.sort(key=lambda item: item[1])
                    prompts.append(
                        _build_tree_template_prompt(
                            content_bytes,
                            identifiers,
                            node.start_byte,
                            node.end_byte,
                            version,
                        )
                    )

            for child in node.children:
                traverse(child)

        traverse(tree.root_node)
        return _filter_nested_prompts(prompts)


def _filter_nested_prompts(prompts: List[Prompt]) -> List[Prompt]:
    prompts.sort(key=lambda item: (item["start"], -item["end"]))
    seen_ranges: List[Tuple[int, int]] = []
    filtered: List[Prompt] = []

    for prompt in prompts:
        start = prompt["start"]
        end = prompt["end"]
        if any(start >= seen_start and end <= seen_end for seen_start, seen_end in seen_ranges):
            continue
        filtered.append(prompt)
        seen_ranges.append((start, end))

    return filtered


def _joined(prompt: Prompt) -> str:
    return "".join(prompt.get("pieces", []))


def _find_pieces_in_source(
    pieces: Sequence[str],
    source_text: str,
    max_gap: int = 2000,
) -> Optional[Tuple[int, int]]:
    anchors = [piece for piece in pieces if piece]
    if not anchors:
        return None
    if len("".join(anchors)) < 20 or max(len(anchor.strip()) for anchor in anchors) < 8:
        return None

    if len(anchors) == 1:
        start = source_text.find(anchors[0])
        return None if start == -1 else (start, start + len(anchors[0]))

    pivot_index = max(range(len(anchors)), key=lambda index: len(anchors[index]))
    pivot_anchor = anchors[pivot_index]
    search_from = 0
    attempts = 0
    while True:
        pivot_start = source_text.find(pivot_anchor, search_from)
        if pivot_start == -1:
            return None
        attempts += 1
        if attempts > 5000:
            return None

        positions = [0] * len(anchors)
        positions[pivot_index] = pivot_start
        matched = True

        current_start = pivot_start
        for index in range(pivot_index - 1, -1, -1):
            anchor = anchors[index]
            window_start = max(0, current_start - max_gap - len(anchor))
            anchor_start = source_text.rfind(anchor, window_start, current_start)
            if (
                anchor_start == -1
                or current_start - (anchor_start + len(anchor)) > max_gap
            ):
                matched = False
                break
            positions[index] = anchor_start
            current_start = anchor_start

        current_end = pivot_start + len(pivot_anchor)
        if matched:
            for index in range(pivot_index + 1, len(anchors)):
                anchor = anchors[index]
                window_end = min(len(source_text), current_end + max_gap + len(anchor))
                anchor_start = source_text.find(anchor, current_end, window_end)
                if (
                    anchor_start == -1
                    or anchor_start - current_end > max_gap
                ):
                    matched = False
                    break
                positions[index] = anchor_start
                current_end = anchor_start + len(anchor)

        if matched:
            return positions[0], positions[-1] + len(anchors[-1])

        search_from = pivot_start + 1


def _recover_existing_prompts(
    existing_prompts: Sequence[Prompt],
    source_text: str,
    already_prompts: Sequence[Prompt],
    current_version: Optional[str],
) -> List[Prompt]:
    already_keys = {
        (_joined(prompt), tuple(prompt.get("identifiers", [])))
        for prompt in already_prompts
    }
    recovered: List[Prompt] = []

    for existing in existing_prompts:
        existing_key = (_joined(existing), tuple(existing.get("identifiers", [])))
        if existing_key in already_keys:
            continue

        start = None
        end = None
        content = _joined(existing)
        if content:
            offset = source_text.find(content)
            if offset != -1:
                start = offset
                end = offset + len(content)

        if start is None:
            match_range = _find_pieces_in_source(existing.get("pieces", []), source_text)
            if match_range:
                start, end = match_range

        if start is None or end is None:
            continue

        item = dict(existing)
        item["start"] = start
        item["end"] = end
        item["version"] = item.get("version") or current_version
        recovered.append(item)
        already_keys.add(existing_key)

    return recovered


def merge_with_existing(
    new_prompts: Sequence[Prompt],
    old_prompts: Sequence[Prompt],
    current_version: Optional[str],
) -> List[Prompt]:
    merged: List[Prompt] = []

    if not old_prompts:
        for prompt in new_prompts:
            item = dict(prompt)
            item["version"] = current_version
            merged.append(item)
        return merged

    for new_prompt in new_prompts:
        item = dict(new_prompt)
        match = None

        for old_prompt in old_prompts:
            if (
                _joined(item) == _joined(old_prompt)
                and item.get("identifiers") == old_prompt.get("identifiers")
            ):
                match = old_prompt
                break

        if match:
            item["name"] = match.get("name", "")
            item["id"] = match.get("id", "") or slugify(item["name"])
            item["description"] = match.get("description", "")
            item["identifierMap"] = match.get("identifierMap", {})
            item["version"] = match.get("version") or current_version
        else:
            similar = next(
                (
                    old_prompt
                    for old_prompt in old_prompts
                    if old_prompt.get("name") and old_prompt.get("name") == item.get("name")
                ),
                None,
            )
            item["id"] = (similar or {}).get("id", "") or slugify(item.get("name", ""))
            item["version"] = current_version

        merged.append(item)

    return merged


def _load_existing(path: Optional[Path]) -> List[Prompt]:
    if not path or not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("prompts", [])


def _version_from_package_json(input_path: Path) -> Optional[str]:
    package_json = input_path.resolve().parent / "package.json"
    if not package_json.exists():
        return None
    try:
        data = json.loads(package_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data.get("version")


def extract_prompts(
    input_path: str,
    min_length: int = 500,
    version: Optional[str] = None,
    existing_prompts: Optional[Sequence[Prompt]] = None,
) -> Dict[str, Any]:
    extractor = PromptExtractor()
    extracted = extractor.extract_strings(
        input_path,
        min_length=min_length,
        version=version,
    )
    merged = merge_with_existing(extracted, existing_prompts or [], version)

    if existing_prompts:
        source_text = Path(input_path).read_text(encoding="utf-8")
        merged.extend(
            _recover_existing_prompts(
                existing_prompts,
                source_text,
                merged,
                version,
            )
        )

    merged.sort(key=_joined)

    for prompt in merged:
        prompt.pop("start", None)
        prompt.pop("end", None)

    return {"version": version, "prompts": merged}


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Extract tweakcc-style prompt JSON from a Claude Code JS file"
    )
    parser.add_argument("input", help="Input JS file")
    parser.add_argument("--output", "-o", default="prompts.json", help="Output JSON file")
    parser.add_argument("--min-length", type=int, default=500, help="Minimum string length")
    parser.add_argument("--existing", "-e", help="Existing prompts JSON file for metadata merging")
    parser.add_argument("--version-hint", help="Claude Code version, for example 2.1.113")
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    output_path = Path(args.output)
    existing_path = Path(args.existing) if args.existing else output_path
    version = args.version_hint or _version_from_package_json(input_path)

    output_data = extract_prompts(
        str(input_path),
        min_length=args.min_length,
        version=version,
        existing_prompts=_load_existing(existing_path),
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(output_data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"Extracted {len(output_data['prompts'])} prompts to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
