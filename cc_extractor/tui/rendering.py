"""Frame, widget, footer, and text rendering helpers.

These functions are pure: they read the state and return strings or widget
objects. They do not mutate state and do not call externally-monkey-patched
functions.
"""

from typing import Optional

from ..workspace import workspace_root
from ._const import DASHBOARD_STEPS, TABS, TAB_MODES, VARIANT_STEPS
from .options import (
    dashboard_options,
    dashboard_steps,
    dashboard_summary,
    dashboard_title,
    format_native_artifact,
    selected_dashboard_packages,
    selected_tweaks_edit_patch,
    tweaks_edit_groups,
    tweaks_edit_options,
    tweaks_source_options,
    variant_options,
    variant_steps,
    variant_summary,
    variant_title,
)
from .themes import active_theme, normalize_theme_id, theme_name


# -- Tab + status bar ---------------------------------------------------------

def active_tab(state):
    if state.mode == "patch-package":
        return "Patch"
    if state.mode == "tweaks-edit":
        return "Tweaks"
    for tab, mode in zip(TABS, TAB_MODES):
        if state.mode == mode:
            return tab
    return "Dashboard"


def active_tab_index(state):
    return TABS.index(active_tab(state))


def tab_bar(state):
    active = active_tab(state)
    parts = []
    for tab in TABS:
        if tab == active:
            parts.append(f"[{tab}]")
        else:
            parts.append(f" {tab} ")
    return "  ".join(parts)


# -- Body labels and progress -------------------------------------------------

def current_labels(state):
    if state.mode == "dashboard":
        return dashboard_title(state), [option.label for option in dashboard_options(state)]
    if state.mode == "inspect":
        return "Inspect", [format_native_artifact(artifact) for artifact in state.native_artifacts]
    if state.mode == "extract":
        return "Extract", [format_native_artifact(artifact) for artifact in state.native_artifacts]
    if state.mode == "patch-source":
        return "Patch source", [format_native_artifact(artifact) for artifact in state.native_artifacts]
    if state.mode == "patch-package":
        labels = []
        for index, package in enumerate(state.patch_packages):
            marker = "[x]" if index in state.selected_patch_indexes else "[ ]"
            labels.append(f"{marker} {package.patch_id}@{package.version}  {package.name}")
        return "Patch packages", labels
    if state.mode == "variants":
        return variant_title(state), [option.label for option in variant_options(state)]
    if state.mode == "tweaks-source":
        return "Tweaks: pick variant", [option.label for option in tweaks_source_options(state)]
    if state.mode == "tweaks-edit":
        labels = _tweaks_edit_labels(state)
        title = f"Patches  ({state.tweaks_variant_id or 'no variant'})"
        return title, labels
    return "Status", []


def _tweaks_edit_labels(state):
    """Build the left-pane label list for tweaks-edit mode.

    Walks `tweaks_edit_options(state)` (one entry per togglable patch) and
    inserts a non-selectable group header (rendered with leading "-- ") above
    the first patch in each group. Group headers are visual-only and do not
    affect `selected_index`.
    """
    options = tweaks_edit_options(state)
    by_id = {opt.value: opt.label for opt in options}
    labels = []
    for group, patch_ids in tweaks_edit_groups(state):
        labels.append(f"-- {group} --")
        for patch_id in patch_ids:
            label = by_id.get(patch_id)
            if label is not None:
                labels.append(label)
    return labels


def tweaks_detail_text(state) -> str:
    """Right-pane content describing the currently selected patch."""
    patch = selected_tweaks_edit_patch(state)
    if patch is None:
        return "No patch selected."
    applied = "yes" if patch.id in (state.tweaks_baseline or ()) else "no"
    pending = "yes" if patch.id in (state.tweaks_pending or ()) else "no"
    blacklist = ", ".join(patch.versions_blacklisted) if patch.versions_blacklisted else "(none)"
    tested = ", ".join(patch.versions_tested) if patch.versions_tested else "(none)"
    description = patch.description or "(no description)"
    return "\n".join([
        patch.name,
        f"Group: {patch.group}",
        "",
        description,
        "",
        f"Versions supported: {patch.versions_supported}",
        f"Tested ranges: {tested}",
        f"Blacklisted: {blacklist}",
        f"On miss: {patch.on_miss}",
        "",
        f"Applied to {state.tweaks_variant_id or '(no variant)'}: {applied}",
        f"Pending: {pending}",
    ])


