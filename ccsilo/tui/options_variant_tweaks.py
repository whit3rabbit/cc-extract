"""Setup creation tweak selector helpers."""

from ..patches._registry import GROUP_ORDER
from ..variant_tweaks import (
    CURATED_TWEAK_IDS,
    DEFAULT_TWEAK_IDS,
    ENV_TWEAK_IDS,
    GATEWAY_MODEL_DISCOVERY_TWEAK_ID,
    default_tweak_ids_for_provider,
)
from ._const import ARCHITECT_MODE_TWEAK_ID
from .options_tweaks import tweak_meta
from .options_variant_state import selected_variant_provider

__all__ = [
    "variant_tweak_ids",
    "variant_setup_tweak_ids",
    "variant_tweak_groups",
    "group_setup_tweak_ids",
    "variant_tweak_selector_rows",
    "variant_tweak_selector_labels",
    "variant_tweak_selected_label_index",
    "_unique_ordered",
]

def variant_tweak_ids(state):
    provider = selected_variant_provider(state)
    recommended_ids = default_tweak_ids_for_provider(provider.get("key") if provider else None)
    if state.tweak_filter != "recommended":
        return list(CURATED_TWEAK_IDS)
    ids = list(recommended_ids)
    if state.variant_model_proxy == "architect" and GATEWAY_MODEL_DISCOVERY_TWEAK_ID in state.selected_variant_tweaks:
        ids.append(GATEWAY_MODEL_DISCOVERY_TWEAK_ID)
    return _unique_ordered(ids)

def variant_setup_tweak_ids(state):
    return [
        tweak_id for tweak_id in variant_tweak_ids(state)
        if tweak_id != ARCHITECT_MODE_TWEAK_ID
    ]

def variant_tweak_groups(state):
    provider = selected_variant_provider(state)
    recommended_ids = default_tweak_ids_for_provider(provider.get("key") if provider else None)
    return group_setup_tweak_ids(variant_setup_tweak_ids(state), recommended_ids)

def group_setup_tweak_ids(tweak_ids, recommended_ids):
    visible_ids = _unique_ordered(str(tweak_id) for tweak_id in tweak_ids)
    recommended = _unique_ordered(str(tweak_id) for tweak_id in recommended_ids)
    used = set()
    groups = []

    default_ids = [tweak_id for tweak_id in DEFAULT_TWEAK_IDS if tweak_id in visible_ids]
    if default_ids:
        groups.append(("Recommended defaults", default_ids))
        used.update(default_ids)

    provider_ids = [
        tweak_id
        for tweak_id in recommended
        if tweak_id in visible_ids and tweak_id not in used
    ]
    if provider_ids:
        groups.append(("Provider defaults", provider_ids))
        used.update(provider_ids)

    env_ids = [
        tweak_id
        for tweak_id in ENV_TWEAK_IDS
        if tweak_id in visible_ids and tweak_id not in used
    ]
    if env_ids:
        groups.append(("Environment variables", env_ids))
        used.update(env_ids)

    for group in GROUP_ORDER:
        group_ids = [
            tweak_id
            for tweak_id in visible_ids
            if tweak_id not in used and getattr(tweak_meta(tweak_id), "group", None) == group
        ]
        if group_ids:
            groups.append((group, group_ids))
            used.update(group_ids)

    remaining = [tweak_id for tweak_id in visible_ids if tweak_id not in used]
    if remaining:
        groups.append(("other", remaining))
    return groups

def variant_tweak_selector_rows(state):
    from .options_variant import variant_options

    options = variant_options(state)
    rows = []
    architect_indexes = [
        index for index, option in enumerate(options)
        if option.kind == "variant-architect-mode"
    ]
    if architect_indexes:
        rows.append(("Architect Mode", None))
        for index in architect_indexes:
            rows.append((options[index].label, index))

    model_proxy_indexes = [
        index for index, option in enumerate(options)
        if option.kind in {"variant-model-proxy", "variant-model-proxy-port"}
    ]
    if model_proxy_indexes:
        rows.append(("OAuth architect proxy", None))
        for index in model_proxy_indexes:
            rows.append((options[index].label, index))

    tweak_options = {
        str(option.value): (index, option)
        for index, option in enumerate(options)
        if option.kind == "variant-tweak"
    }
    for group, tweak_ids in variant_tweak_groups(state):
        group_rows = [
            (tweak_id, tweak_options[tweak_id])
            for tweak_id in tweak_ids
            if tweak_id in tweak_options
        ]
        if not group_rows:
            continue
        rows.append((f"-- {group} --", None))
        for _tweak_id, (index, option) in group_rows:
            rows.append((option.label, index))

    handled = set(architect_indexes) | set(model_proxy_indexes) | {index for index, _option in tweak_options.values()}
    for index, option in enumerate(options):
        if index not in handled:
            rows.append((option.label, index))
    return rows

def variant_tweak_selector_labels(state):
    return [label for label, _option_index in variant_tweak_selector_rows(state)]

def variant_tweak_selected_label_index(state):
    rows = variant_tweak_selector_rows(state)
    if not rows:
        return 0
    for row_index, (_label, option_index) in enumerate(rows):
        if option_index == state.selected_index:
            return row_index
    return 0

def _unique_ordered(tweak_ids):
    result = []
    for tweak_id in tweak_ids:
        if tweak_id not in result:
            result.append(tweak_id)
    return result
