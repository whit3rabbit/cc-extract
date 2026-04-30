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
    return settings


def save_tui_settings(settings: Dict, root: Optional[os.PathLike] = None) -> Dict:
    payload = {"schemaVersion": 1}
    theme_id = settings.get("themeId")
    if theme_id is not None:
        if not isinstance(theme_id, str) or not theme_id:
            raise ValueError("TUI settings themeId must be a non-empty string")
        payload["themeId"] = theme_id
    ensure_workspace(root)
    write_json(tui_settings_path(root), payload)
    return payload
