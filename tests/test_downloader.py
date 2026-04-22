import hashlib
from unittest.mock import MagicMock, patch

import pytest

from cc_extractor.downloader import (
    download_file,
    download_npm,
    fetch_text,
    get_platform_key,
    list_available_binary_versions,
    resolve_requested_version,
    verify_checksum,
)


class DummyProgressBar:
    def __init__(self):
        self.updates = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def update(self, amount):
        self.updates.append(amount)


class FakeHttpResponse:
    def __init__(self, data, headers=None):
        self._data = data
        self._offset = 0
        self.headers = headers or {}

    def read(self, size=-1):
        if size is None or size < 0:
            size = len(self._data) - self._offset
        chunk = self._data[self._offset:self._offset + size]
        self._offset += len(chunk)
        return chunk

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class TestGetPlatformKey:
    @patch("cc_extractor.downloader.platform.system", return_value="Darwin")
    @patch("cc_extractor.downloader.platform.machine", return_value="x86_64")
    def test_darwin_x64(self, mock_machine, mock_system):
        assert get_platform_key() == "darwin-x64"

    @patch("cc_extractor.downloader.platform.system", return_value="Darwin")
    @patch("cc_extractor.downloader.platform.machine", return_value="arm64")
    def test_darwin_arm64(self, mock_machine, mock_system):
        assert get_platform_key() == "darwin-arm64"

    @patch("cc_extractor.downloader.platform.system", return_value="Linux")
    @patch("cc_extractor.downloader.platform.machine", return_value="x86_64")
    @patch("cc_extractor.downloader._linux_uses_musl", return_value=False)
    def test_linux_x64_glibc(self, mock_musl, mock_machine, mock_system):
        assert get_platform_key() == "linux-x64"

    @patch("cc_extractor.downloader.platform.system", return_value="Linux")
    @patch("cc_extractor.downloader.platform.machine", return_value="x86_64")
    @patch("cc_extractor.downloader._linux_uses_musl", return_value=True)
    def test_linux_x64_musl(self, mock_musl, mock_machine, mock_system):
        assert get_platform_key() == "linux-x64-musl"

    @patch("cc_extractor.downloader.platform.system", return_value="Windows")
    @patch("cc_extractor.downloader.platform.machine", return_value="x86_64")
    def test_windows(self, mock_machine, mock_system):
        assert get_platform_key() == "win32-x64"

    @patch("cc_extractor.downloader.platform.system", return_value="FreeBSD")
    @patch("cc_extractor.downloader.platform.machine", return_value="x86_64")
    def test_unsupported_system(self, mock_machine, mock_system):
        with pytest.raises(ValueError, match="Unsupported system"):
            get_platform_key()

    @patch("cc_extractor.downloader.platform.system", return_value="Darwin")
    @patch("cc_extractor.downloader.platform.machine", return_value="i386")
    def test_unsupported_arch(self, mock_machine, mock_system):
        with pytest.raises(ValueError, match="Unsupported architecture"):
            get_platform_key()


class TestVerifyChecksum:
    def test_checksum_matches(self, tmp_path):
        file_path = tmp_path / "data.bin"
        file_path.write_bytes(b"test data")
        expected = hashlib.sha256(b"test data").hexdigest()

        assert verify_checksum(str(file_path), expected) is True

    def test_checksum_mismatch(self, tmp_path):
        file_path = tmp_path / "data.bin"
        file_path.write_bytes(b"test data")

        assert verify_checksum(str(file_path), "wronghash") is False


class TestFetchText:
    def test_fetch_text_success(self):
        response = FakeHttpResponse(b"v1.2.3\n")

        with patch("cc_extractor.downloader._open_url", return_value=response) as mock_open:
            assert fetch_text("http://example.com/version") == "v1.2.3"

        mock_open.assert_called_once_with("http://example.com/version")