def empty_text(state):
    if state.mode in {"inspect", "extract", "patch-source"}:
        return "No centralized native downloads found."
    if state.mode == "patch-package":
        return "No patch packages found."
    if state.mode == "dashboard" and state.dashboard_step == 1:
        return "No patch packages found."
    if state.mode == "variants":
        return "No variants or providers found."
    if state.mode == "tweaks-source":
        return "No variants found - create one in the Variants tab first."
    if state.mode == "tweaks-edit":
        return "No patches registered."
    return "Ready."


def selected_label_index(state):
    """Map state.selected_index (which walks selectable options) to the row
    index in `current_labels()`. Modes with non-selectable header rows (like
    tweaks-edit's group headers) need this offset.
    """
    if state.mode == "tweaks-edit":
        target = state.selected_index
        label_index = 0
        seen = 0
        for _, patch_ids in tweaks_edit_groups(state):
            label_index += 1  # group header
            for _ in patch_ids:
                if seen == target:
                    return label_index
                label_index += 1
                seen += 1
        return max(0, label_index - 1)
    return state.selected_index


def visible_items(labels, selected_index, max_items):
    if not labels:
        return None
    max_items = max(1, max_items)
    if len(labels) <= max_items:
        return 0, labels
    half = max_items // 2
    start = max(0, selected_index - half)
    start = min(start, len(labels) - max_items)
    return start, labels[start:start + max_items]


def clamp_ratio(value):
    return max(0.0, min(float(value), 1.0))


def ascii_progress(title, ratio, label, width=24):
    ratio = clamp_ratio(ratio)
    filled = int(round(ratio * width))
    return f"{title}: [{'#' * filled}{'.' * (width - filled)}] {label}"


def progress_specs(state):
    specs = []
    if state.mode == "dashboard":
        specs.append((
            "Wizard",
            (state.dashboard_step + 1) / len(DASHBOARD_STEPS),
            f"{state.dashboard_step + 1}/{len(DASHBOARD_STEPS)} {DASHBOARD_STEPS[state.dashboard_step]}",
        ))
        if state.dashboard_step == 1:
            specs.append(_patch_progress_spec(state))
    elif state.mode == "patch-package":
        specs.append(_patch_progress_spec(state))
    elif state.mode == "variants":
        specs.append((
            "Variant",
            (state.variant_step + 1) / len(VARIANT_STEPS),
            f"{state.variant_step + 1}/{len(VARIANT_STEPS)} {VARIANT_STEPS[state.variant_step]}",
        ))
    return specs


def _patch_progress_spec(state):
    selected = len(selected_dashboard_packages(state))
    total = len(state.patch_packages)
    ratio = selected / total if total else 0.0
    return ("Patches", ratio, f"{selected}/{total} selected")


# -- Footer / key hints -------------------------------------------------------

def footer_lines(state):
    line = f"Theme: {theme_name(state.theme_id)} ({normalize_theme_id(state.theme_id)})."
    if state.mode == "dashboard":
        lines = [state.message, line, _dashboard_key_line(state)]
        if state.dashboard_step == 2:
            lines.append("Profile names: select the Name row, then type or Backspace.")
        return lines
    if state.mode == "patch-package":
        return [
            state.message,
            line,
            "Keys: Left/Right/Tab tabs, Up/Down select, Space toggle, Enter apply, B/Esc back, T theme, Q quit.",
        ]
    if state.mode == "variants":
        lines = [state.message, line, _variant_key_line(state)]
        if state.variant_step == 1:
            lines.append("Variant names: select the Name row, then type or Backspace.")
        if state.variant_step == 2:
            lines.append("Credential env: select the row, then type or Backspace. Raw API keys are not accepted here.")
        if state.variant_step == 3:
            lines.append("Model aliases: select a row, then type or Backspace. Empty rows use provider defaults.")
        return lines
    if state.mode == "tweaks-source":
        return [
            state.message,
            line,
            "Keys: Left/Right/Tab tabs, Up/Down select, Enter pick variant, B/Esc back, T theme, Q quit.",
        ]
    if state.mode == "tweaks-edit":
        return [
            state.message,
            line,
            "Keys: Up/Down select, Space toggle, A apply, B/Esc discard or back, T theme, Q quit.",
        ]
    return [
        state.message,
        line,
        "Keys: Left/Right/Tab tabs, Up/Down select, Enter run, T theme, Q quit.",
    ]


