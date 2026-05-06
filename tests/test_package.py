import importlib
import importlib.metadata as metadata

import ccsilo
from ccsilo.extractor import extract_all


def test_package_exports_are_loaded_lazily(monkeypatch):
    ccsilo.__dict__.pop("extract_all", None)
    import_calls = []

    def track_import(name, package=None):
        import_calls.append((name, package))
        return importlib.import_module(name, package)

    monkeypatch.setattr(ccsilo, "import_module", track_import)

    assert ccsilo.extract_all is extract_all
    assert import_calls == [(".extractor", "ccsilo")]


def test_package_metadata_has_publish_urls():
    meta = metadata.metadata("ccsilo")

    assert meta["Name"] == "ccsilo"
    project_urls = meta.get_all("Project-URL")
    assert "Repository, https://github.com/whit3rabbit/ccsilo" in project_urls
