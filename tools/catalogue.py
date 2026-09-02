#!/usr/bin/env python3
"""Canonical loading and public projections for the measurement catalogue."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


CSV_COLUMNS = (
    "public_measurement_id",
    "measurement_uuid",
    "date",
    "environment_group",
    "environment_type",
    "country",
    "region",
    "city",
    "location_visibility",
    "laeq_db_a",
    "lafmax_db_a",
    "duration_seconds",
    "quality_classification",
    "attribution_mode",
    "app_version",
    "record_path",
)


def clean(value: Any) -> Any:
    """Match the existing public JSON convention for absent scalar values."""

    return value if value not in (None, "") else None


def parse_rfc3339_instant(value: Any) -> datetime:
    """Parse a canonical timestamp as an aware UTC instant."""

    text = str(value)
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp must include a UTC offset: {value!r}")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class CatalogueEntry:
    """One canonical measurement and its privacy-safe catalogue projection."""

    source_path: Path
    relative_path: Path
    source: dict[str, Any]
    public: dict[str, Any]
    photo_source: Path | None
    photo_url: str | None

    @property
    def public_id(self) -> str:
        return str(self.public["id"])

    @property
    def completed_at(self) -> str:
        return str(self.public["completedAt"])

    def csv_row(self) -> dict[str, Any]:
        identity = self.source["identity"]
        measurement = self.source["measurement"]
        environment = self.source["environment"]
        location = self.source["public_location"]
        levels = self.source["sound_level"]

        return {
            "public_measurement_id": identity["public_measurement_id"],
            "measurement_uuid": identity["measurement_uuid"],
            "date": str(measurement["completed_at_utc"])[:10],
            "environment_group": environment["group_id"],
            "environment_type": environment["type_id"],
            "country": location.get("country_name"),
            "region": location.get("region"),
            "city": location.get("city"),
            "location_visibility": location["visibility"],
            "laeq_db_a": levels["laeq_db_a"],
            "lafmax_db_a": levels["lafmax_db_a"],
            "duration_seconds": measurement["duration_seconds"],
            "quality_classification": self.source["measurement_quality"]["classification"],
            "attribution_mode": self.source["attribution"]["mode"],
            "app_version": self.source["software"]["application_version"],
            "record_path": self.relative_path.as_posix(),
        }


def _photo_details(
    path: Path,
    public_id: str,
    declaration: dict[str, Any],
) -> tuple[Path | None, str | None]:
    if not declaration.get("included"):
        return None, None

    filename = declaration.get("filename")
    if not isinstance(filename, str) or not filename:
        raise ValueError(f"{path}: included photo has no filename")
    if Path(filename).name != filename:
        raise ValueError(f"{path}: photo filename must not contain a path")

    photo_source = path.parent / filename
    if not photo_source.is_file():
        raise FileNotFoundError(f"{path}: declared photo is missing: {photo_source}")

    suffix = photo_source.suffix.lower() or ".jpg"
    return photo_source, f"photos/{public_id}{suffix}"


def _entry(root: Path, path: Path) -> CatalogueEntry:
    source = json.loads(path.read_text(encoding="utf-8"))
    identity = source["identity"]
    measurement = source["measurement"]
    levels = source["sound_level"]
    location = source["public_location"]
    environment = source["environment"]
    attribution = source["attribution"]
    public_id = str(identity["public_measurement_id"])
    photo_source, photo_url = _photo_details(path, public_id, source.get("photo", {}))
    relative_path = path.relative_to(root)

    public = {
        "id": public_id,
        "title": measurement["title"],
        "completedAt": measurement["completed_at_utc"],
        "durationSeconds": measurement["duration_seconds"],
        "environmentGroup": environment["group_id"],
        "environmentType": environment["type_id"],
        "location": {
            "visibility": location["visibility"],
            "city": clean(location.get("city")),
            "country": clean(location.get("country_name")),
        },
        "levels": {
            "laeq": levels["laeq_db_a"],
            "lafmax": levels["lafmax_db_a"],
            "lafmin": clean(levels.get("lafmin_db_a")),
            "lcpeak": clean(levels.get("lcpeak_db_c")),
            "lceq": clean(levels.get("lceq_db_c")),
            "lzeq": clean(levels.get("lzeq_db_z")),
        },
        "calibration": source["calibration"],
        "quality": source["measurement_quality"]["classification"],
        "attribution": {
            "mode": attribution["mode"],
            "name": clean(attribution.get("display_name")),
            "organisation": clean(attribution.get("organisation")),
        },
        "notes": clean(source.get("notes")),
        "photo": photo_url,
        "recordUrl": (
            "https://github.com/directsoundrecords/spl-reference-measurements/blob/main/"
            f"{relative_path.as_posix()}"
        ),
        "license": source["license"],
    }
    return CatalogueEntry(
        source_path=path,
        relative_path=relative_path,
        source=source,
        public=public,
        photo_source=photo_source,
        photo_url=photo_url,
    )


def load_catalogue(root: Path | str) -> list[CatalogueEntry]:
    """Load canonical records once and return deterministic newest-first entries."""

    root = Path(root).resolve()
    paths = sorted(root.glob("measurements/*/*/SPL-*/measurement.json"))
    entries = [_entry(root, path) for path in paths]

    public_ids = [entry.public_id for entry in entries]
    if len(public_ids) != len(set(public_ids)):
        raise ValueError("duplicate public measurement ID")

    # A stable second sort preserves ascending public ID order when instants tie.
    entries.sort(key=lambda entry: entry.public_id)
    entries.sort(
        key=lambda entry: parse_rfc3339_instant(entry.completed_at),
        reverse=True,
    )
    return entries


def write_csv(entries: Iterable[CatalogueEntry], destination: Path | str) -> None:
    """Write the established discovery-index contract from canonical entries."""

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(entries, key=lambda entry: entry.public_id)
    with destination.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(entry.csv_row() for entry in ordered)
