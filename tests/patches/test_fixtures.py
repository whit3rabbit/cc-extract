import pytest

from cc_extractor.download_index import load_download_index
from cc_extractor.patches._versions import resolve_range_to_version


pytestmark = pytest.mark.skipif(
    resolve_range_to_version(">=2.0.0,<3", index=load_download_index()) is None,
    reason="no Claude Code binary version available in download index",
)


def test_cli_js_real_returns_string(cli_js_real):
    version = resolve_range_to_version(">=2.0.0,<3", index=load_download_index())
    js = cli_js_real(version)
    assert isinstance(js, str)
    assert len(js) > 1000


def test_parse_js_accepts_valid(parse_js):
    parse_js("function x(){return 1;}")


def test_parse_js_rejects_invalid(parse_js):
    with pytest.raises(Exception):
        parse_js("function x(){return")
