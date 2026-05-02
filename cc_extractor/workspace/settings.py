"""TUI settings persistence."""

import os
from typing import Dict, Optional

from .._utils import safe_read_json as _safe_read_json
from .paths import ensure_workspace, tui_settings_path, write_json


def load_tui_settings(root: Optional[os.PathLike] = None) -> Dict:
    settings = _safe_read_json(tui_settings_path(root))
    if settings.get("schemaVersion") != 1:
        return {}
    theme_id = settings.get("themeId")
    if theme_id is not None and not isinstance(theme_id, str):
        return {}
    setup_list = settings.get("setupList")
    if setup_list is not None:
        if not isinstance(setup_list, dict):
            return {}
        search_text = setup_list.get("searchText")
        provider_filter = setup_list.get("providerFilter")
        sort_key = setup_list.get("sortKey")
        if search_text is not None and not isinstance(search_text, str):
            return {}
        if provider_filter is not None and not isinstance(provider_filter, str):
            return {}
        if sort_key is not None and not isinstance(sort_key, str):
            return {}
    return settings


def save_tui_settings(settings: Dict, root: Optional[os.PathLike] = None) -> Dict:
    current = load_tui_settings(root)
    payload = {"schemaVersion": 1}
    theme_id = settings.get("themeId", current.get("themeId"))
    if theme_id is not None:
        if not isinstance(theme_id, str) or not theme_id:
            raise ValueError("TUI settings themeId must be a non-empty string")
        payload["themeId"] = theme_id
    setup_list = settings.get("setupList", current.get("setupList"))
    if setup_list is not None:
        if not isinstance(setup_list, dict):
            raise ValueError("TUI settings setupList must be an object")
        saved_setup_list = {}
        search_text = setup_list.get("searchText", "")
        provider_filter = setup_list.get("providerFilter", "all")
        sort_key = setup_list.get("sortKey", "name")
        if not isinstance(search_text, str):
            raise ValueError("TUI settings setupList.searchText must be a string")
        if not isinstance(provider_filter, str) or not provider_filter:
            raise ValueError("TUI settings setupList.providerFilter must be a non-empty string")
        if not isinstance(sort_key, str) or not sort_key:
            raise ValueError("TUI settings setupList.sortKey must be a non-empty string")
        saved_setup_list["searchText"] = search_text
        saved_setup_list["providerFilter"] = provider_filter
        saved_setup_list["sortKey"] = sort_key
        payload["setupList"] = saved_setup_list
    ensure_workspace(root)
    write_json(tui_settings_path(root), payload)
    return payload
