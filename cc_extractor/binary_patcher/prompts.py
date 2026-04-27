from dataclasses import dataclass


OVERLAY_MARKERS = {
    "start": "<!-- cc-mirror:provider-overlay start -->",
    "end": "<!-- cc-mirror:provider-overlay end -->",
}

ANCHORS = {
    "webfetch": {
        "tail": "- For GitHub URLs, prefer using the gh CLI via Bash instead (e.g., gh pr view, gh issue view, gh api).",
    },
    "websearch": {
        "tail": 'Example: If the user asks for "latest React docs", search for "React documentation" with the current year, NOT last year',
    },
    "explore": {
        "tail": "Complete the user's search request efficiently and report your findings clearly.",
    },
    "planEnhanced": {
        "tail": "REMEMBER: You can ONLY explore and plan. You CANNOT and MUST NOT write, edit, or modify any files. You do NOT have access to file editing tools.",
    },
    "enterPlan": {
        "tail": "- Users appreciate being consulted before significant changes are made to their codebase",
    },
    "skill": {
        "tail": "tag in the current conversation turn, the skill has ALREADY been loaded - follow the instructions directly instead of calling this tool again",
    },
    "conversationSummary": {
        "tail": "When you are using compact - please focus on test output and code changes. Include file reads verbatim.",
    },
    "webfetchSummary": {
        "tail": "- Never produce or reproduce exact song lyrics.",
    },
}


@dataclass
class PromptResult:
    js: str
    replaced_targets: list
    missing: list


def apply_prompts(js, overlays):
    replaced_targets = []
    missing = []
    overlays = overlays or {}

    for key, overlay_text in overlays.items():
        if overlay_text is None or not str(overlay_text).strip():
            continue

        spec = ANCHORS.get(key)
        if spec is None:
            missing.append(key)
            continue

        tail_index = js.find(spec["tail"])
        if tail_index == -1:
            missing.append(key)
            continue

        tail_end = tail_index + len(spec["tail"])
        delim = _detect_delimiter(js, tail_index)
        stripped_js, insertion_point = _strip_existing_block(js, tail_end, delim)
        js = stripped_js
        block = _build_overlay_block(str(overlay_text), delim)
        if not block:
            continue
        js = js[:insertion_point] + block + js[insertion_point:]
        replaced_targets.append(key)

    return PromptResult(js=js, replaced_targets=replaced_targets, missing=missing)


def _detect_delimiter(js, index):
    start = max(0, index - 8192)
    for pos in range(index - 1, start - 1, -1):
        if js[pos] in ("`", '"', "'"):
            return js[pos]
    return "`"


def _escape_for_delimiter(text, delim):
    if delim == "`":
        return text.replace("`", "\\`").replace("${", "\\${")
    return text.replace("\\", "\\\\").replace(delim, "\\" + delim).replace("\n", "\\n")


def _build_overlay_block(overlay, delim):
    trimmed = overlay.strip()
    if not trimmed:
        return ""
    block = f"\n\n{OVERLAY_MARKERS['start']}\n{trimmed}\n{OVERLAY_MARKERS['end']}\n"
    return _escape_for_delimiter(block, delim)


def _strip_existing_block(js, tail_end, delim):
    escaped_start = _escape_for_delimiter(f"\n\n{OVERLAY_MARKERS['start']}", delim)
    escaped_end = _escape_for_delimiter(f"{OVERLAY_MARKERS['end']}\n", delim)
    if js[tail_end : tail_end + len(escaped_start)] != escaped_start:
        return js, tail_end
    end_index = js.find(escaped_end, tail_end + len(escaped_start))
    if end_index == -1:
        return js, tail_end
    strip_until = end_index + len(escaped_end)
    return js[:tail_end] + js[strip_until:], tail_end
