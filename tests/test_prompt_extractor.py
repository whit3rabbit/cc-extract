import json

from tools import prompt_extractor


def test_slugify():
    assert prompt_extractor.slugify("Hello World") == "hello-world"
    assert prompt_extractor.slugify("Hello_World") == "hello-world"
    assert prompt_extractor.slugify("  Hello   World  ") == "hello-world"
    assert prompt_extractor.slugify("Hello! @World") == "hello-world"


def test_validate_input_filters_obvious_non_prompts():
    assert not prompt_extractor.validate_input("short")
    assert not prompt_extractor.validate_input("a" * 600)
    assert prompt_extractor.validate_input(
        "You are a helpful assistant. You should always follow instructions. " * 10
    )
    assert prompt_extractor.validate_input("This is the git status output...")
    assert prompt_extractor.validate_input(
        "Whenever you read a file, you should consider whether it matters."
    )


def test_extract_strings_uses_tweakcc_template_piece_shape(tmp_path):
    js_file = tmp_path / "cli.js"
    js_file.write_text(
        (
            "const prompt = `Hello ${toolName}, you are a helpful assistant. "
            "You should always follow instructions.\n"
            "        Use ${toolName} again. You must keep this as a prompt.`;"
        ),
        encoding="utf-8",
    )

    prompts = prompt_extractor.PromptExtractor().extract_strings(
        str(js_file),
        min_length=50,
        version="2.1.113",
    )

    assert len(prompts) == 1
    prompt = prompts[0]
    assert prompt["pieces"] == [
        "Hello ${",
        "}, you are a helpful assistant. You should always follow instructions.\n        Use ${",
        "} again. You must keep this as a prompt.",
    ]
    assert prompt["identifiers"] == [0, 0]
    assert prompt["identifierMap"] == {"0": ""}


def test_extract_prompts_returns_tweakcc_style_json(tmp_path):
    js_file = tmp_path / "cli.js"
    prompt_text = (
        'You are a helpful assistant. You should always follow instructions. '
        'This build is BUILD_TIME:\\"2025-12-09T19:43:43Z\\" and version 2.1.113. '
        'You must keep the output stable. Render escaped surrogate pairs like \\uD83D\\uDE00.'
    )
    js_file.write_text(
        f'const prompt = "{prompt_text}";',
        encoding="utf-8",
    )
    output_file = tmp_path / "prompts.json"

    status = prompt_extractor.main(
        [
            str(js_file),
            "--output",
            str(output_file),
            "--min-length",
            "40",
            "--version-hint",
            "2.1.113",
        ]
    )

    assert status == 0
    data = json.loads(output_file.read_text(encoding="utf-8"))
    assert data["version"] == "2.1.113"
    assert len(data["prompts"]) == 1
    prompt = data["prompts"][0]
    assert set(prompt) == {
        "name",
        "id",
        "description",
        "pieces",
        "identifiers",
        "identifierMap",
        "version",
    }
    assert prompt["pieces"] == [
        (
            'You are a helpful assistant. You should always follow instructions. '
            'This build is BUILD_TIME:"<<BUILD_TIME>>" and version <<CCVERSION>>. '
            'You must keep the output stable. Render escaped surrogate pairs like \U0001f600.'
        )
    ]


def test_regex_literals_do_not_create_false_prompts(tmp_path):
    js_file = tmp_path / "cli.js"
    js_file.write_text(
        (
            'const ignored = /^# "not a prompt"$/;\n'
            'const prompt = "You are a helpful assistant. '
            'You should always follow instructions. '
            'This literal should be extracted.";'
        ),
        encoding="utf-8",
    )

    prompts = prompt_extractor.PromptExtractor().extract_strings(
        str(js_file),
        min_length=40,
    )

    assert len(prompts) == 1
    assert prompts[0]["pieces"] == [
        (
            "You are a helpful assistant. "
            "You should always follow instructions. "
            "This literal should be extracted."
        )
    ]