class TestDownloadFile:
    def test_download_file_supports_basename_output(self, tmp_path, monkeypatch):
        response = FakeHttpResponse(b"hello", headers={"content-length": "5"})

        progress_instances = []

        def make_progress(**kwargs):
            progress = DummyProgressBar()
            progress_instances.append((progress, kwargs))
            return progress

        monkeypatch.chdir(tmp_path)

        with patch("cc_extractor.downloader._open_url", return_value=response), \
             patch("cc_extractor.downloader._get_tqdm", return_value=make_progress), \
             patch("cc_extractor.downloader.os.makedirs") as mock_makedirs:
            download_file("http://example.com/artifact", "artifact.bin")

        assert not mock_makedirs.called
        assert (tmp_path / "artifact.bin").read_bytes() == b"hello"
        progress_bar, kwargs = progress_instances[0]
        assert kwargs == {
            "total": 5,
            "unit": "B",
            "unit_scale": True,
            "desc": "artifact.bin",
        }
        assert progress_bar.updates == [5]


class TestListAvailableBinaryVersions:
    def test_list_available_binary_versions_paginates_and_sorts(self):
        pages = [
            {
                "prefixes": [
                    "claude-code-releases/2.1.2/",
                    "claude-code-releases/1.9.9/",
                ],
                "nextPageToken": "page-2",
            },
            {
                "prefixes": [
                    "claude-code-releases/2.1.10/",
                    "claude-code-releases/2.1.1/",
                ],
            },
        ]

        with patch("cc_extractor.downloader.fetch_json", side_effect=pages) as mock_fetch:
            assert list_available_binary_versions() == [
                "2.1.10",
                "2.1.2",
                "2.1.1",
                "1.9.9",
            ]

        urls = [call.args[0] for call in mock_fetch.call_args_list]
        assert "pageToken=page-2" in urls[1]


class TestResolveRequestedVersion:
    def test_resolve_requested_version_rejects_conflicting_args(self):
        with pytest.raises(ValueError, match="either a version or --latest"):
            resolve_requested_version("2.1.10", latest=True)

    def test_resolve_requested_version_latest_alias(self):
        with patch(
            "cc_extractor.downloader.fetch_latest_binary_version",
            return_value="2.1.116",
        ):
            assert resolve_requested_version("latest") == "2.1.116"

    def test_resolve_requested_version_uses_picker_for_binaries(self):
        with patch(
            "cc_extractor.downloader.list_available_binary_versions",
            return_value=["2.1.116", "2.1.115"],
        ), patch(
            "cc_extractor.downloader.fetch_latest_binary_version",
            return_value="2.1.116",
        ), patch(
            "cc_extractor.downloader._select_version_interactively",
            return_value="2.1.115",
        ) as mock_select:
            assert resolve_requested_version() == "2.1.115"

        mock_select.assert_called_once_with(["2.1.116", "2.1.115"], "2.1.116", False)

    def test_resolve_requested_version_uses_picker_for_npm(self):
        with patch(
            "cc_extractor.downloader.list_available_npm_versions",
            return_value=["2.1.116", "2.1.115"],
        ), patch(
            "cc_extractor.downloader.fetch_latest_npm_version",
            return_value="2.1.116",
        ), patch(
            "cc_extractor.downloader._select_version_interactively",
            return_value="2.1.115",
        ) as mock_select:
            assert resolve_requested_version(npm=True) == "2.1.115"

        mock_select.assert_called_once_with(["2.1.116", "2.1.115"], "2.1.116", True)


class TestDownloadNpm:
    @patch("cc_extractor.downloader.subprocess.run")
    @patch("cc_extractor.downloader.os.makedirs")
    def test_download_npm_success(self, mock_makedirs, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="\n@anthropic-ai/claude-code-1.2.3.tgz",
        )

        result = download_npm("1.2.3", "/tmp/npm")

        assert result == "/tmp/npm/@anthropic-ai/claude-code-1.2.3.tgz"

    @patch("cc_extractor.downloader.subprocess.run")
    @patch("cc_extractor.downloader.os.makedirs")
    def test_download_npm_failure(self, mock_makedirs, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stderr="npm error")

        with pytest.raises(RuntimeError, match="npm pack failed"):
            download_npm("latest", "/tmp/npm")

    @patch("cc_extractor.downloader.subprocess.run")
    @patch("cc_extractor.downloader.os.makedirs")
    def test_download_npm_missing_tarball_name(self, mock_makedirs, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="\n")

        with pytest.raises(RuntimeError, match="did not report an output tarball"):
            download_npm("latest", "/tmp/npm")
