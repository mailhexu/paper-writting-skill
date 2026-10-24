#!/usr/bin/env python3
"""Story 016 submission-package checks and author-controlled scaffolds.

All commands are read-only with respect to manuscript inputs. Generated prose
is a draft; the tool never submits a manuscript, chooses a venue, or edits a
bibliography.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from evidence_manifest import ManifestError, load_manifest  # noqa: E402
from repro_check import PLACEHOLDER, RECORD_SCHEMA, UNKNOWN  # noqa: E402

try:
    import pymupdf as fitz
except ModuleNotFoundError:  # pragma: no cover - dependency notice
    fitz = None

try:
    from PIL import Image
except ModuleNotFoundError:  # pragma: no cover - dependency notice
    Image = None

PROFILE_SCHEMA = "pws.venue-profiles/1"
PAPER_PLAN_SCHEMA = "pws.paper-plan/1"
REPORT_SCHEMA = "pws.submission-report/1"
BOUNDARY = (
    "Package completeness is not submission clearance; the author performs the actual submission. "
    "包完整 ≠ 可投稿；实际投稿由作者执行。"
)
SCIENTIFIC_CAVEAT = "Metadata agreement does not establish scientific support."
DEFAULT_PROFILES = Path(__file__).resolve().parents[1] / "configs" / "venue-profiles.json"
CITATION_COMMANDS = {
    "cite", "cites", "citep", "citet", "citealp", "citealt", "citeauthor", "citeyear",
    "citeyearpar", "Cite", "parencite", "Parencite", "parencites", "textcite", "Textcite",
    "textcites", "Autocite", "autocite", "autocites", "footcite", "footcites", "smartcite",
    "smartcites", "supercite", "supercites", "nocite",
}
MULTI_CITATION_COMMANDS = {
    "cites", "parencites", "textcites", "autocites", "footcites", "smartcites", "supercites",
}


class SubmissionError(Exception):
    """Input or dependency error with a consumer-readable message."""


def _read_json(path_value: str | Path, label: str) -> tuple[dict[str, Any], Path]:
    path = Path(path_value).expanduser().resolve()
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise SubmissionError(f"{label} '{path}' is unreadable: {error}") from None
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SubmissionError(f"{label} '{path}' is invalid UTF-8 JSON: {error}") from None
    if not isinstance(value, dict):
        raise SubmissionError(f"{label} '{path}' must contain a JSON object")
    return value, path


def _load_profiles(path_value: str | Path | None = None) -> dict[str, Any]:
    path = Path(path_value).expanduser().resolve() if path_value else DEFAULT_PROFILES
    document, _ = _read_json(path, "venue profiles")
    if document.get("schema") != PROFILE_SCHEMA or not isinstance(document.get("profiles"), dict):
        raise SubmissionError(f"venue profiles '{path}' must use schema {PROFILE_SCHEMA}")
    for venue_id, profile in document["profiles"].items():
        if not isinstance(profile, dict) or not isinstance(profile.get("checks"), list):
            raise SubmissionError(f"venue profile '{venue_id}' is missing its checks")
        if not isinstance(profile.get("sources"), dict) or not isinstance(profile.get("figure"), dict):
            raise SubmissionError(f"venue profile '{venue_id}' is missing source or figure parameters")
    return document["profiles"]


def _has_value(data: dict[str, Any], field: str) -> bool:
    if field not in data:
        return False
    value = data[field]
    return value is not None and (not isinstance(value, str) or bool(value.strip()))


def _source(profile: dict[str, Any], source_id: str) -> dict[str, Any]:
    source = profile["sources"].get(source_id)
    if not isinstance(source, dict) or not source.get("url"):
        raise SubmissionError(f"venue profile has no cited source '{source_id}'")
    return source


def _check_row(check_id: str, label: str, status: str, detail: str,
               source: dict[str, Any] | None) -> dict[str, Any]:
    row: dict[str, Any] = {"id": check_id, "label": label, "status": status, "detail": detail}
    if source is not None:
        row["source"] = source
    return row


def _evaluate_check(check: dict[str, Any], profile: dict[str, Any],
                    submission: dict[str, Any]) -> dict[str, Any]:
    source = _source(profile, check["source"])
    rule = check["rule"]
    field = check.get("field")
    value = submission.get(field) if field else None
    check_id = check["id"]
    label = check["label"]

    def result(status: str, detail: str) -> dict[str, Any]:
        return _check_row(check_id, label, status, detail, source)

    if rule == "one_of":
        allowed = check["values"]
        if not _has_value(submission, field):
            return result("fail", f"missing required field '{field}'")
        if value not in allowed:
            return result("fail", f"'{value}' is not one of {allowed}")
        return result("pass", f"'{value}' is an allowed article type")

    if rule == "word_limit":
        if not _has_value(submission, field):
            return result("fail", f"missing required field '{field}'")
        count = value
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            return result("fail", f"'{field}' must be a non-negative integer")
        article_type = submission.get(check["lookup_field"])
        limits = check["limits"]
        if not isinstance(article_type, str) or not article_type.strip():
            return result("fail", f"'{check['lookup_field']}' must be a non-empty article-type string")
        if article_type not in limits:
            return result("fail", f"no word-limit rule for article type '{article_type}'")
        limit = limits[article_type]
        if limit is None:
            return result("pass", f"{count} words recorded; the checked source lists no cap for '{article_type}'")
        if count > limit:
            return result("fail", f"{count} words exceeds the {limit}-word limit for '{article_type}'")
        return result("pass", f"{count} words is within the {limit}-word limit")

    if rule == "equals":
        if field not in submission:
            return result("fail", f"missing required field '{field}'")
        expected = check["expected"]
        if value is not expected:
            return result("fail", f"'{field}' is {value!r}; expected {expected!r}")
        return result("pass", f"'{field}' matches the cited requirement")
    if rule == "nonempty":
        if field not in submission:
            return result("fail", f"missing required field '{field}'")
        if not isinstance(value, str) or not value.strip():
            return result("fail", f"'{field}' must be a non-empty string")
        return result("pass", f"'{field}' is recorded")
    if rule == "nonnegative_integer":
        if field not in submission:
            return result("fail", f"missing required field '{field}'")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return result("fail", f"'{field}' must be a non-negative integer")
        return result("pass", f"'{field}' is a non-negative integer")

    if rule in ("conditional_equals", "conditional_nonempty"):
        condition_field = check["condition_field"]
        if not _has_value(submission, condition_field):
            return result("fail", f"missing required condition field '{condition_field}'")
        condition = submission[condition_field]
        allowed_conditions = check.get("condition_allowed_values")
        if allowed_conditions is not None and condition not in allowed_conditions:
            return result("fail", f"'{condition_field}' value '{condition}' is not recognized")
        if condition not in check["condition_values"]:
            return result("pass", f"'{field}' is not required for declared '{condition_field}: {condition}'")
        if rule == "conditional_equals":
            if field not in submission:
                return result("fail", f"'{field}' is required when '{condition_field}' is '{condition}'")
            expected = check["expected"]
            if value is not expected:
                return result("fail", f"'{field}' is {value!r}; expected {expected!r}")
            return result("pass", f"'{field}' is present for declared '{condition_field}: {condition}'")
        if not isinstance(value, str) or not value.strip():
            return result("fail", f"'{field}' must be a non-empty string when '{condition_field}' is '{condition}'")
        return result("pass", f"'{field}' is present for declared '{condition_field}: {condition}'")

    if rule == "maximum":
        if not _has_value(submission, field):
            return result("fail", f"missing required field '{field}'")
        number = value
        if isinstance(number, bool) or not isinstance(number, int) or number < 0:
            return result("fail", f"'{field}' must be a non-negative integer")
        maximum = check["maximum"]
        if number > maximum:
            return result("fail", f"{number} exceeds the maximum {maximum}")
        return result("pass", f"{number} is within the maximum {maximum}")

    if rule == "policy_recheck":
        date_field = check.get("date_field", "current_policy_checked_on")
        attestation_field = check.get("attestation_field", "current_policy_rechecked")
        if submission.get(attestation_field) is not True:
            return result("fail", f"author must recheck current policy and set '{attestation_field}: true'")
        if not _has_value(submission, date_field):
            return result("fail", f"missing required field '{date_field}'")
        try:
            checked_on = date.fromisoformat(submission[date_field])
            not_before = date.fromisoformat(check["not_before"])
        except (TypeError, ValueError):
            return result("fail", f"'{date_field}' and the configured source date must be ISO dates")
        if checked_on < not_before:
            return result("fail", f"policy check date {checked_on} predates the configured source date {not_before}")
        if checked_on > date.today():
            return result("fail", f"policy check date {checked_on} is in the future")
        return result("pass", f"author reports current policy rechecked on {checked_on}; the tool does not fetch policy pages")

    raise SubmissionError(f"venue profile uses unsupported check rule '{rule}'")


def _load_figure_manifest(manifest_value: str | Path) -> tuple[dict[str, Any], Path]:
    manifest, path = _read_json(manifest_value, "figure manifest")
    figures = manifest.get("figures")
    if not isinstance(figures, list) or not figures:
        raise SubmissionError(f"figure manifest '{path}' must contain a non-empty figures list")
    return manifest, path


def _profile_figure(profile: dict[str, Any]) -> dict[str, Any]:
    figure = profile["figure"]
    source = _source(profile, figure["source"])
    return {**figure, "source_record": source}


def _hex_rgb(value: str) -> tuple[int, int, int]:
    value = value.strip().lstrip("#")
    if len(value) != 6:
        raise SubmissionError(f"invalid configured RGB color '{value}'")
    try:
        return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]
    except ValueError:
        raise SubmissionError(f"invalid configured RGB color '{value}'") from None


def _is_neutral(rgb: tuple[int, int, int]) -> bool:
    return max(rgb) - min(rgb) <= 14


def _palette_match(rgb: tuple[int, int, int], palette: list[tuple[int, int, int]]) -> bool:
    return any(max(abs(actual - allowed) for actual, allowed in zip(rgb, candidate)) <= 14
               for candidate in palette)


def _span_text(page: Any) -> list[dict[str, Any]]:
    spans: list[dict[str, Any]] = []
    for block in page.get_text("dict").get("blocks", []):
        for line in block.get("lines", []):
            direction = line.get("dir", (1.0, 0.0))
            for span in line.get("spans", []):
                if span.get("text", "").strip():
                    span["_direction"] = direction
                    spans.append(span)
    return spans


def _rgb_from_pdf_int(value: int) -> tuple[int, int, int]:
    return ((value >> 16) & 255, (value >> 8) & 255, value & 255)


def _check_pdf(path: Path, figure: dict[str, Any], spec: dict[str, Any]) -> list[dict[str, Any]]:
    if fitz is None:
        raise SubmissionError("PDF inspection requires PyMuPDF (install PyMuPDF from requirements-submission.txt)")
    source = spec["source_record"]
    checks: list[dict[str, Any]] = []
    try:
        document = fitz.open(path)
    except Exception as error:
        raise SubmissionError(f"figure '{path}' is not a readable PDF: {error}") from None
    try:
        if document.page_count != 1:
            checks.append(_check_row("page-count", "one rendered figure per file", "fail",
                                     f"PDF contains {document.page_count} pages; expected one", source))
            return checks
        page = document[0]
        rect = page.rect
        column = figure.get("column")
        expected_width = spec["columns_mm"].get(column)
        if expected_width is None:
            checks.append(_check_row("physical-width", "physical column width", "fail",
                                     f"unknown column '{column}'; choose one of {list(spec['columns_mm'])}", source))
        else:
            actual_width = rect.width * 25.4 / 72.0
            tolerance = float(spec.get("width_tolerance_mm", 0.75))
            status = "pass" if abs(actual_width - float(expected_width)) <= tolerance else "fail"
            checks.append(_check_row(
                "physical-width", "physical column width", status,
                f"rendered width {actual_width:.2f} mm; expected {expected_width} mm ± {tolerance:g} mm",
                source,
            ))
        spans = _span_text(page)
        width, height = rect.width, rect.height
        non_panel_spans = [span for span in spans if span.get("text", "").strip()]
        title_candidates = []
        for span in non_panel_spans:
            text = span["text"].strip()
            bbox = span.get("bbox", (0, 0, 0, 0))
            center_x = (float(bbox[0]) + float(bbox[2])) / 2.0
            direction = span.get("_direction", (1.0, 0.0))
            horizontal = (isinstance(direction, (tuple, list)) and len(direction) == 2
                          and abs(float(direction[1])) <= 0.01)
            if (horizontal and len(text) >= 4 and float(bbox[1]) <= height * 0.16
                    and abs(center_x - width / 2.0) <= width * 0.22):
                title_candidates.append(text)
        title_status = "fail" if title_candidates else "manual-required"
        title_detail = (f"title-like centered text at the top: {title_candidates}"
                        if title_candidates else
                        "the position heuristic found no title candidate; inspect all panels for short or left-aligned titles")
        checks.append(_check_row("embedded-title", "no embedded title", title_status, title_detail, source))
        panels = figure.get("panels")
        panel_style = figure.get("panel_style", spec.get("panel_style_default", "parenthesized"))
        if "panels" not in figure:
            checks.append(_check_row("panel-labels", "panel labels", "fail",
                                     "manifest must explicitly list expected panel labels (use an empty list for no panels)", source))
        elif panel_style not in ("parenthesized", "bare"):
            checks.append(_check_row("panel-labels", "panel labels", "fail",
                                     f"unknown panel style '{panel_style}'", source))
        elif not isinstance(panels, list) or any(not isinstance(label, str) or not label.strip() for label in panels):
            checks.append(_check_row("panel-labels", "panel labels", "fail",
                                     "panels must be a list of non-empty panel letters", source))
        else:
            missing: list[str] = []
            nonbold: list[str] = []
            normalized = {str(span["text"]).strip(): span for span in spans}
            for label in panels:
                expected_label = f"({label})" if panel_style == "parenthesized" else label
                span = normalized.get(expected_label)
                if span is None:
                    missing.append(expected_label)
                elif not ("bold" in str(span.get("font", "")).casefold() or int(span.get("flags", 0)) & 16):
                    nonbold.append(expected_label)
            failures = []
            if missing:
                failures.append(f"missing {missing}")
            if nonbold:
                failures.append(f"not bold: {nonbold}")
            checks.append(_check_row(
                "panel-labels", "bold panel labels", "fail" if failures else "pass",
                "; ".join(failures) if failures else f"found required {panel_style} labels {panels}", source,
            ))

            if not panels:
                checks.append(_check_row("panel-placement", "panel labels at each panel's top-left", "pass",
                                         "no panel labels declared", source))
            else:
                panel_regions = figure.get("panel_regions")
                if not isinstance(panel_regions, dict):
                    checks.append(_check_row("panel-placement", "panel labels at each panel's top-left",
                                             "manual-required",
                                             "panel_regions are unavailable; inspect each label relative to its panel", source))
                else:
                    unverified: list[str] = []
                    invalid_regions: list[str] = []
                    misplaced: list[str] = []
                    for label in panels:
                        expected_label = f"({label})" if panel_style == "parenthesized" else label
                        span = normalized.get(expected_label)
                        region = panel_regions.get(label)
                        if span is None or region is None:
                            unverified.append(label)
                            continue
                        if (not isinstance(region, list) or len(region) != 4
                                or any(isinstance(value, bool) or not isinstance(value, (int, float))
                                       for value in region)):
                            invalid_regions.append(label)
                            continue
                        x0, y0, x1, y1 = (float(value) for value in region)
                        if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
                            invalid_regions.append(label)
                            continue
                        bbox = span.get("bbox")
                        if not isinstance(bbox, (tuple, list)) or len(bbox) != 4:
                            unverified.append(label)
                            continue
                        left, top, right, bottom = (float(value) for value in bbox)
                        region_left, region_top = x0 * width, y0 * height
                        region_right, region_bottom = x1 * width, y1 * height
                        if (left < region_left or top < region_top or right > region_right or bottom > region_bottom
                                or left > region_left + (region_right - region_left) * 0.5
                                or top > region_top + (region_bottom - region_top) * 0.5):
                            misplaced.append(label)
                    if invalid_regions:
                        placement_status = "fail"
                        placement_detail = f"invalid normalized panel regions for {invalid_regions}"
                    elif misplaced:
                        placement_status = "fail"
                        placement_detail = f"labels are not at the top-left inside their panel regions: {misplaced}"
                    elif unverified:
                        placement_status = "manual-required"
                        placement_detail = f"panel bounds or extractable labels unavailable for {unverified}; inspect placement"
                    else:
                        placement_status = "pass"
                        placement_detail = "each label is in the top-left quadrant of its declared panel region"
                    checks.append(_check_row("panel-placement", "panel labels at each panel's top-left",
                                             placement_status, placement_detail, source))

        if spans:
            font_names = [str(span.get("font", "")) for span in spans]
            nonsans = [name for name in font_names
                       if not any(token in name.casefold() for token in ("sans", "helvetica", "arial"))]
            checks.append(_check_row(
                "font-family", "sans-serif font family", "fail" if nonsans else "pass",
                f"non-sans fonts found: {sorted(set(nonsans))}" if nonsans else "all extracted text uses a sans-serif family",
                source,
            ))
            ordinary_minimum = float(spec["minimum_ordinary_font_pt"])
            script_minimum = float(spec["minimum_script_font_pt"])
            body = float(spec["body_font_pt"])
            ordinary_sizes: list[float] = []
            script_sizes: list[float] = []
            ambiguous_sizes: list[float] = []
            below_absolute_floor: list[float] = []
            for span in spans:
                size = float(span.get("size", 0.0))
                if int(span.get("flags", 0)) & 1:
                    script_sizes.append(size)
                elif size + 0.1 < script_minimum:
                    below_absolute_floor.append(size)
                elif size + 0.1 < ordinary_minimum:
                    ambiguous_sizes.append(size)
                else:
                    ordinary_sizes.append(size)
            too_small_scripts = [size for size in script_sizes if size + 0.1 < script_minimum]
            has_body_size = any(abs(size - body) <= 0.5 for size in ordinary_sizes)
            size_failures = []
            if below_absolute_floor:
                size_failures.append(
                    f"unclassified text below the absolute {script_minimum:g} pt minimum: "
                    f"{sorted(set(round(x, 2) for x in below_absolute_floor))}"
                )
            if too_small_scripts:
                size_failures.append(
                    f"superscript text below {script_minimum:g} pt: "
                    f"{sorted(set(round(x, 2) for x in too_small_scripts))}"
                )
            if not has_body_size:
                size_failures.append(f"no ordinary text at the configured {body:g} pt body size")
            size_status = "fail" if size_failures else "manual-required"
            if size_failures:
                size_detail = f"{'; '.join(size_failures)}; only extractable text spans were screened"
                if ambiguous_sizes:
                    size_detail += (
                        f"; unclassified spans in the 6–7 pt range need role review: "
                        f"{sorted(set(round(x, 2) for x in ambiguous_sizes))}"
                    )
            else:
                ambiguous_detail = (
                    f"; unclassified 6–7 pt spans need role review: "
                    f"{sorted(set(round(x, 2) for x in ambiguous_sizes))}"
                    if ambiguous_sizes else ""
                )
                size_detail = (
                    f"no known text-size defect among extracted spans: ordinary text at least "
                    f"{ordinary_minimum:g} pt, superscript text at least {script_minimum:g} pt, "
                    f"and {body:g} pt body text is present{ambiguous_detail}; PDF text extraction "
                    "completeness is not verified, so inspect all text at final print size"
                )
            checks.append(_check_row(
                "print-size-legibility", "text size at rendered print dimensions",
                size_status, size_detail, source,
            ))
            text_colors = [_rgb_from_pdf_int(int(span.get("color", 0))) for span in spans]
        else:
            checks.extend([
                _check_row("font-family", "sans-serif font family", "fail", "PDF contains no extractable text", source),
                _check_row("print-size-legibility", "text size at rendered print dimensions", "fail",
                           "PDF contains no extractable text", source),
            ])
            text_colors = []

        palette = [_hex_rgb(color) for color in spec["palette_hex"]]
        drawing_colors: list[tuple[int, int, int]] = []
        for drawing in page.get_drawings():
            for key in ("color", "fill"):
                color = drawing.get(key)
                if isinstance(color, (tuple, list)) and len(color) >= 3:
                    drawing_colors.append(tuple(round(float(channel) * 255) for channel in color[:3]))
        all_colors = drawing_colors + text_colors
        outside = [rgb for rgb in all_colors if not _is_neutral(rgb) and not _palette_match(rgb, palette)]
        checks.append(_check_row(
            "color-palette", "color palette",
            "manual-required" if outside else "pass",
            f"unclassified non-neutral vector/text colors require color-safety inspection: {sorted(set(outside))}"
            if outside else "all extracted vector/text colors are neutral or in the configured categorical palette",
            source,
        ))

        image_occurrences = page.get_image_info(xrefs=True)
        low_resolution: list[str] = []
        min_dpi = _minimum_dpi(spec, figure) if image_occurrences else None
        for index, image in enumerate(image_occurrences):
            pixel_width, pixel_height = image.get("width"), image.get("height")
            transform = image.get("transform")
            try:
                transform = tuple(transform)
            except TypeError:
                transform = ()
            if len(transform) == 6:
                a, b, c, d = (float(value) for value in transform[:4])
                display_width, display_height = (a * a + b * b) ** 0.5, (c * c + d * d) ** 0.5
            else:
                try:
                    bbox = tuple(image.get("bbox", ()))
                except TypeError:
                    bbox = ()
                if len(bbox) != 4:
                    low_resolution.append(f"image occurrence {index}: placement dimensions unavailable")
                    continue
                x0, y0, x1, y1 = (float(value) for value in bbox)
                display_width, display_height = x1 - x0, y1 - y0
            if display_width <= 0 or display_height <= 0:
                low_resolution.append(f"image occurrence {index}: placement dimensions are invalid")
                continue
            dpi_x = pixel_width * 72.0 / display_width
            dpi_y = pixel_height * 72.0 / display_height
            if min(dpi_x, dpi_y) + 0.01 < min_dpi:
                low_resolution.append(
                    f"image occurrence {index}: {dpi_x:.0f}×{dpi_y:.0f} dpi, requires {min_dpi}"
                )
        checks.append(_check_row(
            "resolution", "raster resolution", "fail" if low_resolution else "pass",
            "; ".join(low_resolution) if low_resolution else
            (f"all {len(image_occurrences)} raster image occurrences meet {min_dpi} dpi"
             if image_occurrences else "vector PDF; raster dpi is not applicable"),
            source,
        ))

        pdffonts = shutil.which("pdffonts")
        if pdffonts is None:
            checks.append(_check_row("embedded-fonts", "fonts embedded in PDF", "fail",
                                     "pdffonts is required to verify font embedding", source))
        else:
            command = subprocess.run([pdffonts, str(path)], capture_output=True, text=True, timeout=30)
            if command.returncode != 0:
                checks.append(_check_row("embedded-fonts", "fonts embedded in PDF", "fail",
                                         f"pdffonts failed: {command.stderr.strip()}", source))
            else:
                font_rows = [line for line in command.stdout.splitlines()[2:] if line.strip()]
                embedded = []
                for line in font_rows:
                    match = re.search(
                        r"\s+(yes|no)\s+(yes|no)\s+(yes|no)\s+(?:\d+\s+\d+|-)$", line
                    )
                    embedded.append(match is not None and match.group(1) == "yes")
                fonts_ok = bool(font_rows) and all(embedded)
                detail = ("all listed fonts are embedded" if fonts_ok else
                          "one or more PDF font records are unembedded or unrecognized")
                if not font_rows:
                    detail = "PDF contains no extractable font records"
                checks.append(_check_row("embedded-fonts", "fonts embedded in PDF",
                                         "pass" if fonts_ok else "fail", detail, source))
        if image_occurrences:
            checks.append(_check_row(
                "raster-color-inspection", "raster colors", "manual-required",
                "raster pixels, including inline PDF images, are not palette-verified; inspect the actual print-size rendering",
                source,
            ))
    finally:
        document.close()
    return checks


def _minimum_dpi(spec: dict[str, Any], figure: dict[str, Any]) -> int:
    per_type = spec.get("minimum_raster_dpi_by_artwork_type")
    if isinstance(per_type, dict):
        artwork_type = figure.get("artwork_type")
        if artwork_type not in per_type:
            raise SubmissionError(
                f"raster figure needs artwork_type from {list(per_type)} for the venue's resolution rule"
            )
        return int(per_type[artwork_type])
    return int(spec["minimum_raster_dpi"])


def _check_png(path: Path, figure: dict[str, Any], spec: dict[str, Any]) -> list[dict[str, Any]]:
    source = spec["source_record"]
    if Image is None:
        raise SubmissionError("PNG inspection requires Pillow (install Pillow from requirements-submission.txt)")
    checks: list[dict[str, Any]] = []
    try:
        image = Image.open(path)
        image.load()
    except Exception as error:
        raise SubmissionError(f"figure '{path}' is not a readable PNG: {error}") from None
    if image.format != "PNG":
        raise SubmissionError(f"figure '{path}' has PNG extension but file format is {image.format}")
    column = figure.get("column")
    expected_width = spec["columns_mm"].get(column)
    dpi = image.info.get("dpi")
    if expected_width is None:
        checks.append(_check_row("physical-width", "physical column width", "fail",
                                 f"unknown column '{column}'; choose one of {list(spec['columns_mm'])}", source))
    elif not isinstance(dpi, (tuple, list)) or not dpi or not dpi[0]:
        checks.append(_check_row("physical-width", "physical column width", "fail",
                                 "PNG has no physical-resolution metadata", source))
    else:
        actual_width = image.width * 25.4 / float(dpi[0])
        tolerance = float(spec.get("width_tolerance_mm", 0.75))
        status = "pass" if abs(actual_width - float(expected_width)) <= tolerance else "fail"
        checks.append(_check_row("physical-width", "physical column width", status,
                                 f"rendered width {actual_width:.2f} mm; expected {expected_width} mm ± {tolerance:g} mm", source))
    minimum = _minimum_dpi(spec, figure)
    actual_dpi = min(float(value) for value in dpi[:2]) if isinstance(dpi, (tuple, list)) and len(dpi) >= 2 else 0.0
    resolution_ok = actual_dpi + 0.01 >= minimum
    checks.append(_check_row("resolution", "raster resolution", "pass" if resolution_ok else "fail",
                             f"PNG resolution {actual_dpi:g} dpi; minimum {minimum} dpi", source))
    # A raster image has no reliable text semantics. Do not claim title/panel/font checks passed.
    checks.extend([
        _check_row("embedded-title", "no embedded title", "manual-required",
                   "raster text cannot be semantically inspected; inspect the rendered image at print size", source),
        _check_row("panel-labels", "panel labels", "manual-required",
                   "raster text cannot be semantically inspected; inspect label presence, weight, and placement", source),
        _check_row("font-family", "sans-serif font family", "manual-required",
                   "raster text cannot be semantically inspected; inspect the rendered image at print size", source),
        _check_row("print-size-legibility", "text size at rendered print dimensions", "manual-required",
                   "raster text cannot be semantically inspected; inspect the rendered image at print size", source),
        _check_row("color-palette", "color palette", "manual-required",
                   "raster pixel colors are not treated as palette-verified; inspect the actual rendering", source),
    ])
    image.close()
    return checks


def _inspect_figures(venue_id: str, manifest_value: str | Path,
                     profiles_path: str | Path | None = None) -> dict[str, Any]:
    profiles = _load_profiles(profiles_path)
    profile = profiles.get(venue_id)
    if profile is None:
        return {
            "schema": REPORT_SCHEMA, "status": "fail", "venue": venue_id,
            "message": f"unknown venue '{venue_id}'; no default venue or figure rules are applied",
            "figures": [], "boundary": BOUNDARY,
        }
    manifest, manifest_path = _load_figure_manifest(manifest_value)
    spec = _profile_figure(profile)
    figures: list[dict[str, Any]] = []
    for index, item in enumerate(manifest["figures"]):
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            figures.append({"index": index, "status": "fail", "checks": [
                _check_row("figure-path", "figure path", "fail", "each figure needs a relative path", spec["source_record"])
            ]})
            continue
        value = Path(item["path"])
        if value.is_absolute() or ".." in value.parts:
            raise SubmissionError(f"figure[{index}].path must be relative and must not contain '..'")
        path = manifest_path.parent / value
        resolved = path.resolve()
        if manifest_path.parent.resolve() not in resolved.parents:
            raise SubmissionError(f"figure[{index}].path resolves outside the figure-manifest directory")
        if path.is_symlink():
            raise SubmissionError(f"figure[{index}].path must not be a symbolic link")
        if not path.is_file():
            figures.append({"index": index, "path": str(value), "status": "fail", "checks": [
                _check_row("figure-file", "rendered figure file", "fail", f"file does not exist: {path}", spec["source_record"])
            ]})
            continue
        extension = path.suffix.lower().lstrip(".")
        allowed = spec["allowed_formats"]
        if extension not in allowed:
            checks = [_check_row("format", "figure file format", "fail",
                                 f".{extension} is not allowed; allowed formats: {allowed}", spec["source_record"])]
        else:
            format_row = _check_row("format", "figure file format", "pass",
                                    f"rendered {extension.upper()} is an allowed venue format", spec["source_record"])
            try:
                checks = [format_row] + (_check_pdf(path, item, spec) if extension == "pdf"
                                         else _check_png(path, item, spec))
            except SubmissionError as error:
                checks = [format_row, _check_row("figure-inspection", "rendered figure inspection", "fail",
                                                  str(error), spec["source_record"])]
        status = ("fail" if any(check["status"] == "fail" for check in checks) else
                  "manual-required" if any(check["status"] == "manual-required" for check in checks) else "pass")
        manual = [check for check in checks if check["status"] == "manual-required"]
        figures.append({
            "index": index, "path": str(value), "status": status, "checks": checks,
            "manual_checks_required": manual,
        })
    status = ("fail" if not figures or any(item["status"] == "fail" for item in figures) else
              "manual-required" if any(item["status"] == "manual-required" for item in figures) else "pass")
    return {
        "schema": REPORT_SCHEMA, "status": status, "venue": venue_id,
        "policy_source": spec["source_record"], "figures": figures,
        "human_visual_reading": "required at final print size; this mechanical report does not replace it",
        "manifest": str(manifest_path), "boundary": BOUNDARY,
    }


def venue_check(venue_id: str, submission_value: str | Path, figure_manifest: str | Path | None = None,
                profiles_path: str | Path | None = None) -> dict[str, Any]:
    profiles = _load_profiles(profiles_path)
    submission, submission_path = _read_json(submission_value, "submission checklist input")
    profile = profiles.get(venue_id)
    if profile is None:
        return {
            "schema": REPORT_SCHEMA, "status": "fail", "venue": venue_id,
            "checks": [_check_row("venue-profile", "venue profile", "fail",
                                   f"unknown venue '{venue_id}'; no default venue or policy is applied", None)],
            "boundary": BOUNDARY,
        }
    rows = [_evaluate_check(check, profile, submission) for check in profile["checks"]]
    figure_report = None
    figure_source = _source(profile, profile["figure"]["source"])
    if figure_manifest is None:
        rows.append(_check_row("figure-files", "figure files meet the venue profile", "fail",
                               "no rendered-figure manifest supplied", figure_source))
    else:
        figure_report = _inspect_figures(venue_id, figure_manifest, profiles_path)
        figure_status = figure_report["status"]
        rows.append(_check_row(
            "figure-files", "figure files meet the venue profile", figure_status,
            f"{sum(item['status'] == 'pass' for item in figure_report['figures'])}/"
            f"{len(figure_report['figures'])} rendered files pass mechanical checks",
            figure_source,
        ))
    status = ("fail" if any(row["status"] == "fail" for row in rows) else
              "manual-required" if any(row["status"] == "manual-required" for row in rows) else
              "pass" if rows else "fail")
    report: dict[str, Any] = {
        "schema": REPORT_SCHEMA, "status": status, "venue": venue_id,
        "venue_name": profile["name"], "input": str(submission_path),
        "checks": rows, "boundary": BOUNDARY,
        "policy_note": "Sources are cited but not fetched by this command; the author must recheck current policies.",
    }
    if figure_report is not None:
        report["figure_report"] = figure_report
    return report


def _render_tools(value: Any) -> str:
    if not isinstance(value, list) or not value:
        return ""
    names: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            return ""
        name, model = item.get("name"), item.get("model")
        if not isinstance(name, str) or not name.strip() or not isinstance(model, str) or not model.strip():
            return ""
        names.append(f"{name.strip()} ({model.strip()})")
    return "; ".join(names)


def disclosure(venue_id: str, usage_value: str | Path,
               profiles_path: str | Path | None = None) -> dict[str, Any]:
    profiles = _load_profiles(profiles_path)
    usage, usage_path = _read_json(usage_value, "AI-use record")
    profile = profiles.get(venue_id)
    if profile is None:
        return {
            "schema": REPORT_SCHEMA, "status": "fail", "venue": venue_id,
            "text": "Unknown venue. 核对现行政策 (verify the current policy); no default disclosure text is generated.",
            "source": None, "boundary": BOUNDARY,
        }
    ai = profile.get("ai")
    source = _source(profile, "ai")
    use = usage.get("use")
    if not isinstance(use, str) or not use.strip():
        return {"schema": REPORT_SCHEMA, "status": "fail", "venue": venue_id,
                "message": "AI-use record must explicitly state 'use' (none, basic, substantive, manuscript_preparation, or research_process)",
                "source": source, "input": str(usage_path), "boundary": BOUNDARY}
    valid_uses = {"none", "basic", "substantive", "manuscript_preparation", "research_process"}
    if use not in valid_uses:
        return {"schema": REPORT_SCHEMA, "status": "fail", "venue": venue_id,
                "message": f"unrecognized AI-use category '{use}'", "source": source,
                "input": str(usage_path), "boundary": BOUNDARY}
    required_uses = ai["required_uses"]
    no_disclosure_uses = ai["no_disclosure_uses"]
    if use not in required_uses and use not in no_disclosure_uses:
        return {"schema": REPORT_SCHEMA, "status": "fail", "venue": venue_id,
                "message": f"AI-use category '{use}' is not mapped for venue '{venue_id}'; recheck current policy",
                "source": source, "input": str(usage_path), "boundary": BOUNDARY}
    if use in no_disclosure_uses:
        return {"schema": REPORT_SCHEMA, "status": "pass", "venue": venue_id,
                "text": None, "message": f"author records '{use}'; the venue profile explicitly classifies it as no-disclosure",
                "source": source, "input": str(usage_path), "boundary": BOUNDARY}
    tools = _render_tools(usage.get("tools"))
    required = {
        "tools": tools,
        "purpose": usage.get("purpose"),
        "human_review": usage.get("human_review"),
        "responsibility_statement": usage.get("responsibility_statement"),
        "placement": usage.get("placement"),
    }
    missing = [key for key, value in required.items() if not isinstance(value, str) or not value.strip()]
    if missing:
        return {"schema": REPORT_SCHEMA, "status": "fail", "venue": venue_id,
                "message": f"AI-use record is missing required author facts: {', '.join(missing)}",
                "source": source, "input": str(usage_path), "boundary": BOUNDARY}
    try:
        text = ai["template"].format(**required)
    except (KeyError, ValueError) as error:
        raise SubmissionError(f"invalid AI disclosure template for venue '{venue_id}': {error}") from None
    return {
        "schema": REPORT_SCHEMA, "status": "pass", "venue": venue_id,
        "text": text, "placement_guidance": ai["placement_guidance"],
        "source": source, "input": str(usage_path),
        "policy_note": "Scaffold only; verify the current venue policy and author-provided facts before use.",
        "boundary": BOUNDARY,
    }


def cover_letter(title: str, venue: str, plan_value: str | Path | None) -> dict[str, Any]:
    if plan_value is None:
        return {"schema": REPORT_SCHEMA, "status": "fail",
                "message": "A cover letter requires an author-approved Paper Plan input.",
                "boundary": BOUNDARY}
    plan, plan_path = _read_json(plan_value, "Paper Plan input")
    if plan.get("schema") != PAPER_PLAN_SCHEMA:
        return {"schema": REPORT_SCHEMA, "status": "fail",
                "message": f"Paper Plan input must use schema {PAPER_PLAN_SCHEMA}",
                "input": str(plan_path), "boundary": BOUNDARY}
    if plan.get("status") != "approved":
        return {"schema": REPORT_SCHEMA, "status": "fail",
                "message": "Paper Plan is not approved; cover letter generation is refused.",
                "input": str(plan_path), "boundary": BOUNDARY}
    source = plan.get("source")
    contributions = plan.get("contributions")
    if not isinstance(source, str) or not source.strip():
        return {"schema": REPORT_SCHEMA, "status": "fail",
                "message": "approved Paper Plan input must identify its authoritative source record.",
                "input": str(plan_path), "boundary": BOUNDARY}
    if not isinstance(contributions, list) or not contributions or any(
        not isinstance(item, str) or not item.strip() for item in contributions
    ):
        return {"schema": REPORT_SCHEMA, "status": "fail",
                "message": "approved Paper Plan must contain non-empty contribution items.",
                "input": str(plan_path), "boundary": BOUNDARY}
    if not title.strip() or not venue.strip():
        return {"schema": REPORT_SCHEMA, "status": "fail",
                "message": "title and target venue are required author inputs.",
                "input": str(plan_path), "boundary": BOUNDARY}
    bullets = "\n".join(f"- Contribution: {item.strip()}" for item in contributions)
    draft = (
        "Dear Editor,\n\n"
        f"Please consider the manuscript entitled \"{title.strip()}\" for {venue.strip()}.\n\n"
        "The manuscript's contribution items, taken from the author-approved Paper Plan, are:\n"
        f"{bullets}\n\n"
        "Thank you for your consideration.\n\nSincerely,\n"
    )
    return {
        "schema": REPORT_SCHEMA, "status": "pass", "draft": draft,
        "contributions": [item.strip() for item in contributions],
        "source": {"paper_plan_input": str(plan_path), "author_plan_record": source},
        "boundary": BOUNDARY,
    }


def _strip_comments(text: str) -> str:
    lines: list[str] = []
    for line in text.splitlines():
        cut = len(line)
        for index, char in enumerate(line):
            if char != "%":
                continue
            slashes = 0
            cursor = index - 1
            while cursor >= 0 and line[cursor] == "\\":
                slashes += 1
                cursor -= 1
            if slashes % 2 == 0:
                cut = index
                break
        lines.append(line[:cut])
    return "\n".join(lines)


def _read_tex_group(text: str, start: int, opening: str, closing: str) -> tuple[str, int] | None:
    if start >= len(text) or text[start] != opening:
        return None
    depth = 1
    brace_depth = 0
    cursor = start + 1
    while cursor < len(text):
        char = text[cursor]
        if char == "\\":
            cursor += 2
            continue
        if opening == "[" and char == "{":
            brace_depth += 1
        elif opening == "[" and char == "}" and brace_depth:
            brace_depth -= 1
        elif opening == "{" and char == "{":
            depth += 1
        elif opening == "{" and char == "}":
            depth -= 1
        elif opening == "[" and not brace_depth and char == "[":
            depth += 1
        elif opening == "[" and not brace_depth and char == "]":
            depth -= 1
        if depth == 0:
            return text[start + 1:cursor], cursor + 1
        cursor += 1
    return None


def _citation_keys(tex: str) -> list[str]:
    commands = "|".join(re.escape(command) for command in sorted(CITATION_COMMANDS, key=len, reverse=True))
    pattern = re.compile(rf"\\(?P<command>{commands})\*?")
    uncommented = _strip_comments(tex)
    keys: list[str] = []
    for match in pattern.finditer(uncommented):
        command = match.group("command")
        cursor = match.end()
        arguments: list[str] = []
        while cursor < len(uncommented):
            while cursor < len(uncommented) and uncommented[cursor].isspace():
                cursor += 1
            if cursor < len(uncommented) and uncommented[cursor] == "[":
                group = _read_tex_group(uncommented, cursor, "[", "]")
                if group is None:
                    break
                _, cursor = group
                continue
            if cursor < len(uncommented) and uncommented[cursor] == "{":
                group = _read_tex_group(uncommented, cursor, "{", "}")
                if group is None:
                    break
                content, cursor = group
                arguments.append(content)
                if command not in MULTI_CITATION_COMMANDS:
                    break
                continue
            break
        for argument in arguments:
            for key in argument.split(","):
                key = key.strip()
                if key and key != "*" and key not in keys:
                    keys.append(key)
    return keys


def _bib_keys(bib: str) -> set[str]:
    text = _strip_comments(bib)
    pattern = re.compile(r"(?im)^\s*@\s*([A-Za-z]+)\s*[({]\s*([^,\s]+)\s*,")
    ignored = {"comment", "preamble", "string"}
    return {match.group(2).strip() for match in pattern.finditer(text)
            if match.group(1).casefold() not in ignored}


def citation_check(tex_value: str | Path, bib_value: str | Path) -> dict[str, Any]:
    tex_path, bib_path = Path(tex_value).expanduser().resolve(), Path(bib_value).expanduser().resolve()
    try:
        tex = tex_path.read_text(encoding="utf-8")
    except OSError as error:
        raise SubmissionError(f"manuscript source '{tex_path}' is unreadable: {error}") from None
    try:
        bib = bib_path.read_text(encoding="utf-8")
    except OSError as error:
        raise SubmissionError(f"bibliography '{bib_path}' is unreadable: {error}") from None
    cited = _citation_keys(tex)
    available = _bib_keys(bib)
    missing = sorted(set(cited) - available)
    return {
        "schema": REPORT_SCHEMA, "status": "fail" if missing else "pass",
        "cited_keys": cited, "missing_keys": missing,
        "source": {"manuscript": str(tex_path), "bibliography": str(bib_path)},
        "caveat": SCIENTIFIC_CAVEAT,
        "author_confirmation": "Any suggested bibliography edit requires author confirmation; this check never writes either input.",
        "boundary": BOUNDARY,
    }


def _resolved_locator_identity(locator: Any, manifest_path: Path) -> tuple[str, ...] | None:
    if not isinstance(locator, dict):
        return None
    kind = locator.get("kind")
    base = manifest_path.resolve().parent

    def resolved_path(value: Any) -> str | None:
        if not isinstance(value, str) or not value.strip():
            return None
        path = Path(value)
        return str((path if path.is_absolute() else base / path).resolve())

    try:
        if kind in ("snapshot", "retained"):
            path = resolved_path(locator.get("path"))
            return (kind, path) if path is not None else None
        if kind == "git":
            repo = resolved_path(locator.get("repo"))
            commit, path = locator.get("commit"), locator.get("path")
            if repo is None or not isinstance(commit, str) or not commit or not isinstance(path, str) or not path:
                return None
            return kind, repo, commit, path
    except (OSError, RuntimeError, TypeError, ValueError):
        return None
    return None


def _availability(record_value: str | Path, manifest_value: str | Path) -> dict[str, Any]:
    record, record_path = _read_json(record_value, "reproduction record")
    manifest_path = Path(manifest_value).expanduser().resolve()
    try:
        manifest = load_manifest(str(manifest_path))
    except (ManifestError, OSError) as error:
        raise SubmissionError(f"evidence manifest '{manifest_path}' is invalid: {error}") from None
    recorded_manifest_path: Path | None = None
    recorded_manifest = record.get("manifest")
    if isinstance(recorded_manifest, str) and recorded_manifest.strip():
        candidate = Path(recorded_manifest).expanduser()
        if candidate.is_absolute():
            try:
                recorded_manifest_path = candidate.resolve()
            except (OSError, RuntimeError, ValueError):
                recorded_manifest_path = None
    gaps: list[str] = []
    if record.get("schema") != RECORD_SCHEMA:
        gaps.append(f"reproduction record must use schema {RECORD_SCHEMA}")
    if record.get("result") != "pass":
        gaps.append("reproduction record result is not pass")
    if record.get("edition") != manifest.get("edition"):
        gaps.append("reproduction record edition does not match the evidence manifest")
    record_inputs = record.get("inputs")
    if not isinstance(record_inputs, list):
        record_inputs = []
        gaps.append("reproduction record is missing verified inputs")
    elif not record_inputs:
        gaps.append("reproduction record has no verified inputs")
    artifacts = {item["id"]: item for item in manifest["artifacts"]}
    input_ids: set[str] = set()
    verified_input_ids: set[str] = set()
    input_records: dict[str, dict[str, Any]] = {}
    input_record_indices: dict[str, int] = {}
    for input_index, item in enumerate(record_inputs):
        if not isinstance(item, dict) or not isinstance(item.get("artifact"), str) or not item["artifact"]:
            gaps.append("reproduction record contains a malformed input entry")
            continue
        artifact_id = item["artifact"]
        input_ids.add(artifact_id)
        if artifact_id in input_records:
            gaps.append(f"{artifact_id}: reproduction record contains duplicate input entries")
            continue
        input_records[artifact_id] = item
        input_record_indices[artifact_id] = input_index
        if item.get("status") != "verified":
            gaps.append(f"{artifact_id}: pinned input status is not verified")
            continue
        manifest_artifact = artifacts.get(artifact_id)
        if manifest_artifact is None:
            gaps.append(f"{artifact_id}: verified input is absent from the supplied evidence manifest")
            continue
        if item.get("sha256") != manifest_artifact["sha256"]:
            gaps.append(f"{artifact_id}: reproduction-record sha256 does not match the supplied manifest")
            continue
        if recorded_manifest_path is None:
            gaps.append(
                f"{artifact_id}: original manifest base is unavailable; cannot verify the recorded locator"
            )
            continue
        recorded_locator = _resolved_locator_identity(item.get("locator"), recorded_manifest_path)
        manifest_locator = _resolved_locator_identity(manifest_artifact.get("locator"), manifest_path)
        if recorded_locator is None:
            gaps.append(f"{artifact_id}: reproduction record is missing a valid verified-input locator")
            continue
        if recorded_locator != manifest_locator:
            gaps.append(f"{artifact_id}: reproduction-record locator does not match the supplied manifest")
            continue
        verified_input_ids.add(artifact_id)
    metadata = record.get("package_metadata", {}).get("artifacts") if isinstance(record.get("package_metadata"), dict) else None
    if not isinstance(metadata, list):
        metadata = []
        gaps.append("reproduction record is missing package_metadata.artifacts")
    metadata_ids: set[str] = set()
    field_rows: list[dict[str, Any]] = []
    statement_lines: list[str] = []
    for index, item in enumerate(metadata):
        if not isinstance(item, dict) or not isinstance(item.get("artifact"), str):
            gaps.append(f"package_metadata.artifacts[{index}]: missing artifact id")
            continue
        artifact_id = item["artifact"]
        metadata_ids.add(artifact_id)
        manifest_artifact = artifacts.get(artifact_id)
        if manifest_artifact is None:
            gaps.append(f"{artifact_id}: package metadata artifact is absent from the evidence manifest")
        input_record = input_records.get(artifact_id, {})
        input_index = input_record_indices.get(artifact_id)
        complete = artifact_id in verified_input_ids and manifest_artifact is not None
        values: dict[str, str] = {}
        for field in ("license", "dataset_id"):
            value = item.get(field)
            source = {
                "record": str(record_path),
                "json_pointer": f"/package_metadata/artifacts/{index}/{field}",
                "verified_input_json_pointer": f"/inputs/{input_index}" if input_index is not None else None,
                "verified_input_sha256": input_record.get("sha256"),
                "verified_input_locator": input_record.get("locator"),
                "evidence_manifest": str(manifest_path),
                "manifest_artifact": artifact_id if manifest_artifact is not None else None,
                "manifest_locator": manifest_artifact.get("locator") if manifest_artifact is not None else None,
                "locator": input_record.get("locator"),
            }
            field_rows.append({"artifact": artifact_id, "field": field, "value": value, "source": source})
            if not isinstance(value, str) or not value.strip():
                gaps.append(f"{artifact_id}: missing {field}")
                complete = False
            elif value.strip().casefold() == UNKNOWN or PLACEHOLDER.fullmatch(value.strip()):
                gaps.append(f"{artifact_id}: {field} is unknown or a placeholder ('{value.strip()}')")
                complete = False
            else:
                values[field] = value.strip()
        if complete:
            statement_lines.append(
                f"Artifact {artifact_id}: license {values['license']}; dataset identifier {values['dataset_id']}."
            )
    for artifact_id in sorted(input_ids - metadata_ids):
        gaps.append(f"{artifact_id}: missing package metadata (license and dataset_id)")
    for artifact_id in sorted(metadata_ids - input_ids):
        gaps.append(f"{artifact_id}: package metadata is not tied to a verified pinned input")
    statement = "\n".join(statement_lines)
    return {
        "schema": REPORT_SCHEMA, "status": "fail" if gaps else "pass",
        "statement": statement, "fields": field_rows, "gaps": gaps,
        "record": str(record_path), "evidence_manifest": str(manifest_path),
        "caveat": "This is a source-traced metadata statement only; it does not claim public availability or policy clearance.",
        "boundary": BOUNDARY,
    }


def _result_code(report: dict[str, Any]) -> int:
    return 0 if report.get("status") == "pass" else 1


def _emit(report: dict[str, Any]) -> int:
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return _result_code(report)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="submission", description="Story 016 submission-preparation checks and scaffolds")
    commands = parser.add_subparsers(dest="command", required=True)

    venue_parser = commands.add_parser("venue-check", help="run cited venue requirements against submission facts")
    venue_parser.add_argument("--venue", required=True)
    venue_parser.add_argument("--submission", required=True)
    venue_parser.add_argument("--figure-manifest")
    venue_parser.add_argument("--profiles")

    availability_parser = commands.add_parser("availability", help="generate source-traced data/code metadata statement")
    availability_parser.add_argument("--record", required=True)
    availability_parser.add_argument("--manifest", required=True)

    disclosure_parser = commands.add_parser("disclosure", help="generate the selected venue's AI disclosure scaffold")
    disclosure_parser.add_argument("--venue", required=True)
    disclosure_parser.add_argument("--usage", required=True)
    disclosure_parser.add_argument("--profiles")

    letter_parser = commands.add_parser("cover-letter", help="draft a cover letter from an approved Paper Plan")
    letter_parser.add_argument("--title", required=True)
    letter_parser.add_argument("--venue", required=True)
    letter_parser.add_argument("--plan")

    figures_parser = commands.add_parser("figure-check", help="inspect rendered figure files against a venue profile")
    figures_parser.add_argument("--venue", required=True)
    figures_parser.add_argument("--manifest", required=True)
    figures_parser.add_argument("--profiles")

    citations_parser = commands.add_parser("citation-check", help="name manuscript citation keys absent from its bibliography")
    citations_parser.add_argument("--tex", required=True)
    citations_parser.add_argument("--bib", required=True)

    args = parser.parse_args(argv)
    try:
        if args.command == "venue-check":
            result = venue_check(args.venue, args.submission, args.figure_manifest, args.profiles)
        elif args.command == "availability":
            result = _availability(args.record, args.manifest)
        elif args.command == "disclosure":
            result = disclosure(args.venue, args.usage, args.profiles)
        elif args.command == "cover-letter":
            result = cover_letter(args.title, args.venue, args.plan)
        elif args.command == "figure-check":
            result = _inspect_figures(args.venue, args.manifest, args.profiles)
        elif args.command == "citation-check":
            result = citation_check(args.tex, args.bib)
        else:  # pragma: no cover - argparse constrains this
            raise SubmissionError(f"unknown command '{args.command}'")
    except (SubmissionError, ManifestError, OSError) as error:
        return _emit({"schema": REPORT_SCHEMA, "status": "fail", "message": str(error), "boundary": BOUNDARY})
    except subprocess.TimeoutExpired as error:
        return _emit({"schema": REPORT_SCHEMA, "status": "fail",
                      "message": f"external PDF inspection timed out: {error}", "boundary": BOUNDARY})
    return _emit(result)


if __name__ == "__main__":
    raise SystemExit(main())