def footer_text(state):
    return " ".join(line for line in footer_lines(state) if line)


def _dashboard_key_line(state):
    if state.dashboard_step == 0:
        action = "Enter choose, R refresh"
    elif state.dashboard_step == 1:
        action = "Space toggle, Enter choose"
    elif state.dashboard_step == 3:
        action = "Enter run"
    else:
        action = "Enter choose"
    return f"Keys: Left/Right/Tab tabs, Up/Down select, {action}, B/Esc back, T theme, Q quit."


def _variant_key_line(state):
    if state.variant_step == 4:
        action = "Space toggle tweak, Enter choose"
    elif state.variant_step == 5:
        action = "Enter choose"
    elif state.variant_step in {1, 2, 3}:
        action = "Type text, Enter choose"
    else:
        action = "Enter choose"
    return f"Keys: Left/Right/Tab tabs, Up/Down select, {action}, B/Esc back, T theme, Q quit."


# -- Text fallback (for headless) ---------------------------------------------

def screen_text(state, height=24):
    lines = [
        f"Workspace: {workspace_root()}",
        state.counts,
        f"Theme: {theme_name(state.theme_id)}",
        f"Tabs: {tab_bar(state)}",
        "",
    ]

    if state.mode == "dashboard":
        lines.extend([dashboard_steps(state), dashboard_summary(state)])
    if state.mode == "variants":
        lines.extend([variant_steps(state), variant_summary(state)])
    for title, ratio, label in progress_specs(state):
        lines.append(ascii_progress(title, ratio, label))
    lines.append("")

    title, labels = current_labels(state)
    lines.append(title)
    cursor = selected_label_index(state)
    visible = visible_items(labels, cursor, max(3, height - 16))
    if visible:
        start_index, visible_labels = visible
        for offset, label in enumerate(visible_labels):
            index = start_index + offset
            prefix = "> " if index == cursor else "  "
            lines.append(prefix + label)
    else:
        lines.append("  " + empty_text(state))

    if state.mode == "tweaks-edit":
        lines.append("")
        lines.append("Patch details")
        for line in tweaks_detail_text(state).splitlines():
            lines.append("  " + line)

    lines.extend(["", state.message, ""])
    lines.extend(footer_lines(state))
    return "\n".join(lines)


def body_text(state, height):
    title, labels = current_labels(state)
    lines = [title]
    cursor = selected_label_index(state)
    visible = visible_items(labels, cursor, max(1, height - 3))
    if visible:
        start_index, visible_labels = visible
        for offset, label in enumerate(visible_labels):
            index = start_index + offset
            prefix = "> " if index == cursor else "  "
            lines.append(prefix + label)
    else:
        lines.append("  " + empty_text(state))
    return "\n".join(lines)


# -- ratatui-backed rendering -------------------------------------------------

def style(Style, Color, fg: Optional[str] = None, bg: Optional[str] = None, bold: bool = False):
    s = Style(fg=color(Color, fg), bg=color(Color, bg))
    if bold:
        s = s.bold()
    return s


def color(Color, name: Optional[str]):
    return getattr(Color, name or "Reset")


def status_style(state, Style, Color):
    theme = active_theme(state)
    lowered = state.message.lower()
    if "failed" in lowered or "invalid" in lowered or "missing" in lowered:
        return style(Style, Color, theme.error_fg, theme.footer_bg, bold=True)
    if "complete" in lowered or "created" in lowered or "loaded" in lowered:
        return style(Style, Color, theme.success_fg, theme.footer_bg, bold=True)
    return style(Style, Color, theme.warning_fg, theme.footer_bg)


def tabs_widget(state, Tabs, Style, Color, theme):
    tabs = Tabs()
    tabs.set_titles(TABS)
    tabs.set_selected(active_tab_index(state))
    tabs.set_divider(" | ")
    tabs.set_block_title("Tabs", True)
    tabs.set_styles(
        style(Style, Color, theme.tab_fg, theme.tab_bg),
        style(Style, Color, theme.tab_selected_fg, theme.tab_selected_bg, bold=True),
    )
    return tabs


