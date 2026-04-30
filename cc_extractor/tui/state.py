"""TuiState dataclass and refresh logic."""

from dataclasses import dataclass, field
from typing import Any, Dict, List

from ..download_index import download_versions, load_download_index
from ..variant_tweaks import DEFAULT_TWEAK_IDS
from ..variants import list_variant_providers, scan_variants
from ..variants.model import Variant
from ..workspace import (
    NativeArtifact,
    PatchPackage,
    PatchProfile,
    scan_extractions,
    scan_native_downloads,
    scan_npm_downloads,
    scan_patch_packages,
    scan_patch_profiles,
)
from ._const import DEFAULT_THEME_ID, SOURCE_LATEST
from .themes import normalize_theme_id


@dataclass
class TuiState:
    mode: str = "dashboard"
    selected_index: int = 0
    message: str = ""
    theme_id: str = DEFAULT_THEME_ID
    native_artifacts: List[NativeArtifact] = field(default_factory=list)
    patch_packages: List[PatchPackage] = field(default_factory=list)
    patch_profiles: List[PatchProfile] = field(default_factory=list)
    variants: List[Variant] = field(default_factory=list)
    variant_providers: List[Dict[str, Any]] = field(default_factory=list)
    download_index: dict = field(default_factory=dict)
    download_versions: List[str] = field(default_factory=list)
    selected_source_index: int = 0
    selected_patch_indexes: List[int] = field(default_factory=list)
    counts: str = ""
    dashboard_step: int = 0
    dashboard_source_kind: str = SOURCE_LATEST
    dashboard_source_version: str = ""
    dashboard_source_artifact_index: int = 0
    dashboard_profile_name: str = ""
    dashboard_loaded_profile_id: str = ""
    dashboard_delete_confirm_id: str = ""
    variant_step: int = 0
    variant_provider_index: int = 0
    variant_name: str = ""
    variant_credential_env: str = ""
    variant_model_overrides: Dict[str, str] = field(default_factory=dict)
    selected_variant_tweaks: List[str] = field(default_factory=lambda: list(DEFAULT_TWEAK_IDS))

    def refresh(self):
        self.theme_id = normalize_theme_id(self.theme_id)
        self.native_artifacts = scan_native_downloads()
        npm_count = len(scan_npm_downloads())
        extraction_count = len(scan_extractions())
        self.patch_packages = scan_patch_packages()
        self.patch_profiles = scan_patch_profiles()
        self.variants = scan_variants()
        self.variant_providers = list_variant_providers()
        self.download_index = load_download_index()
        self.download_versions = download_versions(self.download_index, "binary")
        self.counts = (
            f"Native: {len(self.native_artifacts)}  "
            f"NPM: {npm_count}  "
            f"Extractions: {extraction_count}  "
            f"Patch packages: {len(self.patch_packages)}  "
            f"Profiles: {len(self.patch_profiles)}  "
            f"Variants: {len(self.variants)}"
        )
        self.selected_patch_indexes = [
            index for index in self.selected_patch_indexes
            if 0 <= index < len(self.patch_packages)
        ]
        self.selected_index = self._clamp(self.selected_index, self.item_count())
        self.selected_source_index = self._clamp(self.selected_source_index, len(self.native_artifacts))
        self.dashboard_source_artifact_index = self._clamp(
            self.dashboard_source_artifact_index,
            len(self.native_artifacts),
        )
        self.variant_provider_index = self._clamp(
            self.variant_provider_index,
            len(self.variant_providers),
        )

    def item_count(self):
        # Local import avoids a circular module-load on package init.
        from .options import dashboard_options, variant_options

        if self.mode == "dashboard":
            return len(dashboard_options(self))
        if self.mode in {"inspect", "extract", "patch-source"}:
            return len(self.native_artifacts)
        if self.mode == "patch-package":
            return len(self.patch_packages)
        if self.mode == "variants":
            return len(variant_options(self))
        return 1

    def move(self, offset):
        count = self.item_count()
        if count < 1:
            self.selected_index = 0
            return
        self.selected_index = max(0, min(self.selected_index + offset, count - 1))

    def _clamp(self, value, count):
        if count < 1:
            return 0
        return max(0, min(value, count - 1))
