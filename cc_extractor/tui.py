import contextlib
import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from .bun_extract import parse_bun_binary
from .download_index import download_versions, load_download_index, refresh_download_index
from .downloader import download_binary
from .extractor import extract_all
from .patch_workflow import apply_patch_packages_to_native
from .workspace import (
    NativeArtifact,
    PatchPackage,
    PatchProfile,
    delete_patch_profile,
    extraction_paths,
    load_tui_settings,
    native_artifact_from_path,
    rename_patch_profile,
    save_patch_profile,
    save_tui_settings,
    scan_extractions,
    scan_native_downloads,
    scan_npm_downloads,
    scan_patch_packages,
    scan_patch_profiles,
    short_sha,
    workspace_root,
)


TABS = ["Dashboard", "Inspect", "Extract", "Patch"]
TAB_MODES = ["dashboard", "inspect", "extract", "patch-source"]
DASHBOARD_STEPS = ["Source", "Patches", "Profiles", "Review"]
SOURCE_LATEST = "latest"
SOURCE_VERSION = "version"
SOURCE_ARTIFACT = "artifact"
DEFAULT_THEME_ID = "hacker-bbs"
THEME_ORDER = [DEFAULT_THEME_ID, "unicorn", "dark", "light"]


@dataclass(frozen=True)
class TuiTheme:
    theme_id: str
    name: str
    header_fg: str
    header_bg: str
    body_fg: str
    body_bg: str
    footer_fg: str
    footer_bg: str
    tab_fg: str
    tab_bg: str
    tab_selected_fg: str
    tab_selected_bg: str
    highlight_fg: str
    highlight_bg: str
    success_fg: str
    warning_fg: str
    error_fg: str
    gauge_fg: str
    gauge_bg: str
    gauge_label_fg: str
    gauge_label_bg: str
    gauge_fill_fg: str
    gauge_fill_bg: str


TUI_THEMES = {
    "hacker-bbs": TuiTheme(
        theme_id="hacker-bbs",
        name="Hacker BBS",
        header_fg="LightGreen",
        header_bg="Black",
        body_fg="LightCyan",
        body_bg="Black",
        footer_fg="LightYellow",
        footer_bg="Black",
        tab_fg="Green",
        tab_bg="Black",
        tab_selected_fg="Black",
        tab_selected_bg="LightGreen",
        highlight_fg="Black",
        highlight_bg="LightGreen",
        success_fg="LightGreen",
        warning_fg="LightYellow",
        error_fg="LightRed",
        gauge_fg="LightGreen",
        gauge_bg="Black",
        gauge_label_fg="Black",
        gauge_label_bg="LightGreen",
        gauge_fill_fg="LightGreen",
        gauge_fill_bg="Black",
    ),
    "unicorn": TuiTheme(
        theme_id="unicorn",
        name="Unicorn",
        header_fg="LightMagenta",
        header_bg="Black",
        body_fg="White",
        body_bg="Black",
        footer_fg="LightCyan",
        footer_bg="Black",
        tab_fg="LightCyan",
        tab_bg="Black",
        tab_selected_fg="Black",
        tab_selected_bg="LightMagenta",
        highlight_fg="Black",
        highlight_bg="LightMagenta",
        success_fg="LightGreen",
        warning_fg="LightYellow",
        error_fg="LightRed",
        gauge_fg="LightMagenta",
        gauge_bg="Black",
        gauge_label_fg="Black",
        gauge_label_bg="LightYellow",
        gauge_fill_fg="LightMagenta",
        gauge_fill_bg="Black",
    ),
    "dark": TuiTheme(
        theme_id="dark",
        name="Dark",
        header_fg="LightCyan",
        header_bg="Black",
        body_fg="White",
        body_bg="Black",
        footer_fg="Yellow",
        footer_bg="Black",
        tab_fg="Gray",
        tab_bg="Black",
        tab_selected_fg="Black",
        tab_selected_bg="LightCyan",
        highlight_fg="Black",
        highlight_bg="LightCyan",
        success_fg="LightGreen",
        warning_fg="LightYellow",
        error_fg="LightRed",
        gauge_fg="LightCyan",
        gauge_bg="Black",
        gauge_label_fg="Black",
        gauge_label_bg="LightCyan",
        gauge_fill_fg="LightCyan",
        gauge_fill_bg="Black",
    ),
    "light": TuiTheme(
        theme_id="light",
        name="Light",
        header_fg="Blue",
        header_bg="White",
        body_fg="Black",
        body_bg="White",
        footer_fg="Blue",
        footer_bg="White",
        tab_fg="DarkGray",
        tab_bg="White",
        tab_selected_fg="White",
        tab_selected_bg="Blue",
        highlight_fg="White",
        highlight_bg="Blue",
        success_fg="Green",
        warning_fg="Yellow",
        error_fg="Red",
        gauge_fg="Blue",
        gauge_bg="White",
        gauge_label_fg="White",
        gauge_label_bg="Blue",
        gauge_fill_fg="Blue",
        gauge_fill_bg="White",
    ),
}


@dataclass
class MenuOption:
    kind: str
    label: str
    value: object = None


