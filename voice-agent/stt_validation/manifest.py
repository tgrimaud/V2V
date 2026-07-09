import json
from dataclasses import dataclass
from pathlib import Path

from .quality import DEFAULT_QUALITY_THRESHOLD, FixtureCategory, FixtureSpec


@dataclass(frozen=True)
class FixtureManifest:
    quality_threshold: float
    expected_categories: list[FixtureCategory]
    specs: list[FixtureSpec]


def load_manifest(manifest_path: Path) -> FixtureManifest:
    """Load a QA fixture manifest; audio paths are resolved relative to it."""
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    base_dir = manifest_path.parent
    expected = [FixtureCategory(value) for value in data.get("categories", [])]
    specs = [_parse_spec(entry, base_dir) for entry in data.get("fixtures", [])]
    threshold = float(data.get("quality_threshold", DEFAULT_QUALITY_THRESHOLD))
    return FixtureManifest(threshold, expected, specs)


def _parse_spec(entry: dict, base_dir: Path) -> FixtureSpec:
    return FixtureSpec(
        name=entry["name"],
        category=FixtureCategory(entry["category"]),
        audio_path=(base_dir / entry["audio"]).resolve(),
        reference=entry.get("reference"),
        expect_usable=bool(entry.get("expect_usable", True)),
    )
