#!/usr/bin/env python3
"""Build the progressively enhanced GitHub Pages measurement catalogue."""

from __future__ import annotations

import html
import json
import math
import shutil
from pathlib import Path
from typing import Any

try:  # Support both ``python tools/build_site.py`` and package imports in tests.
    from .catalogue import (
        CatalogueEntry,
        load_catalogue,
        parse_rfc3339_instant,
        write_csv,
    )
except ImportError:  # pragma: no cover - exercised by the script entry point.
    from catalogue import (
        CatalogueEntry,
        load_catalogue,
        parse_rfc3339_instant,
        write_csv,
    )


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "docs"
DATA = SITE / "data" / "measurements.json"
CSV = SITE / "data" / "measurements.csv"
PHOTOS = SITE / "photos"
TEMPLATE = SITE / "index.template.html"

TOKENS = (
    "{{MEASUREMENT_COUNT}}",
    "{{LOCATION_COUNT}}",
    "{{RESULT_COUNT}}",
    "{{MEASUREMENT_CARDS}}",
)
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _escape(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _title_case(value: Any, fallback: str = "Not specified") -> str:
    text = str(value).strip() if value is not None else ""
    return text.replace("_", " ").title() if text else fallback


def _level(value: Any) -> str:
    if value is None:
        return "—"
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"non-finite public sound level: {value!r}")
    return f"{number:.1f} dB"


def _duration(value: Any) -> str:
    seconds = float(value)
    if not math.isfinite(seconds):
        raise ValueError(f"non-finite measurement duration: {value!r}")
    total = max(0, math.floor(seconds + 0.5))
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def _display_date(value: Any) -> str:
    parsed = parse_rfc3339_instant(value).date()
    return f"{parsed.day} {MONTHS[parsed.month - 1]} {parsed.year}"


def _location_label(location: dict[str, Any]) -> str:
    parts = [location.get("city"), location.get("country")]
    return ", ".join(str(part) for part in parts if part) or "Location withheld"


def _attribution_label(attribution: dict[str, Any]) -> str:
    if attribution["mode"] == "anonymous":
        return "Anonymous"
    parts = [attribution.get("name"), attribution.get("organisation")]
    return " · ".join(str(part) for part in parts if part) or "Attributed contributor"


def _details_row(term: str, description: Any) -> str:
    return (
        "<div><dt>"
        f"{_escape(term)}"
        "</dt><dd>"
        f"{_escape(description)}"
        "</dd></div>"
    )


def _static_card(entry: CatalogueEntry) -> str:
    item = entry.public
    title = item["title"]
    public_id = item["id"]
    completed_at = item["completedAt"]
    location = item["location"]
    location_label = _location_label(location)
    levels = item["levels"]
    calibration = item["calibration"]
    calibration_label = _title_case(
        calibration.get("method") or calibration.get("status")
    )
    environment_label = (
        f"{_title_case(item['environmentGroup'])} · "
        f"{_title_case(item['environmentType'])}"
    )
    search = " ".join(
        str(value)
        for value in (
            title,
            public_id,
            item["environmentGroup"],
            item["environmentType"],
            location_label,
        )
    ).lower()

    if item["photo"]:
        photo = (
            '<div class="photo-wrap">'
            '<img class="measurement-photo" '
            f'alt="{_escape(f"Public photograph for {title}")}" '
            'loading="lazy" '
            f'src="{_escape(item["photo"])}">'
            "</div>"
        )
    else:
        photo = ""

    details = "\n".join(
        (
            _details_row("Environment", environment_label),
            _details_row("LAFmin", _level(levels.get("lafmin"))),
            _details_row("LCeq", _level(levels.get("lceq"))),
            _details_row("LZeq", _level(levels.get("lzeq"))),
            _details_row("Calibration", calibration_label),
            _details_row("Quality", _title_case(item["quality"])),
            _details_row("Contributor", _attribution_label(item["attribution"])),
            _details_row("Licence", str(item["license"]).replace("-", " ")),
        )
    )
    notes = item.get("notes")
    notes_markup = (
        f'<p class="notes">{_escape(notes)}</p>'
        if notes
        else '<p class="notes" hidden></p>'
    )

    return f"""<article class="measurement-card" data-measurement-id="{_escape(public_id)}" data-search="{_escape(search)}">
  {photo}
  <div class="card-body">
    <div class="card-kicker"><span class="environment-pill">{_escape(_title_case(item["environmentType"]))}</span><time datetime="{_escape(completed_at)}">{_escape(_display_date(completed_at))}</time></div>
    <h3>{_escape(title)}</h3>
    <p class="location">{_escape(location_label)}</p>
    <dl class="levels">
      <div><dt>LAeq</dt><dd class="laeq">{_escape(_level(levels["laeq"]))}</dd></div>
      <div><dt>LAFmax</dt><dd class="lafmax">{_escape(_level(levels["lafmax"]))}</dd></div>
      <div><dt>LCpeak</dt><dd class="lcpeak">{_escape(_level(levels.get("lcpeak")))}</dd></div>
      <div><dt>Duration</dt><dd class="duration">{_escape(_duration(item["durationSeconds"]))}</dd></div>
    </dl>
    <details>
      <summary>Measurement details</summary>
      <dl class="details-list">
{details}
      </dl>
      {notes_markup}
    </details>
    <div class="card-footer"><span class="measurement-id">{_escape(public_id)}</span><a class="record-link" href="{_escape(item["recordUrl"])}" aria-label="{_escape(f"Open public record for {title}")}">Open public record <span aria-hidden="true">↗</span></a></div>
  </div>
</article>"""