def list_widget(state, height, TuiList, Style, Color, theme):
    title, labels = current_labels(state)
    body = TuiList()
    body.set_block_title(title, True)
    body.set_highlight_symbol(">> ")
    body.set_highlight_style(
        style(Style, Color, theme.highlight_fg, theme.highlight_bg, bold=True)
    )

    if labels:
        item_style = style(Style, Color, theme.body_fg, theme.body_bg)
        for label in labels:
            body.append_item(label, item_style)
        cursor = selected_label_index(state)
        body.set_selected(cursor)
        body.set_scroll_offset(max(0, cursor - max(0, height // 2)))
    else:
        body.append_item(empty_text(state), style(Style, Color, theme.body_fg, theme.body_bg))
        body.set_selected(None)
    return body


def tweaks_detail_widget(state, Paragraph, Style, Color, theme):
    """Right-pane Paragraph for tweaks-edit mode."""
    text = tweaks_detail_text(state)
    paragraph = Paragraph.from_text(text)
    paragraph.set_block_title("Patch details", True)
    paragraph.set_style(style(Style, Color, theme.body_fg, theme.body_bg))
    paragraph.set_wrap(True)
    return paragraph


def gauge_widget(title, ratio, label, Gauge, Style, Color, theme):
    gauge = Gauge()
    gauge.ratio(clamp_ratio(ratio))
    gauge.label(label)
    gauge.set_block_title(title, True)
    gauge.set_styles(
        style(Style, Color, theme.gauge_fg, theme.gauge_bg),
        style(Style, Color, theme.gauge_label_fg, theme.gauge_label_bg, bold=True),
        style(Style, Color, theme.gauge_fill_fg, theme.gauge_fill_bg, bold=True),
    )
    return gauge


def render_frame(term, state, width, height, Paragraph, Style, Color, DrawCmd, Tabs, TuiList, Gauge):
    from ratatui_py.layout import split_v as _split_v
    width = max(1, width - 1)
    height = max(1, height - 1)
    theme = active_theme(state)
    header_lines = [
        f"Workspace: {workspace_root()}",
        state.counts,
        f"Theme: {theme.name}",
    ]
    if state.mode == "dashboard":
        header_lines.extend([dashboard_steps(state), dashboard_summary(state)])
    if state.mode == "variants":
        header_lines.extend([variant_steps(state), variant_summary(state)])

    header_height = min(max(4, len(header_lines) + 2), height)
    tabs_height = 3 if height - header_height > 3 else 0
    progress = progress_specs(state)
    progress_height = min(
        len(progress) * 3,
        max(0, height - header_height - tabs_height - 2),
    )
    footer_height = min(6, max(1, height - header_height - tabs_height - progress_height))
    body_height = max(1, height - header_height - tabs_height - progress_height - footer_height)

    header = Paragraph.from_text("\n".join(header_lines))
    header.set_block_title("cc-extractor", True)
    header.set_style(style(Style, Color, theme.header_fg, theme.header_bg, bold=True))
    header.set_wrap(True)

    tabs = tabs_widget(state, Tabs, Style, Color, theme)
    body = list_widget(state, body_height, TuiList, Style, Color, theme)

    footer = Paragraph.from_text("\n".join(footer_lines(state)))
    footer.set_block_title("Status", True)
    footer.set_style(status_style(state, Style, Color))
    footer.set_wrap(True)

    commands = [DrawCmd.paragraph(header, (0, 0, width, header_height))]
    top = header_height
    if tabs_height:
        commands.append(DrawCmd.tabs(tabs, (0, top, width, tabs_height)))
        top += tabs_height
    for index, (title, ratio, label) in enumerate(progress):
        if top + 2 >= height:
            break
        commands.append(
            DrawCmd.gauge(
                gauge_widget(title, ratio, label, Gauge, Style, Color, theme),
                (0, top, width, 3),
            )
        )
        top += 3
        if (index + 1) * 3 >= progress_height:
            break

    if state.mode == "tweaks-edit" and width > 60:
        left_rect, right_rect = _split_v((0, top, width, body_height), 0.45, 0.55, gap=1)
        detail = tweaks_detail_widget(state, Paragraph, Style, Color, theme)
        commands.append(DrawCmd.list(body, left_rect))
        commands.append(DrawCmd.paragraph(detail, right_rect))
    else:
        commands.append(DrawCmd.list(body, (0, top, width, body_height)))
    footer_top = top + body_height
    commands.append(
        DrawCmd.paragraph(footer, (0, footer_top, width, max(1, height - footer_top)))
    )
    term.draw_frame(commands)
