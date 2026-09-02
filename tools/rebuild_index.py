#!/usr/bin/env python3
"""Build the CSV discovery index from canonical measurement records."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Sequence

try:  # Support both ``python tools/rebuild_index.py`` and package imports.
    from .catalogue import CatalogueEntry, load_catalogue, write_csv
except ImportError:  # pragma: no cover - exercised by the script entry point.
    from catalogue import CatalogueEntry, load_catalogue, write_csv


ROOT = Path(__file__).resolve().parents[1]


def rebuild_index(
    root: Path | str | None = None,
    destination: Path | str | None = None,
) -> list[CatalogueEntry]:
    root_path = Path(root) if root is not None else ROOT
    destination_path = (
        Path(destination)
        if destination is not None
        else root_path / "docs" / "data" / "measurements.csv"
    )
    entries = load_catalogue(root_path)
    write_csv(entries, destination_path)
    return entries


def main(argv: Sequence[str] | None = None) -> None:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) > 1:
        raise SystemExit("usage: rebuild_index.py [destination]")
    destination = Path(arguments[0]) if arguments else None
    rebuild_index(destination=destination)


if __name__ == "__main__":
    main()
