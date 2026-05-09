import re
from typing import List, Dict, Any, Optional, Tuple
from . import PatchResult, build_regex_from_pieces

_JS_IDENTIFIER_CHAR = r"A-Za-z0-9_$"


def detect_unicode_escaping(content: str) -> bool:
    return bool(re.search(r'\\u[0-9a-fA-F]{4}', content))

def extract_build_time(content: str) -> Optional[str]:
    match = re.search(r'\bBUILD_TIME:"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)"', content)
    return match.group(1) if match else None

def escape_unescaped_char(s: str, char: str) -> str:
    return escape_js_string_fragment(s, char)

def escape_js_string_fragment(s: str, delimiter: str) -> str:
    result = []
    for c in s:
        if c == "\\":
            result.append("\\\\")
        elif c == delimiter:
            result.append("\\" + delimiter)
        elif c == "\n":
            result.append("\\n")
        elif c == "\r":
            result.append("\\r")
        elif c == "\t":
            result.append("\\t")
        elif c == "\b":
            result.append("\\b")
        elif c == "\f":
            result.append("\\f")
        elif c == "\0":
            result.append("\\u0000")
        elif c == "\u2028":
            result.append("\\u2028")
        elif c == "\u2029":
            result.append("\\u2029")
        elif ord(c) < 0x20:
            result.append(f"\\u{ord(c):04x}")
        else:
            result.append(c)
    return "".join(result)

def escape_js_template_fragment(s: str, preserve_interpolations: Tuple[Tuple[int, int], ...] = ()) -> str:
    result = []
    i = 0
    spans = tuple(sorted(preserve_interpolations))
    span_index = 0
    while i < len(s):
        if span_index < len(spans) and i == spans[span_index][0]:
            _start, end = spans[span_index]
            result.append(s[i:end])
            i = end
            span_index += 1
            continue

        c = s[i]
        if c == "\\":
            result.append("\\\\")
        elif c == "`":
            result.append("\\`")
        elif c == "$" and i + 1 < len(s) and s[i + 1] == "{":
            result.append("\\${")
            i += 1
        elif c == "\r":
            result.append("\\r")
        elif c == "\0":
            result.append("\\u0000")
        elif c == "\u2028":
            result.append("\\u2028")
        elif c == "\u2029":
            result.append("\\u2029")
        elif ord(c) < 0x20 and c != "\n" and c != "\t":
            result.append(f"\\u{ord(c):04x}")
        else:
            result.append(c)
        i += 1
    return "".join(result)


def _validate_pieces(pieces: Any) -> List[str]:
    if not isinstance(pieces, list) or not pieces:
        raise ValueError("pieces must be a non-empty list of strings")
    if not all(isinstance(piece, str) for piece in pieces):
        raise ValueError("pieces must be a non-empty list of strings")
    return pieces


def _replace_prompt_placeholders(text: str, version: str, build_time: Optional[str]) -> str:
    text = text.replace("<<CCVERSION>>", version)
    if build_time:
        text = text.replace("<<BUILD_TIME>>", build_time)
    return text


def _processed_pieces(pieces: Any, version: str, build_time: Optional[str]) -> List[str]:
    return [_replace_prompt_placeholders(piece, version, build_time) for piece in _validate_pieces(pieces)]


def _captured_identifier_map(
    prompt_entry: Dict[str, Any],
    match: re.Match,
) -> Dict[str, str]:
    identifiers = prompt_entry.get("identifiers") or []
    identifier_map = prompt_entry.get("identifierMap") or {}
    if not isinstance(identifiers, (list, tuple)) or not isinstance(identifier_map, dict):
        return {}

    captured_vars = match.groups()
    mapped: Dict[str, str] = {}
    for index, captured_var in enumerate(captured_vars):
        if index >= len(identifiers) or not captured_var:
            continue
        human_name = identifier_map.get(str(identifiers[index]))
        if isinstance(human_name, str) and human_name:
            mapped[human_name] = captured_var
    return mapped


def _replace_identifier_names(text: str, identifier_map: Dict[str, str]) -> str:
    # Map markdown-style names back to the minified variables captured from the bundle.
    for human_name, actual_var in sorted(identifier_map.items(), key=lambda item: len(item[0]), reverse=True):
        pattern = re.compile(
            rf"(?<![{_JS_IDENTIFIER_CHAR}]){re.escape(human_name)}(?![{_JS_IDENTIFIER_CHAR}])"
        )
        text = pattern.sub(lambda _match, actual_var=actual_var: actual_var, text)
    return text