def test_template_identifier_collection_matches_tweakcc_member_rules(tmp_path):
    js_file = tmp_path / "cli.js"
    prefix = "You should always answer clearly. You must keep context. " * 8
    js_file.write_text(
        (
            "const prompt = `"
            f"{prefix}"
            "${items.map(($_)=>{let a=d[$_.question],"
            "b=dC8($_)?Q[$_.question]?.textInputValue?.trim():void 0,"
            'c=[`- "${$_.question}"`];return c.join(`\\n`)}).join(`\\n`)}`;'
        ),
        encoding="utf-8",
    )

    prompts = prompt_extractor.PromptExtractor().extract_strings(
        str(js_file),
        min_length=20,
    )

    assert len(prompts) == 1
    assert prompts[0]["pieces"][4] == "[$_.question],"
    assert prompts[0]["pieces"][8] == "[$_.question]?."
    assert prompts[0]["pieces"][9] == "?."


def test_existing_metadata_is_preserved_for_matching_prompts(tmp_path):
    js_file = tmp_path / "cli.js"
    js_file.write_text(
        (
            "const prompt = `Hello ${toolName}, you are a helpful assistant. "
            "You should always follow instructions.\n"
            "        Use ${toolName} again. You must keep this as a prompt.`;"
        ),
        encoding="utf-8",
    )

    raw = prompt_extractor.PromptExtractor().extract_strings(str(js_file), min_length=50)
    existing = [
        {
            **{key: value for key, value in raw[0].items() if key not in {"start", "end"}},
            "name": "Tool Prompt",
            "id": "tool-prompt",
            "description": "A prompt with a tool variable.",
            "identifierMap": {"0": "TOOL_NAME"},
            "version": "2.1.112",
        }
    ]

    data = prompt_extractor.extract_prompts(
        str(js_file),
        min_length=50,
        version="2.1.113",
        existing_prompts=existing,
    )

    assert data["prompts"][0]["name"] == "Tool Prompt"
    assert data["prompts"][0]["id"] == "tool-prompt"
    assert data["prompts"][0]["identifierMap"] == {"0": "TOOL_NAME"}
    assert data["prompts"][0]["version"] == "2.1.112"


def test_existing_metadata_matches_decoded_template_escape_equivalents(tmp_path):
    js_file = tmp_path / "cli.js"
    js_file.write_text(
        (
            "const prompt = `Hello \\u2014 ${flag} "
            "You should always follow instructions. You must keep context.`;"
        ),
        encoding="utf-8",
    )

    data = prompt_extractor.extract_prompts(
        str(js_file),
        min_length=20,
        version="2.1.110",
        existing_prompts=[
            {
                "name": "Decoded Prompt",
                "id": "decoded-prompt",
                "description": "Uses cooked template text.",
                "pieces": [
                    "Hello \u2014 ${",
                    "} You should always follow instructions. You must keep context.",
                ],
                "identifiers": [0],
                "identifierMap": {"0": "FLAG"},
                "version": "2.1.109",
            }
        ],
    )

    assert data["prompts"][0]["id"] == "decoded-prompt"
    assert data["prompts"][0]["identifierMap"] == {"0": "FLAG"}
    assert data["prompts"][0]["pieces"] == [
        "Hello \\u2014 ${",
        "} You should always follow instructions. You must keep context.",
    ]


def test_existing_metadata_exact_match_wins_before_normalized_match(tmp_path):
    js_file = tmp_path / "cli.js"
    js_file.write_text(
        (
            "const prompt = `Hello \\u2014 ${flag} "
            "You should always follow instructions. You must keep context.`;"
        ),
        encoding="utf-8",
    )

    data = prompt_extractor.extract_prompts(
        str(js_file),
        min_length=20,
        version="2.1.110",
        existing_prompts=[
            {
                "name": "Raw Prompt",
                "id": "raw-prompt",
                "description": "Uses raw template source text.",
                "pieces": [
                    "Hello \\u2014 ${",
                    "} You should always follow instructions. You must keep context.",
                ],
                "identifiers": [0],
                "identifierMap": {"0": "RAW_FLAG"},
                "version": "2.1.110",
            },
            {
                "name": "Decoded Prompt",
                "id": "decoded-prompt",
                "description": "Uses cooked template text.",
                "pieces": [
                    "Hello \u2014 ${",
                    "} You should always follow instructions. You must keep context.",
                ],
                "identifiers": [0],
                "identifierMap": {"0": "DECODED_FLAG"},
                "version": "2.1.109",
            },
        ],
    )

    assert data["prompts"][0]["id"] == "raw-prompt"
    assert data["prompts"][0]["identifierMap"] == {"0": "RAW_FLAG"}


