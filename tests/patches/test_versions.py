import pytest

from cc_extractor.patches._versions import (
    SemverRangeError,
    parse_version,
    version_in_range,
)


def test_parse_version_three_components():
    assert parse_version("2.1.123") == (2, 1, 123)


def test_parse_version_rejects_two_components():
    with pytest.raises(SemverRangeError):
        parse_version("2.1")


def test_parse_version_rejects_non_numeric():
    with pytest.raises(SemverRangeError):
        parse_version("2.0.x")


def test_version_in_range_simple_ge():
    assert version_in_range("2.0.40", ">=2.0.20") is True


def test_version_in_range_simple_lt():
    assert version_in_range("2.0.40", "<2.1.0") is True
    assert version_in_range("2.1.0", "<2.1.0") is False


def test_version_in_range_eq():
    assert version_in_range("2.0.40", "==2.0.40") is True
    assert version_in_range("2.0.41", "==2.0.40") is False


def test_version_in_range_and_clause():
    assert version_in_range("2.0.40", ">=2.0.20,<2.1") is True
    assert version_in_range("2.1.0", ">=2.0.20,<2.1") is False


def test_version_in_range_or_clause():
    expr = ">=2.0.20,<2.1 || >=2.1.0,<3"
    assert version_in_range("2.0.40", expr) is True
    assert version_in_range("2.1.123", expr) is True
    assert version_in_range("2.0.5", expr) is False
    assert version_in_range("3.0.0", expr) is False


def test_version_in_range_rejects_bad_comparator():
    with pytest.raises(SemverRangeError):
        version_in_range("2.0.40", "~=2.0.20")


def test_version_in_range_rejects_bad_version_in_range():
    with pytest.raises(SemverRangeError):
        version_in_range("2.0.40", ">=foo")
