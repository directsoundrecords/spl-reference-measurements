from __future__ import annotations

import copy
import csv
import html
import json
import re
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.build_site import build_site  # noqa: E402
from tools.catalogue import load_catalogue, parse_rfc3339_instant  # noqa: E402


TEMPLATE = REPOSITORY_ROOT / "docs" / "index.template.html"
CANONICAL_PATTERN = "measurements/*/*/SPL-*/measurement.json"
PRIVATE_FIELD = re.compile(
    r"(^|_)(latitude|longitude|coordinates?|gps|precise_address|project|project_id|project_name|project_title)($|_)",
    re.IGNORECASE,
)
REQUIRED_DISCOVERY_FIELDS = {
    "id",
    "title",
    "completedAt",
    "durationSeconds",
    "environmentGroup",
    "environmentType",
    "location",
    "levels",
    "calibration",
    "quality",
    "attribution",
    "notes",
    "photo",
    "recordUrl",
    "license",
}
REQUIRED_CSV_FIELDS = {
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
}
PUBLIC_SITE_URL = "https://directsoundrecords.github.io/spl-reference-measurements/"
CC_BY_4_0_URL = "https://creativecommons.org/licenses/by/4.0/"
REQUIRED_MEASURED_VARIABLES = {
    "LAeq",
    "LAFmax",
    "LAFmin",
    "LCpeak",
    "LCeq",
    "LZeq",
}