def _is_escaped_at(text: str, index: int) -> bool:
    backslashes = 0
    pos = index - 1
    while pos >= 0 and text[pos] == "\\":
        backslashes += 1
        pos -= 1
    return backslashes % 2 == 1


def _template_interpolation_end(text: str, start: int) -> int:
    depth = 1
    quote = ""
    escaped = False
    pos = start + 2
    while pos < len(text):
        char = text[pos]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
        elif char in ('"', "'", "`"):
            quote = char
            escaped = False
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return pos + 1
        pos += 1
    return -1


def _interpolation_contains_identifier(interpolation: str, identifiers: Tuple[str, ...]) -> bool:
    for identifier in identifiers:
        if not identifier:
            continue
        pattern = rf"(?<![{_JS_IDENTIFIER_CHAR}]){re.escape(identifier)}(?![{_JS_IDENTIFIER_CHAR}])"
        if re.search(pattern, interpolation):
            return True
    return False


def _mapped_template_interpolation_spans(text: str, identifiers: Tuple[str, ...]) -> Tuple[Tuple[int, int], ...]:
    spans = []
    pos = 0
    while pos < len(text):
        start = text.find("${", pos)
        if start == -1:
            break
        if _is_escaped_at(text, start):
            pos = start + 2
            continue
        end = _template_interpolation_end(text, start)
        if end == -1:
            pos = start + 2
            continue
        if _interpolation_contains_identifier(text[start:end], identifiers):
            spans.append((start, end))
        pos = end
    return tuple(spans)


def _interpolate_custom_content(
    custom_content: Any,
    prompt_entry: Dict[str, Any],
    match: re.Match,
    version: str,
    build_time: Optional[str],
) -> Tuple[str, Tuple[str, ...]]:
    replacement = _replace_prompt_placeholders(str(custom_content), version, build_time)
    identifier_map = _captured_identifier_map(prompt_entry, match)
    replacement = _replace_identifier_names(replacement, identifier_map)
    return replacement, tuple(identifier_map.values())


def apply_system_prompts(
    content: str,
    version: str,
    prompts_data: List[Dict[str, Any]],
    patch_filter: Optional[List[str]] = None
) -> Tuple[str, List[PatchResult]]:
    detect_unicode_escaping(content)
    build_time = extract_build_time(content)

    results = []

    for prompt_entry in prompts_data:
        prompt_id = prompt_entry.get('id')
        prompt_name = prompt_entry.get('name', 'Unknown')
        
        if patch_filter and prompt_id not in patch_filter:
            results.append(PatchResult(prompt_id, prompt_name, "System Prompts", False, skipped=True))
            continue

        try:
            processed_pieces = _processed_pieces(prompt_entry.get('pieces', []), version, build_time)
        except ValueError as exc:
            results.append(PatchResult(prompt_id, prompt_name, "System Prompts", False, failed=True, details=str(exc)))
            continue

        regex_pattern = build_regex_from_pieces(processed_pieces)

        # 's' flag in JS dotAll is 're.DOTALL' in Python
        # 'i' flag is 're.IGNORECASE'
        try:
            pattern = re.compile(regex_pattern, re.DOTALL | re.IGNORECASE)
            match = pattern.search(content)
        except re.error as e:
            results.append(PatchResult(prompt_id, prompt_name, "System Prompts", False, failed=True, details=f"Regex error: {str(e)}"))
            continue

        if match:
            custom_content = prompt_entry.get('custom_content')
            if not custom_content:
                # If no custom content, we don't actually change anything, just mark as found
                results.append(PatchResult(prompt_id, prompt_name, "System Prompts", True, details="Found but no custom content provided"))
                continue

            replacement, mapped_identifiers = _interpolate_custom_content(
                custom_content,
                prompt_entry,
                match,
                version,
                build_time,
            )

            # Handle delimiter escaping
            match_index = match.start()
            delimiter = content[match_index - 1] if match_index > 0 else ''
            
            if delimiter in ('"', "'"):
                replacement = escape_js_string_fragment(replacement, delimiter)
            elif delimiter == '`':
                # Preserve mapped JS template expressions while escaping user text.
                preserved = _mapped_template_interpolation_spans(replacement, mapped_identifiers)
                replacement = escape_js_template_fragment(replacement, preserved)

            # Replace in content
            # Use a lambda to avoid backreference issues
            content = content[:match.start()] + replacement + content[match.end():]
            
            results.append(PatchResult(prompt_id, prompt_name, "System Prompts", True))
        else:
            results.append(PatchResult(prompt_id, prompt_name, "System Prompts", False, details="Prompt not found in binary"))

    return content, results
