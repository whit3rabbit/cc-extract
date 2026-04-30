import json

import pytest

from tools import extract_prompt_versions


def build_prompt():
    return {
        "name": "Test Prompt",
        "id": "test-prompt",
        "description": "A test prompt.",
        "pieces": ["Hello ${", "}"],
        "identifiers": [0],
        "identifierMap": {"0": "NAME"},
        "version": "1.2.3",
    }


def test_prompt_output_path_uses_prompts_version_json(tmp_path):
    assert extract_prompt_versions.prompt_output_path(tmp_path / "prompts", "1.2.3") == (
        tmp_path / "prompts" / "1.2.3.json"
    )


def test_validate_prompt_data_accepts_tweakcc_shape():
    extract_prompt_versions.validate_prompt_data(
        {"version": "1.2.3", "prompts": [build_prompt()]},
        "1.2.3",
    )


def test_validate_prompt_data_rejects_identifier_piece_mismatch():
    prompt = build_prompt()
    prompt["pieces"] = ["Hello"]

    with pytest.raises(ValueError, match="pieces length"):
        extract_prompt_versions.validate_prompt_data(
            {"version": "1.2.3", "prompts": [prompt]},
            "1.2.3",
        )


def test_write_validated_prompt_data_round_trips_json(tmp_path):
    output_path = tmp_path / "prompts" / "1.2.3.json"
    data = {"version": "1.2.3", "prompts": [build_prompt()]}

    extract_prompt_versions.write_validated_prompt_data(data, output_path, "1.2.3")

    assert json.loads(output_path.read_text(encoding="utf-8")) == data


def test_local_versions_discovers_downloaded_binaries(tmp_path):
    (tmp_path / "2.1.9").mkdir()
    (tmp_path / "2.1.9" / "claude").write_text("", encoding="utf-8")
    (tmp_path / "2.1.10").mkdir()
    (tmp_path / "2.1.10" / "claude").write_text("", encoding="utf-8")

    assert extract_prompt_versions.local_versions(tmp_path) == ["2.1.10", "2.1.9"]


def test_sort_versions_filters_non_version_markers():
    assert extract_prompt_versions.sort_versions(["plugins", "2.1.10", "1.0.1"]) == [
        "2.1.10",
        "1.0.1",
    ]
