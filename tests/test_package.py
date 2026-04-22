import importlib

import cc_extractor
from cc_extractor.extractor import extract_all


def test_package_exports_are_loaded_lazily(monkeypatch):
    cc_extractor.__dict__.pop("extract_all", None)
    import_calls = []

    def track_import(name, package=None):
        import_calls.append((name, package))
        return importlib.import_module(name, package)

    monkeypatch.setattr(cc_extractor, "import_module", track_import)

    assert cc_extractor.extract_all is extract_all
    assert import_calls == [(".extractor", "cc_extractor")]