def _render_index(template_text: str, entries: list[CatalogueEntry]) -> str:
    for token in TOKENS:
        count = template_text.count(token)
        if count != 1:
            raise ValueError(f"template must contain {token} exactly once; found {count}")

    measurement_count = len(entries)
    location_count = sum(
        bool(entry.public["location"].get("city") or entry.public["location"].get("country"))
        for entry in entries
    )
    cards = "\n".join(_static_card(entry) for entry in entries)
    if not cards:
        cards = '<p class="empty-state">No public measurements are available yet.</p>'
    result_count = f"{measurement_count} {'result' if measurement_count == 1 else 'results'}"
    replacements = {
        "{{MEASUREMENT_COUNT}}": str(measurement_count),
        "{{LOCATION_COUNT}}": str(location_count),
        "{{RESULT_COUNT}}": result_count,
        "{{MEASUREMENT_CARDS}}": cards,
    }
    for token, replacement in replacements.items():
        template_text = template_text.replace(token, replacement)
    return template_text


def _copy_photos(entries: list[CatalogueEntry], photos: Path) -> None:
    if photos.exists():
        shutil.rmtree(photos)
    photos.mkdir(parents=True)
    for entry in sorted(entries, key=lambda value: value.public_id):
        if entry.photo_source is None or entry.photo_url is None:
            continue
        shutil.copyfile(entry.photo_source, photos / Path(entry.photo_url).name)


def build_site(
    root: Path | str | None = None,
    site: Path | str | None = None,
    template: Path | str | None = None,
) -> list[CatalogueEntry]:
    """Generate static HTML plus JSON, CSV, and photo artefacts from one load."""

    root_path = Path(root) if root is not None else ROOT
    site_path = Path(site) if site is not None else root_path / "docs"
    template_path = Path(template) if template is not None else site_path / "index.template.html"
    entries = load_catalogue(root_path)
    rendered_index = _render_index(template_path.read_text(encoding="utf-8"), entries)

    data = site_path / "data"
    photos = site_path / "photos"
    data.mkdir(parents=True, exist_ok=True)
    _copy_photos(entries, photos)
    (data / "measurements.json").write_text(
        json.dumps(
            {"measurements": [entry.public for entry in entries]},
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    write_csv(entries, data / "measurements.csv")
    (site_path / "index.html").write_text(rendered_index, encoding="utf-8")
    return entries


def main() -> None:
    entries = build_site()
    print(f"Built catalogue site for {len(entries)} measurements")


if __name__ == "__main__":
    main()