@dataclass
class TuiState:
    mode: str = "dashboard"
    selected_index: int = 0
    message: str = ""
    theme_id: str = DEFAULT_THEME_ID
    native_artifacts: List[NativeArtifact] = field(default_factory=list)
    patch_packages: List[PatchPackage] = field(default_factory=list)
    patch_profiles: List[PatchProfile] = field(default_factory=list)
    download_index: dict = field(default_factory=dict)
    download_versions: List[str] = field(default_factory=list)
    selected_source_index: int = 0
    selected_patch_indexes: List[int] = field(default_factory=list)
    counts: str = ""
    dashboard_step: int = 0
    dashboard_source_kind: str = SOURCE_LATEST
    dashboard_source_version: str = ""
    dashboard_source_artifact_index: int = 0
    dashboard_profile_name: str = ""
    dashboard_loaded_profile_id: str = ""
    dashboard_delete_confirm_id: str = ""

    def refresh(self):
        self.theme_id = _normalize_theme_id(self.theme_id)
        self.native_artifacts = scan_native_downloads()
        npm_count = len(scan_npm_downloads())
        extraction_count = len(scan_extractions())
        self.patch_packages = scan_patch_packages()
        self.patch_profiles = scan_patch_profiles()
        self.download_index = load_download_index()
        self.download_versions = download_versions(self.download_index, "binary")
        self.counts = (
            f"Native: {len(self.native_artifacts)}  "
            f"NPM: {npm_count}  "
            f"Extractions: {extraction_count}  "
            f"Patch packages: {len(self.patch_packages)}  "
            f"Profiles: {len(self.patch_profiles)}"
        )
        self.selected_patch_indexes = [
            index for index in self.selected_patch_indexes
            if 0 <= index < len(self.patch_packages)
        ]
        self.selected_index = self._clamp(self.selected_index, self.item_count())
        self.selected_source_index = self._clamp(self.selected_source_index, len(self.native_artifacts))
        self.dashboard_source_artifact_index = self._clamp(
            self.dashboard_source_artifact_index,
            len(self.native_artifacts),
        )

    def item_count(self):
        if self.mode == "dashboard":
            return len(_dashboard_options(self))
        if self.mode in {"inspect", "extract", "patch-source"}:
            return len(self.native_artifacts)
        if self.mode == "patch-package":
            return len(self.patch_packages)
        return 1

    def move(self, offset):
        count = self.item_count()
        if count < 1:
            self.selected_index = 0
            return
        self.selected_index = max(0, min(self.selected_index + offset, count - 1))

    def _clamp(self, value, count):
        if count < 1:
            return 0
        return max(0, min(value, count - 1))


def run_tui():
    try:
        from ratatui_py import (
            App,
            Color,
            DrawCmd,
            Gauge,
            KeyCode,
            List as TuiList,
            Paragraph,
            Style,
            Tabs,
        )
    except (ImportError, OSError, RuntimeError) as exc:
        raise RuntimeError(f"ratatui is unavailable: {exc}") from exc

    state = TuiState(theme_id=_load_saved_theme_id())
    state.refresh()

    def render(term, app_state):
        width, height = term.size()
        try:
            _render_frame(
                term,
                app_state,
                width,
                height,
                Paragraph,
                Style,
                Color,
                DrawCmd,
                Tabs,
                TuiList,
                Gauge,
            )
        except Exception:
            theme = _active_theme(app_state)
            screen = Paragraph.from_text(_screen_text(app_state, height=max(1, height - 1)))
            screen.set_block_title("cc-extractor", True)
            screen.set_style(_style(Style, Color, theme.body_fg, theme.body_bg, bold=True))
            screen.set_wrap(True)
            term.draw_paragraph(screen, (0, 0, max(1, width - 1), max(1, height - 1)))

    def on_event(term, event, app_state):
        if event.get("kind") != "key":
            return True

        code = event.get("code")
        char_code = event.get("ch") or 0

        if code == int(KeyCode.Up):
            app_state.move(-1)
        elif code == int(KeyCode.Down):
            app_state.move(1)
        elif code == int(KeyCode.Left):
            _move_tab(app_state, -1)
        elif code == int(KeyCode.Right) or code == int(KeyCode.Tab):
            _move_tab(app_state, 1)
        elif code == int(KeyCode.Home):
            app_state.selected_index = 0
        elif code == int(KeyCode.End):
            app_state.selected_index = max(0, app_state.item_count() - 1)
        elif code == int(KeyCode.Backspace):
            if not _dashboard_backspace(app_state):
                _go_back(app_state)
        elif code == int(KeyCode.Esc):
            _go_back(app_state)
        elif code == int(KeyCode.Enter):
            return _activate(app_state)
        elif code == int(KeyCode.Char) and char_code:
            char = chr(char_code)
            if char == "T":
                _cycle_theme(app_state)
                return True
            if _dashboard_accepts_profile_text(app_state):
                if char.isprintable() and char not in "\r\n\t":
                    app_state.dashboard_profile_name += char
                    app_state.dashboard_delete_confirm_id = ""
                return True

            lowered = char.lower()
            if lowered == "q":
                return False
            if lowered == "b":
                _go_back(app_state)
            elif char == " ":
                _toggle_selected(app_state)
            elif lowered == "r" and app_state.mode == "dashboard" and app_state.dashboard_step == 0:
                _refresh_dashboard_index(app_state)

        return True

    def on_start(term, app_state):
        term.enter_alt()
        term.enable_raw()
        term.clear()

    def on_stop(exc, term, app_state):
        term.show_cursor()
        term.disable_raw()
        term.leave_alt()

    app = App(
        render=render,
        on_event=on_event,
        on_start=on_start,
        on_stop=on_stop,
        tick_ms=3_600_000,
        clear_each_frame=True,
    )
    app.run(state)


