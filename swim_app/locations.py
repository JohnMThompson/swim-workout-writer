from __future__ import annotations

from pathlib import Path

from flask import current_app, has_app_context


def get_canonical_locations() -> list[str]:
    path = _canonical_locations_path()
    if not path.exists():
        return []
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def save_canonical_location(location: str) -> bool:
    cleaned_location = location.strip()
    if not cleaned_location:
        return False

    path = _canonical_locations_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_locations = get_canonical_locations()
    normalized_existing = {_normalize_location(location) for location in existing_locations}
    if _normalize_location(cleaned_location) in normalized_existing:
        return False

    updated_locations = existing_locations + [cleaned_location]
    path.write_text("\n".join(updated_locations) + "\n", encoding="utf-8")
    return True


def _canonical_locations_path() -> Path:
    if has_app_context():
        configured_path = current_app.config.get("CANONICAL_LOCATIONS_FILE")
        if configured_path:
            return Path(configured_path)
    return Path(__file__).with_name("canonical_locations.txt")


def _normalize_location(location: str) -> str:
    return "".join(char for char in location.lower() if char.isalnum())