def test_nonmatching_existing_metadata_remains_unnamed(tmp_path):
    js_file = tmp_path / "cli.js"
    js_file.write_text(
        (
            "const prompt = `Different \\u2014 ${flag} "
            "You should always follow instructions. You must keep context.`;"
        ),
        encoding="utf-8",
    )

    data = prompt_extractor.extract_prompts(
        str(js_file),
        min_length=20,
        version="2.1.110",
        existing_prompts=[
            {
                "name": "Decoded Prompt",
                "id": "decoded-prompt",
                "description": "Uses cooked template text.",
                "pieces": [
                    "Hello \u2014 ${",
                    "} You should always follow instructions. You must keep context.",
                ],
                "identifiers": [0],
                "identifierMap": {"0": "FLAG"},
                "version": "2.1.109",
            }
        ],
    )

    extracted = next(
        prompt
        for prompt in data["prompts"]
        if prompt["pieces"][0].startswith("Different")
    )
    assert extracted["name"] == ""
    assert extracted["id"] == ""
    assert extracted["description"] == ""


def test_existing_catalog_recovers_short_prompt_literals(tmp_path):
    js_file = tmp_path / "cli.js"
    js_file.write_text(
        'const shortPrompt = "Your responses should be short and concise.";',
        encoding="utf-8",
    )

    data = prompt_extractor.extract_prompts(
        str(js_file),
        version="2.1.122",
        existing_prompts=[
            {
                "name": "System Prompt: Concise output",
                "id": "system-prompt-concise-output",
                "description": "Short response guidance.",
                "pieces": ["Your responses should be short and concise."],
                "identifiers": [],
                "identifierMap": {},
                "version": "2.1.53",
            }
        ],
    )

    assert data["prompts"] == [
        {
            "name": "System Prompt: Concise output",
            "id": "system-prompt-concise-output",
            "description": "Short response guidance.",
            "pieces": ["Your responses should be short and concise."],
            "identifiers": [],
            "identifierMap": {},
            "version": "2.1.53",
        }
    ]


def test_existing_catalog_recovers_short_template_prompts(tmp_path):
    js_file = tmp_path / "cli.js"
    js_file.write_text(
        'const reminder = `The user opened the file ${fileName} in the IDE.`;',
        encoding="utf-8",
    )

    data = prompt_extractor.extract_prompts(
        str(js_file),
        version="2.1.122",
        existing_prompts=[
            {
                "name": "System Reminder: File opened in IDE",
                "id": "system-reminder-file-opened-in-ide",
                "description": "IDE file-open reminder.",
                "pieces": ["The user opened the file ${", "} in the IDE."],
                "identifiers": [0],
                "identifierMap": {"0": "FILENAME"},
                "version": "2.1.18",
            }
        ],
    )

    assert data["prompts"][0]["id"] == "system-reminder-file-opened-in-ide"
    assert data["prompts"][0]["pieces"] == [
        "The user opened the file ${",
        "} in the IDE.",
    ]


def test_existing_catalog_recovers_short_template_with_escape_equivalence(tmp_path):
    js_file = tmp_path / "cli.js"
    js_file.write_text(
        'const reminder = `The user saw \\u2014 ${fileName} in the IDE.`;',
        encoding="utf-8",
    )

    data = prompt_extractor.extract_prompts(
        str(js_file),
        version="2.1.122",
        existing_prompts=[
            {
                "name": "System Reminder: IDE escape",
                "id": "system-reminder-ide-escape",
                "description": "IDE reminder with cooked escape text.",
                "pieces": ["The user saw \u2014 ${", "} in the IDE."],
                "identifiers": [0],
                "identifierMap": {"0": "FILENAME"},
                "version": "2.1.18",
            }
        ],
    )

    assert data["prompts"][0]["id"] == "system-reminder-ide-escape"
    assert data["prompts"][0]["pieces"] == [
        "The user saw \u2014 ${",
        "} in the IDE.",
    ]