def _screen_text(state, height=24):
    lines = [
        f"Workspace: {workspace_root()}",
        state.counts,
        f"Theme: {_theme_name(state.theme_id)}",
        f"Tabs: {_tab_bar(state)}",
        "",
    ]

    if state.mode == "dashboard":
        lines.extend([
            _dashboard_steps(state),
            _dashboard_summary(state),
        ])
    for title, ratio, label in _progress_specs(state):
        lines.append(_ascii_progress(title, ratio, label))
    lines.append("")

    title, labels = _current_labels(state)
    lines.append(title)
    visible = _visible_items(labels, state.selected_index, max(3, height - 16))
    if visible:
        start_index, visible_labels = visible
        for offset, label in enumerate(visible_labels):
            index = start_index + offset
            prefix = "> " if index == state.selected_index else "  "
            lines.append(prefix + label)
    else:
        lines.append("  " + _empty_text(state))

    lines.extend(["", state.message, ""])
    lines.extend(_footer_lines(state))
    return "\n".join(lines)


def _render_frame(
    term,
    state,
    width,
    height,
    Paragraph,
    Style,
    Color,
    DrawCmd,
    Tabs,
    TuiList,
    Gauge,
):
    width = max(1, width - 1)
    height = max(1, height - 1)
    theme = _active_theme(state)
    header_lines = [
        f"Workspace: {workspace_root()}",
        state.counts,
        f"Theme: {theme.name}",
    ]
    if state.mode == "dashboard":
        header_lines.extend([
            _dashboard_steps(state),
            _dashboard_summary(state),
        ])

    header_height = min(max(4, len(header_lines) + 2), height)
    tabs_height = 3 if height - header_height > 3 else 0
    progress_specs = _progress_specs(state)
    progress_height = min(
        len(progress_specs) * 3,
        max(0, height - header_height - tabs_height - 2),
    )
    footer_height = min(6, max(1, height - header_height - tabs_height - progress_height))
    body_height = max(1, height - header_height - tabs_height - progress_height - footer_height)

    header = Paragraph.from_text("\n".join(header_lines))
    header.set_block_title("cc-extractor", True)
    header.set_style(_style(Style, Color, theme.header_fg, theme.header_bg, bold=True))
    header.set_wrap(True)

    tabs = _tabs_widget(state, Tabs, Style, Color, theme)
    body = _list_widget(state, body_height, TuiList, Style, Color, theme)

    footer = Paragraph.from_text("\n".join(_footer_lines(state)))
    footer.set_block_title("Status", True)
    footer.set_style(_status_style(state, Style, Color))
    footer.set_wrap(True)

    commands = [DrawCmd.paragraph(header, (0, 0, width, header_height))]
    top = header_height
    if tabs_height:
        commands.append(DrawCmd.tabs(tabs, (0, top, width, tabs_height)))
        top += tabs_height
    for index, (title, ratio, label) in enumerate(progress_specs):
        if top + 2 >= height:
            break
        commands.append(
            DrawCmd.gauge(
                _gauge_widget(title, ratio, label, Gauge, Style, Color, theme),
                (0, top, width, 3),
            )
        )
        top += 3
        if (index + 1) * 3 >= progress_height:
            break

    commands.append(DrawCmd.list(body, (0, top, width, body_height)))
    footer_top = top + body_height
    commands.append(
        DrawCmd.paragraph(footer, (0, footer_top, width, max(1, height - footer_top)))
    )
    term.draw_frame(commands)


def _tabs_widget(state, Tabs, Style, Color, theme):
    tabs = Tabs()
    tabs.set_titles(TABS)
    tabs.set_selected(_active_tab_index(state))
    tabs.set_divider(" | ")
    tabs.set_block_title("Tabs", True)
    tabs.set_styles(
        _style(Style, Color, theme.tab_fg, theme.tab_bg),
        _style(Style, Color, theme.tab_selected_fg, theme.tab_selected_bg, bold=True),
    )
    return tabs


