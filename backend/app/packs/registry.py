from pathlib import Path

import yaml

from app.packs.contract import JourneyPackManifest
from app.packs.validator import PackViolation, validate_manifest
from app.schemas.enums import JourneyType

MANIFESTS_DIR = Path(__file__).parent / "manifests"


class PackRegistry:
    def __init__(self, manifests_dir: Path = MANIFESTS_DIR):
        self.manifests_dir = manifests_dir
        self._cache: dict[str, JourneyPackManifest] = {}
        self.load_all()

    def load_all(self):
        self._cache.clear()
        if not self.manifests_dir.exists():
            return
        for yaml_file in self.manifests_dir.glob("*.yaml"):
            with open(yaml_file, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            manifest = JourneyPackManifest.model_validate(data)
            self._cache[manifest.metadata.journey_type.value] = manifest

    def get_pack(self, journey_type: JourneyType | str) -> JourneyPackManifest | None:
        key = journey_type.value if isinstance(journey_type, JourneyType) else str(journey_type)
        return self._cache.get(key)

    def list_packs(self) -> list[JourneyPackManifest]:
        ordered = []
        for jtype in JourneyType:
            if jtype.value in self._cache:
                ordered.append(self._cache[jtype.value])
        for manifest in self._cache.values():
            if manifest not in ordered:
                ordered.append(manifest)
        return ordered

    def validate_all_packs(self) -> dict[str, list[PackViolation]]:
        results = {}
        for jtype, manifest in self._cache.items():
            violations = validate_manifest(manifest)
            if violations:
                results[jtype] = violations
        return results


pack_registry = PackRegistry()