class CatalogueHTMLParser(HTMLParser):
    """Collect the generated, non-template catalogue content."""

    _void_elements = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
    _field_classes = {
        "environment-pill",
        "location",
        "laeq",
        "lafmax",
        "lcpeak",
        "duration",
        "measurement-id",
        "notes",
    }
    _summary_ids = {"measurement-count", "location-count", "result-count"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.cards: list[dict] = []
        self.links: list[str] = []
        self.summaries: dict[str, str] = {}
        self._template_depth = 0
        self._current_card: dict | None = None
        self._stack: list[tuple[str, str | None, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key: value or "" for key, value in attrs}
        classes = set(attributes.get("class", "").split())

        if tag == "template":
            self._template_depth += 1
        ignored = self._template_depth > 0

        if not ignored and tag == "a" and attributes.get("href"):
            self.links.append(attributes["href"])

        card_id = attributes.get("data-measurement-id")
        if not ignored and tag == "article" and card_id:
            self._current_card = {
                "id": card_id,
                "fields": {},
                "text": [],
                "tags": [],
                "record_href": None,
                "photo_src": None,
                "time_datetime": None,
            }

        card_target = None
        if self._current_card is not None and not ignored:
            self._current_card["tags"].append(tag)
            if tag == "h3":
                card_target = "title"
            else:
                card_target = next(
                    (name for name in self._field_classes if name in classes),
                    None,
                )
            if card_target is not None:
                self._current_card["fields"].setdefault(card_target, [])
            if tag == "a" and "record-link" in classes:
                self._current_card["record_href"] = attributes.get("href")
            if tag == "img" and "measurement-photo" in classes:
                self._current_card["photo_src"] = attributes.get("src")
            if tag == "time":
                self._current_card["time_datetime"] = attributes.get("datetime")

        summary_target = attributes.get("id")
        if summary_target not in self._summary_ids:
            summary_target = None

        if tag not in self._void_elements:
            self._stack.append((tag, card_target, summary_target))

    def handle_endtag(self, tag: str) -> None:
        if self._current_card is not None and tag == "article" and self._template_depth == 0:
            for key, parts in self._current_card["fields"].items():
                self._current_card["fields"][key] = "".join(parts).strip()
            self._current_card["text"] = " ".join(
                "".join(self._current_card["text"]).split()
            )
            self.cards.append(self._current_card)
            self._current_card = None

        for index in range(len(self._stack) - 1, -1, -1):
            if self._stack[index][0] == tag:
                del self._stack[index:]
                break

        if tag == "template":
            self._template_depth = max(0, self._template_depth - 1)

    def handle_data(self, data: str) -> None:
        if self._current_card is not None and self._template_depth == 0:
            self._current_card["text"].append(data)
            for _, card_target, _ in reversed(self._stack):
                if card_target is not None:
                    self._current_card["fields"][card_target].append(data)
                    break

        for _, _, summary_target in reversed(self._stack):
            if summary_target is not None:
                self.summaries[summary_target] = (
                    self.summaries.get(summary_target, "") + data
                ).strip()
                break


class JSONLDHTMLParser(HTMLParser):
    """Collect static ``application/ld+json`` script contents."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.scripts: list[str] = []
        self._current: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "script":
            return
        attributes = {key.casefold(): (value or "") for key, value in attrs}
        media_type = attributes.get("type", "").split(";", 1)[0].strip().casefold()
        if media_type == "application/ld+json":
            if attributes.get("src"):
                raise AssertionError("JSON-LD must be embedded statically, not loaded by src")
            self._current = []

    def handle_data(self, data: str) -> None:
        if self._current is not None:
            self._current.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._current is not None:
            self.scripts.append("".join(self._current))
            self._current = None


def canonical_records(root: Path) -> list[tuple[Path, dict]]:
    return [
        (path, json.loads(path.read_text(encoding="utf-8")))
        for path in sorted(root.glob(CANONICAL_PATTERN))
    ]


def discovery_ids(document: dict) -> list[str]:
    return [record["id"] for record in document["measurements"]]


def private_keys(value) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if PRIVATE_FIELD.search(key):
                keys.add(key)
            keys.update(private_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.update(private_keys(child))
    return keys


def nested_dicts(value):
    """Yield every object in a JSON-compatible tree."""

    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from nested_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from nested_dicts(child)


def has_schema_type(value: dict, expected: str) -> bool:
    declared = value.get("@type")
    return expected in (declared if isinstance(declared, list) else [declared])


def referenced_ids(value) -> set[str]:
    """Return JSON-LD identifiers from a reference, inline node, or list."""

    if isinstance(value, str):
        return {value}
    if isinstance(value, dict):
        identifier = value.get("@id")
        return {identifier} if isinstance(identifier, str) else set()
    if isinstance(value, list):
        result: set[str] = set()
        for child in value:
            result.update(referenced_ids(child))
        return result
    return set()


def assert_absolute_web_url(test: unittest.TestCase, value, label: str) -> None:
    test.assertIsInstance(value, str, f"{label} must be a URL string")
    parsed = urlparse(value)
    test.assertIn(
        parsed.scheme,
        {"http", "https"},
        f"{label} must be an absolute web URL",
    )
    test.assertTrue(parsed.netloc, f"{label} must include a hostname")


def tree_snapshot(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


class CatalogueBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.canonical = canonical_records(REPOSITORY_ROOT)
        cls.expected_by_id = {
            record["identity"]["public_measurement_id"]: (path, record)
            for path, record in cls.canonical
        }
        cls.expected_ids = set(cls.expected_by_id)
        if not cls.expected_ids:
            raise AssertionError("Catalogue tests require at least one canonical fixture")
        if not TEMPLATE.is_file():
            raise AssertionError(f"Missing catalogue template: {TEMPLATE}")

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.site = Path(self.temporary_directory.name) / "site"
        self.entries = build_site(
            root=REPOSITORY_ROOT,
            site=self.site,
            template=TEMPLATE,
        )

    def load_outputs(self) -> tuple[CatalogueHTMLParser, dict, list[dict]]:
        parser = CatalogueHTMLParser()
        parser.feed((self.site / "index.html").read_text(encoding="utf-8"))
        document = json.loads(
            (self.site / "data" / "measurements.json").read_text(encoding="utf-8")
        )
        with (self.site / "data" / "measurements.csv").open(
            encoding="utf-8", newline=""
        ) as handle:
            rows = list(csv.DictReader(handle))
        return parser, document, rows

    def load_json_ld(self, site: Path | None = None) -> list[dict]:
        index_html = ((site or self.site) / "index.html").read_text(encoding="utf-8")
        parser = JSONLDHTMLParser()
        parser.feed(index_html)
        self.assertTrue(
            parser.scripts,
            "Generated static HTML must embed application/ld+json metadata",
        )

        documents: list[dict] = []
        for index, script in enumerate(parser.scripts):
            with self.subTest(json_ld_script=index):
                self.assertTrue(script.strip(), "JSON-LD script must not be empty")
                try:
                    document = json.loads(script)
                except json.JSONDecodeError as error:
                    self.fail(f"JSON-LD script {index} is not valid JSON: {error}")
                self.assertIsInstance(document, dict)
                documents.append(document)
        return documents

    def test_html_json_and_csv_have_the_same_unique_canonical_records(self) -> None:
        parser, document, rows = self.load_outputs()
        html_ids = [card["id"] for card in parser.cards]
        json_ids = discovery_ids(document)
        csv_ids = [row["public_measurement_id"] for row in rows]
        entry_ids = [entry.public_id for entry in self.entries]
        expected_count = len(self.expected_ids)

        for name, ids in {
            "HTML": html_ids,
            "JSON": json_ids,
            "CSV": csv_ids,
            "entries": entry_ids,
        }.items():
            with self.subTest(format=name):
                self.assertEqual(len(ids), expected_count)
                self.assertEqual(len(ids), len(set(ids)))
                self.assertEqual(set(ids), self.expected_ids)

        expected_location_count = sum(
            bool(record["public_location"].get("city") or record["public_location"].get("country_name"))
            for _, record in self.canonical
        )
        self.assertEqual(parser.summaries["measurement-count"], str(expected_count))
        self.assertEqual(parser.summaries["location-count"], str(expected_location_count))
        expected_result = f"{expected_count} {'result' if expected_count == 1 else 'results'}"
        self.assertEqual(parser.summaries["result-count"], expected_result)
        self.assertIn("data/measurements.json", parser.links)
        self.assertIn("data/measurements.csv", parser.links)

    def test_static_json_ld_describes_the_catalogue_dataset_and_downloads(self) -> None:
        documents = self.load_json_ld()
        self.assertTrue(
            any(
                str(document.get("@context", "")).rstrip("/")
                == "https://schema.org"
                for document in documents
            ),
            "JSON-LD must declare the schema.org context",
        )

        nodes = [node for document in documents for node in nested_dicts(document)]
        typed = {
            schema_type: [node for node in nodes if has_schema_type(node, schema_type)]
            for schema_type in ("Organization", "DataCatalog", "Dataset", "DataDownload")
        }
        self.assertEqual(len(typed["Organization"]), 1)
        self.assertEqual(len(typed["DataCatalog"]), 1)
        self.assertEqual(len(typed["Dataset"]), 1)
        self.assertEqual(len(typed["DataDownload"]), 2)

        organisation = typed["Organization"][0]
        catalogue = typed["DataCatalog"][0]
        dataset = typed["Dataset"][0]
        downloads = typed["DataDownload"]

        for label, node in {
            "Organization": organisation,
            "DataCatalog": catalogue,
            "Dataset": dataset,
        }.items():
            assert_absolute_web_url(self, node.get("@id"), f"{label} @id")
            assert_absolute_web_url(self, node.get("url"), f"{label} url")

        self.assertEqual(catalogue["url"], PUBLIC_SITE_URL)
        self.assertEqual(dataset["url"], PUBLIC_SITE_URL)
        self.assertEqual(dataset["name"], "DSR SPL Reference Measurements")
        self.assertGreaterEqual(len(dataset.get("description", "")), 50)
        self.assertLessEqual(len(dataset.get("description", "")), 5000)
        self.assertIn(
            dataset["@id"],
            referenced_ids(catalogue.get("dataset")),
            "DataCatalog.dataset must link to the generated Dataset",
        )

        declared_distributions = dataset.get("distribution")
        if not isinstance(declared_distributions, list):
            declared_distributions = [declared_distributions]
        self.assertEqual(len(declared_distributions), 2)
        for download in downloads:
            download_id = download.get("@id")
            linked = any(
                candidate is download
                or (
                    isinstance(candidate, dict)
                    and isinstance(download_id, str)
                    and candidate.get("@id") == download_id
                )
                for candidate in declared_distributions
            )
            self.assertTrue(linked, "Every DataDownload must be linked by Dataset.distribution")

        expected_download_urls = {
            f"{PUBLIC_SITE_URL}data/measurements.json": "application/json",
            f"{PUBLIC_SITE_URL}data/measurements.csv": "text/csv",
        }
        actual_download_urls: dict[str, str] = {}
        for download in downloads:
            content_url = download.get("contentUrl")
            assert_absolute_web_url(self, content_url, "DataDownload contentUrl")
            self.assertIsInstance(download.get("encodingFormat"), str)
            actual_download_urls[content_url] = download["encodingFormat"]
            if "@id" in download:
                assert_absolute_web_url(self, download["@id"], "DataDownload @id")
        self.assertEqual(actual_download_urls, expected_download_urls)

        timestamp_pairs = [
            parse_rfc3339_instant(record["measurement"]["completed_at_utc"])
            for _, record in self.canonical
        ]
        oldest_date = min(timestamp_pairs).date().isoformat()
        newest_date = max(timestamp_pairs).date().isoformat()
        self.assertEqual(
            dataset.get("temporalCoverage"),
            f"{oldest_date}/{newest_date}",
        )

        variable_nodes = dataset.get("variableMeasured")
        self.assertIsInstance(variable_nodes, list)
        self.assertEqual(len(variable_nodes), len(REQUIRED_MEASURED_VARIABLES))
        for variable_node in variable_nodes:
            self.assertEqual(variable_node.get("@type"), "PropertyValue")
            self.assertIn(variable_node.get("unitText"), {"dB(A)", "dB(C)", "dB(Z)"})
        measured_variables = json.dumps(variable_nodes, ensure_ascii=False).casefold()
        for variable in REQUIRED_MEASURED_VARIABLES:
            with self.subTest(variable=variable):
                self.assertIn(variable.casefold(), measured_variables)

        licences = {
            node["license"]
            for node in (catalogue, dataset, *downloads)
            if "license" in node
        }
        self.assertEqual(licences, {CC_BY_4_0_URL})
        self.assertEqual(dataset.get("license"), CC_BY_4_0_URL)
        citation = (REPOSITORY_ROOT / "CITATION.cff").read_text(encoding="utf-8")
        citation_version = re.search(r"(?m)^version:\s*(\S+)\s*$", citation)
        citation_release = re.search(r"(?m)^date-released:\s*(\S+)\s*$", citation)
        self.assertIsNotNone(citation_version)
        self.assertIsNotNone(citation_release)
        self.assertEqual(dataset.get("version"), citation_version.group(1))
        self.assertEqual(dataset.get("datePublished"), citation_release.group(1))
        self.assertEqual(private_keys(documents), set())

    def test_static_cards_and_discovery_files_expose_required_public_fields_only(self) -> None:
        parser, document, rows = self.load_outputs()
        cards = {card["id"]: card for card in parser.cards}

        self.assertEqual(set(cards), self.expected_ids)
        self.assertEqual(set(rows[0]), REQUIRED_CSV_FIELDS)
        self.assertFalse(any(PRIVATE_FIELD.search(name) for name in rows[0]))
        self.assertEqual(private_keys(document), set())

        for public_record in document["measurements"]:
            with self.subTest(public_id=public_record["id"], format="JSON"):
                self.assertEqual(set(public_record), REQUIRED_DISCOVERY_FIELDS)
                self.assertTrue({"visibility", "city", "country"} <= set(public_record["location"]))
                self.assertTrue(
                    {"laeq", "lafmax", "lafmin", "lcpeak", "lceq", "lzeq"}
                    <= set(public_record["levels"])
                )

        required_card_text = {
            "LAeq",
            "LAFmax",
            "Duration",
            "Environment",
            "Calibration",
            "Quality",
            "Contributor",
            "Licence",
            "Open public record",
        }
        for public_id, (path, source) in self.expected_by_id.items():
            card = cards[public_id]
            fields = card["fields"]
            expected_record_url = (
                "https://github.com/directsoundrecords/spl-reference-measurements/blob/main/"
                + str(path.relative_to(REPOSITORY_ROOT))
            )
            with self.subTest(public_id=public_id, format="HTML"):
                self.assertEqual(fields["measurement-id"], public_id)
                self.assertEqual(fields["title"], source["measurement"]["title"])
                self.assertEqual(card["time_datetime"], source["measurement"]["completed_at_utc"])
                self.assertEqual(card["record_href"], expected_record_url)
                for field in (
                    "environment-pill",
                    "location",
                    "laeq",
                    "lafmax",
                    "lcpeak",
                    "duration",
                ):
                    self.assertTrue(fields[field], field)
                for label in required_card_text:
                    self.assertIn(label, card["text"])

    def test_optional_photos_are_copied_and_rebuild_is_deterministic(self) -> None:
        _, document, _ = self.load_outputs()
        public_by_id = {record["id"]: record for record in document["measurements"]}
        expected_photos: dict[str, Path] = {}
        for path, source in self.canonical:
            declaration = source.get("photo", {})
            if declaration.get("included") and declaration.get("filename"):
                source_photo = path.parent / declaration["filename"]
                if source_photo.is_file():
                    public_id = source["identity"]["public_measurement_id"]
                    filename = f"{public_id}{source_photo.suffix.lower() or '.jpg'}"
                    expected_photos[filename] = source_photo
                    self.assertEqual(public_by_id[public_id]["photo"], f"photos/{filename}")

        self.assertTrue(expected_photos, "Canonical fixtures must exercise optional photos")
        actual_photo_names = {path.name for path in (self.site / "photos").iterdir()}
        self.assertEqual(actual_photo_names, set(expected_photos))
        for filename, source_photo in expected_photos.items():
            self.assertEqual((self.site / "photos" / filename).read_bytes(), source_photo.read_bytes())

        first_build = tree_snapshot(self.site)
        (self.site / "photos" / "stale-photo.jpg").write_bytes(b"stale")
        build_site(root=REPOSITORY_ROOT, site=self.site, template=TEMPLATE)
        self.assertEqual(tree_snapshot(self.site), first_build)

    def test_adversarial_text_is_escaped_private_fields_are_omitted_and_null_calibration_is_safe(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_root_name:
            synthetic_root = Path(temporary_root_name) / "archive"
            synthetic_site = Path(temporary_root_name) / "site"
            public_id = "SPL-2099-999999"
            title = '<script data-name="title">alert("x") & \'quoted\'</script>'
            city = '<b data-name="city">London & "Town"</b>'
            notes = '<img src="x" onerror="alert(1)"> private-looking text & detail'
            source = copy.deepcopy(self.canonical[0][1])
            source["identity"]["public_measurement_id"] = public_id
            source["identity"]["measurement_uuid"] = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
            source["measurement"]["title"] = title
            source["measurement"]["completed_at_utc"] = "2099-12-31T23:59:59Z"
            source["public_location"].update(
                {
                    "visibility": "city",
                    "country_code": "GB",
                    "country_name": "United & Kingdom",
                    "city": city,
                    "latitude": 51.5123456789,
                    "longitude": -0.123456789,
                }
            )
            source["calibration"]["method"] = None
            source["notes"] = notes
            source["project_name"] = "PRIVATE-PROJECT-SENTINEL"
            source["precise_address"] = "PRIVATE-ADDRESS-SENTINEL"
            source["photo"] = {"included": False, "filename": None, "sha256": None}
            record_path = (
                synthetic_root
                / "measurements"
                / "2099"
                / "12"
                / public_id
                / "measurement.json"
            )
            record_path.parent.mkdir(parents=True)
            record_path.write_text(json.dumps(source), encoding="utf-8")

            build_site(root=synthetic_root, site=synthetic_site, template=TEMPLATE)
            generated_html = (synthetic_site / "index.html").read_text(encoding="utf-8")
            parser = CatalogueHTMLParser()
            parser.feed(generated_html)
            document = json.loads(
                (synthetic_site / "data" / "measurements.json").read_text(encoding="utf-8")
            )

            self.assertEqual(len(parser.cards), 1)
            card = parser.cards[0]
            self.assertEqual(card["fields"]["title"], title)
            self.assertEqual(card["fields"]["location"], f"{city}, United & Kingdom")
            self.assertNotIn("script", card["tags"])
            self.assertNotIn("b", card["tags"])
            self.assertNotIn("img", card["tags"])
            self.assertIn(html.escape(title, quote=True), generated_html)
            self.assertIn(html.escape(city, quote=True), generated_html)
            self.assertIn(html.escape(notes, quote=True), generated_html)
            self.assertNotIn("None", card["text"])
            self.assertIn("Calibration", card["text"])

            public_record = document["measurements"][0]
            self.assertEqual(public_record["title"], title)
            self.assertEqual(public_record["calibration"]["method"], None)
            self.assertEqual(private_keys(document), set())

            structured_documents = self.load_json_ld(synthetic_site)
            structured_text = json.dumps(structured_documents, ensure_ascii=False)
            self.assertEqual(private_keys(structured_documents), set())
            for private_value in (
                "PRIVATE-PROJECT-SENTINEL",
                "PRIVATE-ADDRESS-SENTINEL",
                "51.5123456789",
                "-0.123456789",
            ):
                with self.subTest(private_value=private_value):
                    self.assertNotIn(private_value, structured_text)

            title_case_definition = re.search(
                r"const\s+titleCase\s*=\s*value\s*=>\s*\{(.*?)\n\};",
                (REPOSITORY_ROOT / "docs" / "assets" / "app.js").read_text(encoding="utf-8"),
                flags=re.DOTALL,
            )
            self.assertIsNotNone(title_case_definition)
            self.assertRegex(
                title_case_definition.group(1),
                r"(\?\?|==\s*null|\?\.|String\s*\()",
                "titleCase must tolerate nullable calibration methods from public records",
            )

    def test_offset_timestamps_sort_and_render_as_utc_instants(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_root_name:
            synthetic_root = Path(temporary_root_name) / "archive"
            synthetic_site = Path(temporary_root_name) / "site"
            cases = (
                ("SPL-2099-000001", "2099-09-02T00:30:00+02:00"),
                ("SPL-2099-000002", "2099-09-01T23:45:00Z"),
            )
            for public_id, completed_at in cases:
                source = copy.deepcopy(self.canonical[0][1])
                source["identity"]["public_measurement_id"] = public_id
                source["identity"]["measurement_uuid"] = (
                    "aaaaaaaa-bbbb-4ccc-8ddd-" + public_id[-6:].zfill(12)
                )
                source["measurement"]["title"] = public_id
                source["measurement"]["completed_at_utc"] = completed_at
                source["photo"] = {"included": False, "filename": None, "sha256": None}
                record_path = (
                    synthetic_root
                    / "measurements"
                    / "2099"
                    / "09"
                    / public_id
                    / "measurement.json"
                )
                record_path.parent.mkdir(parents=True)
                record_path.write_text(json.dumps(source), encoding="utf-8")

            entries = load_catalogue(synthetic_root)
            self.assertEqual(
                [entry.public_id for entry in entries],
                ["SPL-2099-000002", "SPL-2099-000001"],
            )

            build_site(root=synthetic_root, site=synthetic_site, template=TEMPLATE)
            generated_html = (synthetic_site / "index.html").read_text(encoding="utf-8")
            parser = CatalogueHTMLParser()
            parser.feed(generated_html)
            self.assertEqual([card["id"] for card in parser.cards], ["SPL-2099-000002", "SPL-2099-000001"])
            self.assertIn("1 Sep 2099", parser.cards[0]["text"])
            self.assertIn("1 Sep 2099", parser.cards[1]["text"])

            app_javascript = (
                REPOSITORY_ROOT / "docs" / "assets" / "app.js"
            ).read_text(encoding="utf-8")
            self.assertIn('timeZone:"UTC"', app_javascript)


if __name__ == "__main__":
    unittest.main()