def _list_widget(state, height, TuiList, Style, Color, theme):
    title, labels = _current_labels(state)
    body = TuiList()
    body.set_block_title(title, True)
    body.set_highlight_symbol(">> ")
    body.set_highlight_style(
        _style(Style, Color, theme.highlight_fg, theme.highlight_bg, bold=True)
    )

    if labels:
        item_style = _style(Style, Color, theme.body_fg, theme.body_bg)
        for label in labels:
            body.append_item(label, item_style)
        body.set_selected(state.selected_index)
        body.set_scroll_offset(max(0, state.selected_index - max(0, height // 2)))
    else:
        body.append_item(_empty_text(state), _style(Style, Color, theme.body_fg, theme.body_bg))
        body.set_selected(None)
    return body


def _gauge_widget(title, ratio, label, Gauge, Style, Color, theme):
    gauge = Gauge()
    gauge.ratio(_clamp_ratio(ratio))
    gauge.label(label)
    gauge.set_block_title(title, True)
    gauge.set_styles(
        _style(Style, Color, theme.gauge_fg, theme.gauge_bg),
        _style(Style, Color, theme.gauge_label_fg, theme.gauge_label_bg, bold=True),
        _style(Style, Color, theme.gauge_fill_fg, theme.gauge_fill_bg, bold=True),
    )
    return gauge


def _style(Style, Color, fg: Optional[str] = None, bg: Optional[str] = None, bold: bool = False):
    style = Style(fg=_color(Color, fg), bg=_color(Color, bg))
    if bold:
        style = style.bold()
    return style


def _color(Color, name: Optional[str]):
    return getattr(Color, name or "Reset")


def _body_text(state, height):
    title, labels = _current_labels(state)
    lines = [title]
    visible = _visible_items(labels, state.selected_index, max(1, height - 3))
    if visible:
        start_index, visible_labels = visible
        for offset, label in enumerate(visible_labels):
            index = start_index + offset
            prefix = "> " if index == state.selected_index else "  "
            lines.append(prefix + label)
    else:
        lines.append("  " + _empty_text(state))
    return "\n".join(lines)


def _status_style(state, Style, Color):
    theme = _active_theme(state)
    lowered = state.message.lower()
    if "failed" in lowered or "invalid" in lowered or "missing" in lowered:
        return _style(Style, Color, theme.error_fg, theme.footer_bg, bold=True)
    if "complete" in lowered or "created" in lowered or "loaded" in lowered:
        return _style(Style, Color, theme.success_fg, theme.footer_bg, bold=True)
    return _style(Style, Color, theme.warning_fg, theme.footer_bg)


def _current_labels(state):
    if state.mode == "dashboard":
        return _dashboard_title(state), [option.label for option in _dashboard_options(state)]
    if state.mode == "inspect":
        return "Inspect", [_format_native_artifact(artifact) for artifact in state.native_artifacts]
    if state.mode == "extract":
        return "Extract", [_format_native_artifact(artifact) for artifact in state.native_artifacts]
    if state.mode == "patch-source":
        return "Patch source", [_format_native_artifact(artifact) for artifact in state.native_artifacts]
    if state.mode == "patch-package":
        labels = []
        for index, package in enumerate(state.patch_packages):
            marker = "[x]" if index in state.selected_patch_indexes else "[ ]"
            labels.append(f"{marker} {package.patch_id}@{package.version}  {package.name}")
        return "Patch packages", labels
    return "Status", []


def _empty_text(state):
    if state.mode in {"inspect", "extract", "patch-source"}:
        return "No centralized native downloads found."
    if state.mode == "patch-package":
        return "No patch packages found."
    if state.mode == "dashboard" and state.dashboard_step == 1:
        return "No patch packages found."
    return "Ready."


def _tab_bar(state):
    active = _active_tab(state)
    parts = []
    for tab in TABS:
        if tab == active:
            parts.append(f"[{tab}]")
        else:
            parts.append(f" {tab} ")
    return "  ".join(parts)


def _active_tab(state):
    if state.mode == "patch-package":
        return "Patch"
    for tab, mode in zip(TABS, TAB_MODES):
        if state.mode == mode:
            return tab
    return "Dashboard"


def _active_tab_index(state):
    return TABS.index(_active_tab(state))


def _visible_items(labels, selected_index, max_items):
    if not labels:
        return None
    max_items = max(1, max_items)
    if len(labels) <= max_items:
        return 0, labels
    half = max_items // 2
    start = max(0, selected_index - half)
    start = min(start, len(labels) - max_items)
    return start, labels[start:start + max_items]


def _footer_lines(state):
    theme_line = f"Theme: {_theme_name(state.theme_id)} ({_normalize_theme_id(state.theme_id)})."
    if state.mode == "dashboard":
        return [
            state.message,
            theme_line,
            "Keys: Up/Down select, Enter choose, Space toggle, B/Esc back, Tab tabs, T theme, Q quit.",
            "Profile names: select the Name row, then type or Backspace.",
        ]
    if state.mode == "patch-package":
        return [
            state.message,
            theme_line,
            "Keys: Left/Right tabs, Up/Down select, Space toggle, Enter apply, B/Esc back, T theme, Q quit.",
        ]
    return [
        state.message,
        theme_line,
        "Keys: Left/Right tabs, Up/Down select, Enter run, T theme, Q quit.",
    ]


def _footer_text(state):
    return " ".join(line for line in _footer_lines(state) if line)


def _load_saved_theme_id():
    return _normalize_theme_id(load_tui_settings().get("themeId"))


def _normalize_theme_id(theme_id):
    if theme_id in TUI_THEMES:
        return theme_id
    return DEFAULT_THEME_ID


def _active_theme(state):
    return TUI_THEMES[_normalize_theme_id(state.theme_id)]


def _theme_name(theme_id):
    return TUI_THEMES[_normalize_theme_id(theme_id)].name


def _cycle_theme(state):
    current = _normalize_theme_id(state.theme_id)
    next_index = (THEME_ORDER.index(current) + 1) % len(THEME_ORDER)
    state.theme_id = THEME_ORDER[next_index]
    try:
        save_tui_settings({"themeId": state.theme_id})
        state.message = f"Theme saved: {_theme_name(state.theme_id)}"
    except Exception as exc:
        state.message = f"Theme changed but save failed: {exc}"


def _progress_specs(state):
    specs = []
    if state.mode == "dashboard":
        specs.append((
            "Wizard",
            (state.dashboard_step + 1) / len(DASHBOARD_STEPS),
            f"{state.dashboard_step + 1}/{len(DASHBOARD_STEPS)} {DASHBOARD_STEPS[state.dashboard_step]}",
        ))
        if state.dashboard_step == 1:
            specs.append(("Patches", _patch_selection_ratio(state), _patch_selection_label(state)))
    elif state.mode == "patch-package":
        specs.append(("Patches", _patch_selection_ratio(state), _patch_selection_label(state)))
    return specs


def _patch_selection_ratio(state):
    total = len(state.patch_packages)
    if total < 1:
        return 0.0
    return len(_selected_dashboard_packages(state)) / total


def _patch_selection_label(state):
    return f"{len(_selected_dashboard_packages(state))}/{len(state.patch_packages)} selected"


def _ascii_progress(title, ratio, label, width=24):
    ratio = _clamp_ratio(ratio)
    filled = int(round(ratio * width))
    return f"{title}: [{'#' * filled}{'.' * (width - filled)}] {label}"


def _clamp_ratio(value):
    return max(0.0, min(float(value), 1.0))


def _dashboard_title(state):
    return f"Dashboard: {DASHBOARD_STEPS[state.dashboard_step]}"


def _dashboard_steps(state):
    labels = []
    for index, step in enumerate(DASHBOARD_STEPS):
        if index == state.dashboard_step:
            labels.append(f"[{step}]")
        elif index < state.dashboard_step:
            labels.append(f"{step}*")
        else:
            labels.append(step)
    return "Steps: " + " > ".join(labels)


def _dashboard_summary(state):
    profile = _loaded_profile(state)
    profile_label = profile.name if profile else "none"
    return (
        f"Source: {_dashboard_source_label(state)}  "
        f"Patches: {len(_selected_dashboard_packages(state))}  "
        f"Profile: {profile_label}"
    )


def _dashboard_options(state):
    if state.dashboard_step == 0:
        return _dashboard_source_options(state)
    if state.dashboard_step == 1:
        return _dashboard_patch_options(state)
    if state.dashboard_step == 2:
        return _dashboard_profile_options(state)
    return _dashboard_review_options(state)


def _dashboard_source_options(state):
    options = [
        MenuOption("source-latest", _selected_label(state, SOURCE_LATEST, None, "Latest native binary")),
        MenuOption("refresh-index", "Refresh version list"),
    ]
    latest = state.download_index.get("binary", {}).get("latest")
    for version in state.download_versions:
        suffix = " (latest)" if version == latest else ""
        label = f"Native {version}{suffix}"
        options.append(MenuOption("source-version", _selected_label(state, SOURCE_VERSION, version, label), version))
    if state.native_artifacts:
        options.append(MenuOption("section", "Downloaded native artifacts"))
    for index, artifact in enumerate(state.native_artifacts):
        label = f"Downloaded {_format_native_artifact(artifact)}"
        options.append(MenuOption("source-artifact", _selected_label(state, SOURCE_ARTIFACT, index, label), index))
    return options


def _dashboard_patch_options(state):
    options = []
    for index, package in enumerate(state.patch_packages):
        marker = "[x]" if index in state.selected_patch_indexes else "[ ]"
        options.append(MenuOption("patch-toggle", f"{marker} {package.patch_id}@{package.version}  {package.name}", index))

    if state.patch_profiles:
        options.append(MenuOption("section", "Saved profiles"))
    for profile in state.patch_profiles:
        missing = _profile_missing_refs(state, profile)
        if missing:
            label = f"Load profile: {profile.name} (invalid, missing {', '.join(missing)})"
        else:
            label = f"Load profile: {profile.name} ({len(profile.patches)} patches)"
        options.append(MenuOption("profile-load", label, profile.profile_id))

    options.append(MenuOption("patch-continue", "Continue to profile management"))
    return options


def _dashboard_profile_options(state):
    name = state.dashboard_profile_name or "(type a profile name)"
    options = [
        MenuOption("profile-name", f"Name: {name}"),
        MenuOption("profile-create", "Create new profile from selected patches"),
        MenuOption("review-continue", "Continue to review"),
    ]
    for profile in state.patch_profiles:
        suffix = " [loaded]" if profile.profile_id == state.dashboard_loaded_profile_id else ""
        options.extend([
            MenuOption("profile-load", f"Load profile: {profile.name}{suffix}", profile.profile_id),
            MenuOption("profile-rename", f"Rename profile to typed name: {profile.name}", profile.profile_id),
            MenuOption("profile-overwrite", f"Overwrite profile with selected patches: {profile.name}", profile.profile_id),
            MenuOption("profile-delete", _delete_label(state, profile), profile.profile_id),
        ])
    return options


def _dashboard_review_options(state):
    return [
        MenuOption("review-run", "Run dashboard build"),
        MenuOption("review-back", "Back to profile management"),
        MenuOption("review-reset", "Reset dashboard wizard"),
    ]


def _selected_label(state, kind, value, label):
    selected = False
    if state.dashboard_source_kind == kind:
        if kind == SOURCE_LATEST:
            selected = True
        elif kind == SOURCE_VERSION:
            selected = state.dashboard_source_version == value
        elif kind == SOURCE_ARTIFACT:
            selected = state.dashboard_source_artifact_index == value
    return f"* {label}" if selected else f"  {label}"


def _delete_label(state, profile):
    if state.dashboard_delete_confirm_id == profile.profile_id:
        return f"Confirm delete profile: {profile.name}"
    return f"Delete profile: {profile.name}"


def _activate(state):
    state.message = ""
    if state.mode == "dashboard":
        _activate_dashboard(state)
    elif state.mode == "inspect":
        _activate_inspect(state)
    elif state.mode == "extract":
        _activate_extract(state)
    elif state.mode == "patch-source":
        _activate_patch_source(state)
    elif state.mode == "patch-package":
        _activate_patch_packages(state)

    state.refresh()
    return True


def _activate_dashboard(state):
    option = _selected_dashboard_option(state)
    if option is None:
        return

    if option.kind != "profile-delete":
        state.dashboard_delete_confirm_id = ""

    if option.kind == "section":
        return
    if option.kind == "source-latest":
        state.dashboard_source_kind = SOURCE_LATEST
        state.dashboard_source_version = ""
        _advance_dashboard(state)
    elif option.kind == "source-version":
        state.dashboard_source_kind = SOURCE_VERSION
        state.dashboard_source_version = option.value
        _advance_dashboard(state)
    elif option.kind == "source-artifact":
        state.dashboard_source_kind = SOURCE_ARTIFACT
        state.dashboard_source_artifact_index = int(option.value)
        _advance_dashboard(state)
    elif option.kind == "refresh-index":
        _refresh_dashboard_index(state)
    elif option.kind == "patch-toggle":
        _toggle_dashboard_patch(state, int(option.value))
    elif option.kind == "profile-load":
        _load_dashboard_profile(state, str(option.value))
    elif option.kind == "patch-continue":
        if _require_dashboard_patches(state):
            _advance_dashboard(state)
    elif option.kind == "profile-name":
        state.message = "Type a profile name here, then choose a profile action."
    elif option.kind == "profile-create":
        _create_dashboard_profile(state)
    elif option.kind == "profile-rename":
        _rename_dashboard_profile(state, str(option.value))
    elif option.kind == "profile-overwrite":
        _overwrite_dashboard_profile(state, str(option.value))
    elif option.kind == "profile-delete":
        _delete_dashboard_profile(state, str(option.value))
    elif option.kind == "review-continue":
        if _require_dashboard_patches(state):
            _advance_dashboard(state)
    elif option.kind == "review-run":
        _run_dashboard_build(state)
    elif option.kind == "review-back":
        state.dashboard_step = 2
        state.selected_index = 0
    elif option.kind == "review-reset":
        _reset_dashboard(state)


def _refresh_dashboard_index(state):
    try:
        index, output = _run_quiet(refresh_download_index)
        state.download_index = index
        state.download_versions = download_versions(index, "binary")
        state.message = f"Saved {len(state.download_versions)} native versions to {workspace_root() / 'download-index.json'}"
    except Exception as exc:
        state.message = f"Refresh failed: {exc}"


def _advance_dashboard(state):
    state.dashboard_step = min(state.dashboard_step + 1, len(DASHBOARD_STEPS) - 1)
    state.selected_index = 0


def _reset_dashboard(state):
    state.dashboard_step = 0
    state.selected_index = 0
    state.selected_patch_indexes = []
    state.dashboard_source_kind = SOURCE_LATEST
    state.dashboard_source_version = ""
    state.dashboard_source_artifact_index = 0
    state.dashboard_profile_name = ""
    state.dashboard_loaded_profile_id = ""
    state.dashboard_delete_confirm_id = ""
    state.message = "Dashboard reset."


def _selected_dashboard_option(state):
    options = _dashboard_options(state)
    if not options:
        return None
    index = max(0, min(state.selected_index, len(options) - 1))
    return options[index]


def _toggle_selected(state):
    if state.mode == "dashboard":
        option = _selected_dashboard_option(state)
        if option and option.kind == "patch-toggle":
            _toggle_dashboard_patch(state, int(option.value))
    elif state.mode == "patch-package":
        _toggle_patch(state)


def _toggle_dashboard_patch(state, index):
    if index in state.selected_patch_indexes:
        state.selected_patch_indexes.remove(index)
        state.dashboard_loaded_profile_id = ""
    else:
        state.selected_patch_indexes.append(index)
        state.selected_patch_indexes.sort()
        state.dashboard_loaded_profile_id = ""


def _dashboard_accepts_profile_text(state):
    if state.mode != "dashboard" or state.dashboard_step != 2:
        return False
    option = _selected_dashboard_option(state)
    return option is not None and option.kind == "profile-name"


def _dashboard_backspace(state):
    if not _dashboard_accepts_profile_text(state):
        return False
    state.dashboard_profile_name = state.dashboard_profile_name[:-1]
    state.dashboard_delete_confirm_id = ""
    return True


def _profile_refs_by_key(state):
    return {
        (package.patch_id, package.version): index
        for index, package in enumerate(state.patch_packages)
    }


def _profile_missing_refs(state, profile):
    available = _profile_refs_by_key(state)
    missing = []
    for ref in profile.patches:
        key = (ref["id"], ref["version"])
        if key not in available:
            missing.append(f"{ref['id']}@{ref['version']}")
    return missing


def _load_dashboard_profile(state, profile_id):
    profile = _profile_by_id(state, profile_id)
    if profile is None:
        state.message = f"Profile not found: {profile_id}"
        return False

    missing = _profile_missing_refs(state, profile)
    if missing:
        state.dashboard_loaded_profile_id = profile.profile_id
        state.message = f"Profile {profile.name} is invalid, missing {', '.join(missing)}"
        return False

    available = _profile_refs_by_key(state)
    state.selected_patch_indexes = [
        available[(ref["id"], ref["version"])]
        for ref in profile.patches
    ]
    state.selected_patch_indexes.sort()
    state.dashboard_profile_name = profile.name
    state.dashboard_loaded_profile_id = profile.profile_id
    state.message = f"Loaded profile: {profile.name}"
    return True


def _create_dashboard_profile(state):
    if not _require_dashboard_patches(state):
        return
    try:
        profile = save_patch_profile(
            state.dashboard_profile_name,
            _selected_patch_refs(state),
            overwrite=False,
        )
        state.dashboard_loaded_profile_id = profile.profile_id
        state.dashboard_profile_name = profile.name
        state.message = f"Created profile: {profile.name}"
    except Exception as exc:
        state.message = f"Create profile failed: {exc}"


def _rename_dashboard_profile(state, profile_id):
    if not state.dashboard_profile_name.strip():
        state.message = "Type a non-empty profile name before renaming."
        return
    try:
        profile = rename_patch_profile(profile_id, state.dashboard_profile_name)
        if state.dashboard_loaded_profile_id == profile_id:
            state.dashboard_loaded_profile_id = profile.profile_id
        state.dashboard_profile_name = profile.name
        state.message = f"Renamed profile: {profile.name}"
    except Exception as exc:
        state.message = f"Rename profile failed: {exc}"


def _overwrite_dashboard_profile(state, profile_id):
    if not _require_dashboard_patches(state):
        return
    profile = _profile_by_id(state, profile_id)
    if profile is None:
        state.message = f"Profile not found: {profile_id}"
        return
    try:
        updated = save_patch_profile(
            profile.name,
            _selected_patch_refs(state),
            profile_id=profile.profile_id,
            overwrite=True,
        )
        state.dashboard_loaded_profile_id = updated.profile_id
        state.dashboard_profile_name = updated.name
        state.message = f"Overwrote profile: {updated.name}"
    except Exception as exc:
        state.message = f"Overwrite profile failed: {exc}"


def _delete_dashboard_profile(state, profile_id):
    profile = _profile_by_id(state, profile_id)
    if profile is None:
        state.message = f"Profile not found: {profile_id}"
        return
    if state.dashboard_delete_confirm_id != profile_id:
        state.dashboard_delete_confirm_id = profile_id
        state.message = f"Press Enter again to delete profile: {profile.name}"
        return
    try:
        delete_patch_profile(profile_id)
        if state.dashboard_loaded_profile_id == profile_id:
            state.dashboard_loaded_profile_id = ""
        state.dashboard_delete_confirm_id = ""
        state.message = f"Deleted profile: {profile.name}"
    except Exception as exc:
        state.message = f"Delete profile failed: {exc}"


def _profile_by_id(state, profile_id):
    for profile in state.patch_profiles:
        if profile.profile_id == profile_id:
            return profile
    return None


def _loaded_profile(state):
    if not state.dashboard_loaded_profile_id:
        return None
    return _profile_by_id(state, state.dashboard_loaded_profile_id)


def _selected_patch_refs(state):
    return [
        {"id": package.patch_id, "version": package.version}
        for package in _selected_dashboard_packages(state)
    ]


def _selected_dashboard_packages(state):
    return [
        state.patch_packages[index]
        for index in state.selected_patch_indexes
        if 0 <= index < len(state.patch_packages)
    ]


def _require_dashboard_patches(state):
    if not _selected_dashboard_packages(state):
        state.message = "Select at least one patch package."
        return False
    return True


def _dashboard_source_label(state):
    if state.dashboard_source_kind == SOURCE_VERSION:
        return f"native {state.dashboard_source_version}"
    if state.dashboard_source_kind == SOURCE_ARTIFACT:
        artifact = _dashboard_source_artifact(state)
        if artifact is None:
            return "downloaded artifact unavailable"
        return f"downloaded {artifact.version} {artifact.platform} {short_sha(artifact.sha256)}"
    return "latest native"


def _dashboard_source_artifact(state):
    if not state.native_artifacts:
        return None
    index = max(0, min(state.dashboard_source_artifact_index, len(state.native_artifacts) - 1))
    return state.native_artifacts[index]


def _run_dashboard_build(state):
    if not _require_dashboard_patches(state):
        return

    loaded_profile = _loaded_profile(state)
    if loaded_profile is not None:
        missing = _profile_missing_refs(state, loaded_profile)
        if missing:
            state.message = f"Loaded profile is invalid, missing {', '.join(missing)}"
            return

    packages = _selected_dashboard_packages(state)
    try:
        artifact = _dashboard_artifact_for_run(state)
        if artifact is None:
            return
        result, output = _run_quiet(apply_patch_packages_to_native, artifact, packages)
        state.message = f"Dashboard build complete: {result.output_path}"
    except Exception as exc:
        state.message = f"Dashboard build failed: {exc}"


def _dashboard_artifact_for_run(state):
    if state.dashboard_source_kind == SOURCE_ARTIFACT:
        artifact = _dashboard_source_artifact(state)
        if artifact is None:
            state.message = "Selected downloaded artifact is unavailable."
        return artifact

    requested_version = "latest"
    if state.dashboard_source_kind == SOURCE_VERSION:
        requested_version = state.dashboard_source_version
        if not requested_version:
            state.message = "Select a native version before running."
            return None

    path, output = _run_quiet(download_binary, requested_version)
    artifact = native_artifact_from_path(path)
    if artifact is None:
        state.refresh()
        artifact = native_artifact_from_path(path)
    if artifact is None:
        state.message = f"Downloaded binary was not found in the workspace: {path}"
    return artifact


def _activate_inspect(state):
    artifact = _selected_artifact(state)
    if artifact is None:
        return

    try:
        data = artifact.path.read_bytes()
        info = parse_bun_binary(data)
        entry = info.modules[info.entry_point_id].name if 0 <= info.entry_point_id < len(info.modules) else "unknown"
        state.message = (
            f"{artifact.version} {artifact.platform} {short_sha(artifact.sha256)}: "
            f"{info.platform}, {len(info.modules)} modules, entry {entry}"
        )
    except Exception as exc:
        state.message = f"Inspect failed: {exc}"


def _activate_extract(state):
    artifact = _selected_artifact(state)
    if artifact is None:
        return

    try:
        _run_quiet(extract_all, str(artifact.path), source_version=artifact.version)
        _, bundle_path = extraction_paths(artifact.version, artifact.platform, artifact.sha256)
        state.message = f"Extraction ready: {bundle_path}"
    except Exception as exc:
        state.message = f"Extract failed: {exc}"


def _activate_patch_source(state):
    artifact = _selected_artifact(state)
    if artifact is None:
        return
    if not state.patch_packages:
        state.message = f"No patch packages found under {workspace_root() / 'patches' / 'packages'}"
        return
    state.selected_source_index = state.selected_index
    state.selected_patch_indexes = []
    _set_mode(state, "patch-package")


def _activate_patch_packages(state):
    artifact = _source_artifact(state)
    if artifact is None:
        _set_mode(state, "patch-source")
        return
    if not state.selected_patch_indexes:
        state.message = "Select at least one patch package with Space."
        return

    packages = [state.patch_packages[index] for index in state.selected_patch_indexes]
    try:
        result, output = _run_quiet(apply_patch_packages_to_native, artifact, packages)
        state.message = f"Patched binary: {result.output_path}"
        _set_mode(state, "patch-source")
    except Exception as exc:
        state.message = f"Patch failed: {exc}"


def _toggle_patch(state):
    if not state.patch_packages:
        return
    index = state.selected_index
    if index in state.selected_patch_indexes:
        state.selected_patch_indexes.remove(index)
    else:
        state.selected_patch_indexes.append(index)
        state.selected_patch_indexes.sort()


def _go_back(state):
    if state.mode == "dashboard":
        if state.dashboard_delete_confirm_id:
            state.dashboard_delete_confirm_id = ""
            state.message = "Delete cancelled."
            return
        if state.dashboard_step > 0:
            state.dashboard_step -= 1
            state.selected_index = 0
    elif state.mode == "patch-package":
        _set_mode(state, "patch-source")


def _set_mode(state, mode):
    state.mode = mode
    state.selected_index = 0


def _move_tab(state, offset):
    active = _active_tab(state)
    current = TABS.index(active)
    next_index = (current + offset) % len(TABS)
    _set_mode(state, TAB_MODES[next_index])


def _selected_artifact(state):
    if not state.native_artifacts:
        state.message = "No centralized native downloads found."
        return None
    return state.native_artifacts[state.selected_index]


def _source_artifact(state):
    if not state.native_artifacts:
        return None
    index = max(0, min(state.selected_source_index, len(state.native_artifacts) - 1))
    return state.native_artifacts[index]


def _format_native_artifact(artifact):
    size = _format_size(artifact.path)
    return f"{artifact.version}  {artifact.platform}  {short_sha(artifact.sha256)}  {size}  {artifact.path}"


def _format_size(path: Path):
    try:
        size = path.stat().st_size
    except OSError:
        return "unknown"
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    if size >= 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size} B"


def _run_quiet(func, *args, **kwargs):
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        result = func(*args, **kwargs)
    output = "\n".join(
        part.strip()
        for part in (stdout.getvalue(), stderr.getvalue())
        if part.strip()
    )
    return result, output
