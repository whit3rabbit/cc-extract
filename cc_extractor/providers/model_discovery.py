"""Discover local model ids from OpenAI-compatible endpoints."""

import json
from typing import List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


MODEL_DISCOVERY_TIMEOUT = 2.0


def provider_models_url(base_url: str) -> str:
    """Return the model-list URL for a provider endpoint."""
    endpoint = (base_url or "").strip().rstrip("/")
    if not endpoint:
        raise RuntimeError("Endpoint is required to refresh models")
    if endpoint.endswith("/v1"):
        return f"{endpoint}/models"
    return f"{endpoint}/v1/models"


def fetch_provider_models(base_url: str, *, api_key: Optional[str] = None, timeout: float = MODEL_DISCOVERY_TIMEOUT) -> List[str]:
    url = provider_models_url(base_url)
    headers = {"User-Agent": "cc-extractor"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"Failed to refresh models from {url}: {exc}") from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Malformed model list from {url}: {exc}") from exc
    return parse_model_ids(payload)


def parse_model_ids(payload: object) -> List[str]:
    if isinstance(payload, dict):
        if "data" in payload:
            return _unique_model_ids(payload.get("data"))
        if "models" in payload:
            return _unique_model_ids(payload.get("models"))
    if isinstance(payload, list):
        return _unique_model_ids(payload)
    raise RuntimeError("Model list response did not contain data or models")


def _unique_model_ids(items: object) -> List[str]:
    if not isinstance(items, list):
        raise RuntimeError("Model list entries must be a list")
    seen = set()
    result = []
    for item in items:
        model_id = _model_id(item)
        if model_id and model_id not in seen:
            seen.add(model_id)
            result.append(model_id)
    return result


def _model_id(item: object) -> str:
    if isinstance(item, str):
        return item.strip()
    if not isinstance(item, dict):
        return ""
    for key in ("id", "key", "name"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""
