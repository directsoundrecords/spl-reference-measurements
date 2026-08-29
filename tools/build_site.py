#!/usr/bin/env python3
"""Build the privacy-safe data bundle used by the GitHub Pages catalogue."""

from __future__ import annotations

import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "docs"
DATA = SITE / "data" / "measurements.json"
PHOTOS = SITE / "photos"


def clean(value):
    return value if value not in (None, "") else None


def measurement_record(path: Path) -> dict:
    source = json.loads(path.read_text(encoding="utf-8"))
    identity = source["identity"]
    measurement = source["measurement"]
    levels = source["sound_level"]
    location = source["public_location"]
    environment = source["environment"]
    attribution = source["attribution"]
    photo = source.get("photo", {})
    public_id = identity["public_measurement_id"]

    photo_url = None
    if photo.get("included") and photo.get("filename"):
        photo_source = path.parent / photo["filename"]
        if photo_source.is_file():
            suffix = photo_source.suffix.lower() or ".jpg"
            photo_name = f"{public_id}{suffix}"
            shutil.copyfile(photo_source, PHOTOS / photo_name)
            photo_url = f"photos/{photo_name}"

    return {
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
        "recordUrl": f"https://github.com/directsoundrecords/spl-reference-measurements/blob/main/{path.relative_to(ROOT)}",
        "license": source["license"],
    }


def main() -> None:
    DATA.parent.mkdir(parents=True, exist_ok=True)
    if PHOTOS.exists():
        shutil.rmtree(PHOTOS)
    PHOTOS.mkdir(parents=True)

    paths = sorted(ROOT.glob("measurements/*/*/SPL-*/measurement.json"))
    records = sorted(
        (measurement_record(path) for path in paths),
        key=lambda item: item["completedAt"],
        reverse=True,
    )
    DATA.write_text(
        json.dumps({"measurements": records}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Built catalogue data for {len(records)} measurements")


if __name__ == "__main__":
    main()
