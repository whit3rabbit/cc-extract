"""Theme palettes and theme-related helpers."""

from dataclasses import dataclass

from ..workspace import load_tui_settings, save_tui_settings
from ._const import DEFAULT_THEME_ID, THEME_ORDER


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


def normalize_theme_id(theme_id):
    if theme_id in TUI_THEMES:
        return theme_id
    return DEFAULT_THEME_ID


def active_theme(state):
    return TUI_THEMES[normalize_theme_id(state.theme_id)]


def theme_name(theme_id):
    return TUI_THEMES[normalize_theme_id(theme_id)].name


def load_saved_theme_id():
    return normalize_theme_id(load_tui_settings().get("themeId"))


def cycle_theme(state):
    current = normalize_theme_id(state.theme_id)
    next_index = (THEME_ORDER.index(current) + 1) % len(THEME_ORDER)
    state.theme_id = THEME_ORDER[next_index]
    try:
        save_tui_settings({"themeId": state.theme_id})
        state.message = f"Theme saved: {theme_name(state.theme_id)}"
    except Exception as exc:
        state.message = f"Theme changed but save failed: {exc}"
