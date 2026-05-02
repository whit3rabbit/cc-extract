"""Backspace + text-input helpers for the dashboard and variants tabs.

``_handle_char_key`` and ``_variant_accepts_name_text`` deliberately stay in
:mod:`cc_extractor.tui` because the latter is monkey-patched by tests and the
former calls it; rebinding has to occur in the same module's globals.
"""

from .options import selected_dashboard_option, selected_variant_option


def dashboard_accepts_profile_text(state) -> bool:
    if state.mode != "dashboard" or state.dashboard_step != 2:
        return False
    option = selected_dashboard_option(state)
    return option is not None and option.kind == "profile-name"


def dashboard_backspace(state) -> bool:
    if not dashboard_accepts_profile_text(state):
        return False
    state.dashboard_profile_name = state.dashboard_profile_name[:-1]
    state.dashboard_delete_confirm_id = ""
    return True


def variant_accepts_text(state) -> bool:
    if state.mode not in {"variants", "first-run-setup"}:
        return False
    option = selected_variant_option(state)
    return option is not None and option.kind in {
        "variant-name",
        "variant-credential-env",
        "variant-model",
    }


def variant_append_text(state, char: str) -> None:
    option = selected_variant_option(state)
    if option is None:
        return
    if option.kind == "variant-name":
        state.variant_name += char
    elif option.kind == "variant-credential-env":
        state.variant_credential_env += char
    elif option.kind == "variant-model":
        key = str(option.value)
        state.variant_model_overrides[key] = state.variant_model_overrides.get(key, "") + char


def variant_backspace(state) -> bool:
    if not variant_accepts_text(state):
        return False
    option = selected_variant_option(state)
    if option.kind == "variant-name":
        state.variant_name = state.variant_name[:-1]
    elif option.kind == "variant-credential-env":
        state.variant_credential_env = state.variant_credential_env[:-1]
    elif option.kind == "variant-model":
        key = str(option.value)
        state.variant_model_overrides[key] = state.variant_model_overrides.get(key, "")[:-1]
    return True
