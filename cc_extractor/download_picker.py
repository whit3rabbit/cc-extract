"""Interactive version picker with TUI and text fallback."""

import sys
from dataclasses import dataclass, field
from typing import List, Optional

PROMPT_PAGE_SIZE = 20
LIST_PAGE_STEP = 10


def select_version(versions, latest_version=None, title="Select Claude Code download"):
    if not versions:
        raise RuntimeError("No Claude Code downloads were found")

    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise RuntimeError(
            "Interactive version selection requires a TTY. Pass --latest or specify a version."
        )

    try:
        from ratatui_py import App, Color, KeyCode, List as TuiList, Paragraph, Style
    except (ImportError, OSError, RuntimeError) as exc:
        print(
            f"[*] ratatui is unavailable ({exc}). Falling back to a text prompt.",
            file=sys.stderr,
        )
        return _select_with_prompt(versions, latest_version, title)

    state = _PickerState(
        versions=list(versions),
        latest_version=latest_version,
        title=title,
    )
    highlight_style = Style(fg=Color.Black, bg=Color.LightCyan).bold()

    def render(term, picker_state):
        width, height = term.size()
        header_height = min(4, height)
        footer_height = min(4, max(0, height - header_height - 1))
        list_height = max(1, height - header_height - footer_height)
        footer_top = header_height + list_height

        header = Paragraph.from_text(
            "\n".join(
                [
                    picker_state.title,
                    "Latest: {0}".format(picker_state.latest_version or "unknown"),
                    "Type to filter, Enter to download, Esc to cancel.",
                ]
            )
        )
        header.set_block_title("Downloads", True)
        header.set_wrap(True)
        term.draw_paragraph(header, (0, 0, width, header_height))

        if picker_state.filtered_versions:
            version_list = TuiList()
            for version in picker_state.filtered_versions:
                version_list.append_item(_display_label(version, picker_state.latest_version))
            version_list.set_block_title(
                "Versions ({0})".format(len(picker_state.filtered_versions)),
                True,
            )
            version_list.set_highlight_symbol("> ")
            version_list.set_highlight_style(highlight_style)
            version_list.set_selected(picker_state.selected_index)
            version_list.set_scroll_offset(
                max(0, picker_state.selected_index - max(0, list_height // 2))
            )
            term.draw_list(version_list, (0, header_height, width, list_height))
        else:
            empty = Paragraph.from_text("No versions match the current filter.")
            empty.set_block_title("Versions (0)", True)
            empty.set_wrap(True)
            term.draw_paragraph(empty, (0, header_height, width, list_height))

        if footer_top < height:
            footer = Paragraph.from_text(
                "\n".join(
                    [
                        "Filter: {0}".format(picker_state.filter_text or "(none)"),
                        "Selection: {0}".format(picker_state.current_version() or "none"),
                        "Keys: Up/Down, PageUp/PageDown, Home/End, Backspace.",
                    ]
                )
            )
            footer.set_block_title("Search", True)
            footer.set_wrap(True)
            term.draw_paragraph(footer, (0, footer_top, width, height - footer_top))

    def on_event(term, event, picker_state):
        if event.get("kind") != "key":
            return True

        code = event.get("code")
        char_code = event.get("ch") or 0

        if code == int(KeyCode.Up):
            picker_state.move(-1)
        elif code == int(KeyCode.Down):
            picker_state.move(1)
        elif code == int(KeyCode.PageUp):
            picker_state.move(-LIST_PAGE_STEP)
        elif code == int(KeyCode.PageDown):
            picker_state.move(LIST_PAGE_STEP)
        elif code == int(KeyCode.Home):
            picker_state.move_to_start()
        elif code == int(KeyCode.End):
            picker_state.move_to_end()
        elif code == int(KeyCode.Backspace):
            picker_state.set_filter(picker_state.filter_text[:-1])
        elif code == int(KeyCode.Enter):
            picker_state.selected_version = picker_state.current_version()
            return picker_state.selected_version is None
        elif code == int(KeyCode.Esc):
            picker_state.cancelled = True
            return False
        elif code == int(KeyCode.Char) and char_code:
            char = chr(char_code)
            if char.isprintable() and char not in "\r\n\t":
                picker_state.set_filter(picker_state.filter_text + char)

        return True

    app = App(render=render, on_event=on_event, tick_ms=100, clear_each_frame=True)
    app.run(state)

    if state.cancelled:
        raise RuntimeError("Download selection cancelled")
    if state.selected_version:
        return state.selected_version
    raise RuntimeError("No version was selected")


@dataclass
class _PickerState:
    versions: List[str]
    latest_version: Optional[str]
    title: str
    filter_text: str = ""
    filtered_versions: List[str] = field(default_factory=list)
    selected_index: int = 0
    selected_version: Optional[str] = None
    cancelled: bool = False

    def __post_init__(self):
        self.filtered_versions = list(self.versions)
        if self.latest_version in self.filtered_versions:
            self.selected_index = self.filtered_versions.index(self.latest_version)

    def current_version(self):
        if not self.filtered_versions:
            return None
        return self.filtered_versions[self.selected_index]

    def move(self, offset):
        if not self.filtered_versions:
            self.selected_index = 0
            return
        self.selected_index = max(
            0,
            min(self.selected_index + offset, len(self.filtered_versions) - 1),
        )

    def move_to_start(self):
        if self.filtered_versions:
            self.selected_index = 0

    def move_to_end(self):
        if self.filtered_versions:
            self.selected_index = len(self.filtered_versions) - 1

    def set_filter(self, filter_text):
        current = self.current_version()
        self.filter_text = filter_text
        lowered = filter_text.lower()
        self.filtered_versions = [
            version for version in self.versions if lowered in version.lower()
        ]
        if not self.filtered_versions:
            self.selected_index = 0
            return
        if current in self.filtered_versions:
            self.selected_index = self.filtered_versions.index(current)
        elif self.latest_version in self.filtered_versions:
            self.selected_index = self.filtered_versions.index(self.latest_version)
        else:
            self.selected_index = 0


def _display_label(version, latest_version):
    if version == latest_version:
        return f"{version} (latest)"
    return version


def _filter_versions(versions, filter_text):
    lowered = filter_text.lower()
    return [version for version in versions if lowered in version.lower()]


def _select_with_prompt(versions, latest_version, title):
    filter_text = ""

    while True:
        matches = _filter_versions(versions, filter_text)
        print(title)
        print("Latest: {0}".format(latest_version or "unknown"))
        print("Filter: {0}".format(filter_text or "(none)"))

        if matches:
            visible_matches = matches[:PROMPT_PAGE_SIZE]
            for index, version in enumerate(visible_matches, start=1):
                print("{0}. {1}".format(index, _display_label(version, latest_version)))
            if len(matches) > PROMPT_PAGE_SIZE:
                remaining = len(matches) - PROMPT_PAGE_SIZE
                print("... {0} more matches, type a narrower filter.".format(remaining))
        else:
            visible_matches = []
            print("No versions match the current filter.")

        response = input(
            "Choose number, type filter text, press Enter for latest, or q to cancel: "
        ).strip()

        if not response:
            if latest_version:
                return latest_version
            if visible_matches:
                return visible_matches[0]
            continue

        if response.lower() in {"q", "quit", "exit"}:
            raise RuntimeError("Download selection cancelled")

        if response.isdigit():
            index = int(response) - 1
            if 0 <= index < len(visible_matches):
                return visible_matches[index]
            print("[!] Selection out of range.", file=sys.stderr)
            continue

        filter_text = response
        print()
