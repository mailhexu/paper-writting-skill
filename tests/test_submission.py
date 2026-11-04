from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

import pymupdf
ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "paper-writing-skill" / "tools"
TOOL = TOOLS / "submission.py"
PYTHON = sys.executable


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([PYTHON, str(TOOL), *args], capture_output=True, text=True, timeout=60)


def write_json(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")
    return path




def render_pdf(path: Path, width_mm: float = 86, title: str | None = None,
               panel_label: bool = True) -> None:
    fig, ax = plt.subplots(figsize=(width_mm / 25.4, 2.2))
    ax.plot([0, 1], [0, 1], color="#0072B2", linewidth=1.2)
    ax.set_xlabel("Dimensionless x")
    ax.set_ylabel("Dimensionless y")
    if title:
        fig.suptitle(title)
    if panel_label:
        fig.text(0.03, 0.91, "(a)", fontfamily="DejaVu Sans", fontweight="bold", fontsize=8)
    fig.savefig(path, format="pdf")
    plt.close(fig)

def render_grid_pdf(path: Path) -> dict[str, list[float]]:
    fig, axes = plt.subplots(2, 2, figsize=(3.4, 3.0))
    regions = {}
    for label, ax in zip("abcd", axes.flat):
        ax.plot([0, 1], [0, 1], color="#0072B2", linewidth=1.2)
        ax.set_xlabel("Dimensionless x")
        ax.set_ylabel("Dimensionless y")
        ax.text(0.03, 0.82, f"({label})", transform=ax.transAxes,
                fontfamily="DejaVu Sans", fontweight="bold", fontsize=8)
        x, y, width, height = ax.get_position().bounds
        regions[label] = [x, 1 - y - height, x + width, 1 - y]
    fig.savefig(path, format="pdf")
    plt.close(fig)
    return regions


def render_small_ordinary_text_pdf(path: Path, fontsize: float = 6) -> None:
    fig, ax = plt.subplots(figsize=(86 / 25.4, 2.2))
    ax.plot([0, 1], [0, 1], color="#0072B2", linewidth=1.2)
    ax.set_xlabel("Normal x", fontsize=8)
    ax.set_ylabel("Normal y", fontsize=8)
    fig.text(0.5, 0.2, "Small ordinary text", ha="center", fontsize=fontsize, fontfamily="DejaVu Sans")
    ax.text(0.03, 0.91, "(a)", transform=ax.transAxes, fontfamily="DejaVu Sans",
            fontweight="bold", fontsize=8)
    fig.savefig(path, format="pdf")
    plt.close(fig)


def report(result: subprocess.CompletedProcess[str]) -> dict:
    assert result.stdout, result.stderr
    return json.loads(result.stdout)


def test_venue_check_lists_cited_requirements_and_fails_missing_or_over_limit_fields(tmp_path):
    submission = write_json(tmp_path / "submission.json", {
        "article_type": "letter",
        "word_count": 4501,
        "body_stands_alone_without_supplement": True,
        "current_policy_checked_on": "2026-10-24",
        "current_policy_rechecked": True,
    })
    result = run_cli("venue-check", "--venue", "prb", "--submission", str(submission))
    output = report(result)

    assert result.returncode == 1
    assert output["status"] == "fail"
    assert {item["status"] for item in output["checks"]} == {"pass", "fail"}
    assert any(item["id"] == "word-limit" and "4500" in item["detail"]
               for item in output["checks"] if item["status"] == "fail")
    assert all(item["source"]["url"] for item in output["checks"])
    assert any(item["id"] == "ai-disclosure" and item["status"] == "fail"
               for item in output["checks"])

def test_venue_fixture_requires_review_when_title_absence_is_inconclusive(tmp_path):
    figure = tmp_path / "figure.pdf"
    render_pdf(figure)
    figure_manifest = write_json(tmp_path / "figures.json", {
        "figures": [{
            "path": figure.name, "column": "single", "panels": ["a"],
            "panel_regions": {"a": [0, 0, 1, 1]},
        }]
    })
    submission = write_json(tmp_path / "submission.json", {
        "article_type": "regular_article",
        "word_count": 5200,
        "body_stands_alone_without_supplement": True,
        "current_policy_checked_on": "2026-10-24",
        "current_policy_rechecked": True,
        "ai_use": "none",
    })
    result = run_cli("venue-check", "--venue", "prb", "--submission", str(submission),
                     "--figure-manifest", str(figure_manifest))
    output = report(result)

    assert result.returncode == 1
    assert output["status"] == "manual-required"
    assert all(item["status"] != "fail" for item in output["checks"])
    assert any(item["id"] == "figure-files" and item["status"] == "manual-required"
               for item in output["checks"])
    assert all(item["source"]["url"] for item in output["checks"])


def test_unknown_venue_fails_without_falling_back_to_another_regime(tmp_path):
    submission = write_json(tmp_path / "submission.json", {})
    result = run_cli("venue-check", "--venue", "unknown-journal", "--submission", str(submission))
    output = report(result)

    assert result.returncode == 1
    assert output["status"] == "fail"
    assert "unknown venue" in output["checks"][0]["detail"].lower()
    assert "no default" in output["checks"][0]["detail"].lower()

def test_venue_check_rejects_malformed_counts_and_declaration_types(tmp_path):
    base = {
        "word_count": 120,
        "data_statement": "Data are available in the repository.",
        "central_custom_code": True,
        "code_statement": "Code is available in the repository.",
        "supplementary_methods": False,
        "figure_legend_words": 80,
        "current_policy_checked_on": "2026-10-24",
        "current_policy_rechecked": True,
        "ai_use": "none",
    }
    cases = [
        ("word_count", -1, "word-count-recorded"),
        ("word_count", {}, "word-count-recorded"),
        ("data_statement", False, "data-statement"),
        ("code_statement", [], "central-code"),
    ]
    for index, (field, value, check_id) in enumerate(cases):
        submission = write_json(tmp_path / f"malformed-{index}.json", {**base, field: value})
        result = run_cli("venue-check", "--venue", "npj", "--submission", str(submission))
        output = report(result)
        checks = {item["id"]: item for item in output["checks"]}
        assert result.returncode == 1
        assert checks[check_id]["status"] == "fail"


def test_unhashable_article_type_returns_structured_failure(tmp_path):
    submission = write_json(tmp_path / "submission.json", {
        "article_type": [],
        "word_count": 100,
        "body_stands_alone_without_supplement": True,
        "current_policy_checked_on": "2026-10-24",
        "current_policy_rechecked": True,
        "ai_use": "none",
    })

    result = run_cli("venue-check", "--venue", "prb", "--submission", str(submission))
    output = report(result)
    checks = {item["id"]: item for item in output["checks"]}

    assert result.returncode == 1
    assert checks["article-type"]["status"] == "fail"
    assert checks["word-limit"]["status"] == "fail"


def test_availability_statement_traces_record_fields_and_names_missing_metadata(tmp_path):
    manifest_path = tmp_path / "evidence-manifest.yaml"
    manifest_path.write_text(
        "edition: fixture-edition\n"
        "artifacts:\n"
        "  - id: dataset\n    sha256: " + "a" * 64 + "\n"
        "    locator: {kind: retained, path: dataset.csv}\n"
        "  - id: analysis-code\n    sha256: " + "b" * 64 + "\n"
        "    locator: {kind: git, repo: research-repository, commit: " + "c" * 40 + ", path: analysis.py}\n"
        "claims:\n"
        "  - id: claim-1\n    statement: Fixture claim.\n    artifacts: [dataset]\n"
        "    intent: test provenance\n    judgment: support\n    reason: fixture evidence\n",
        encoding="utf-8",
    )
    record_path = write_json(tmp_path / "repro-record.json", {
        "schema": "pws.repro-record/1",
        "edition": "fixture-edition",
        "result": "pass",
        "manifest": str(manifest_path.resolve()),
        "inputs": [
            {"artifact": "dataset", "status": "verified", "sha256": "a" * 64,
             "path": "clean/data.csv", "locator": {"kind": "retained", "path": "dataset.csv"}},
            {"artifact": "analysis-code", "status": "verified", "sha256": "b" * 64,
             "path": "clean/analysis.py",
             "locator": {"kind": "git", "repo": "research-repository", "commit": "c" * 40, "path": "analysis.py"}},
        ],
        "package_metadata": {"artifacts": [
            {"artifact": "dataset", "license": "CC BY 4.0", "dataset_id": "10.5281/zenodo.fixture"},
            {"artifact": "analysis-code", "license": "MIT", "dataset_id": "not-applicable-private"},
        ]},
    })

    result = run_cli("availability", "--record", str(record_path), "--manifest", str(manifest_path))
    output = report(result)

    assert result.returncode == 0
    assert output["status"] == "pass"
    assert "10.5281/zenodo.fixture" in output["statement"]
    assert "CC BY 4.0" in output["statement"]
    assert all(item["source"]["record"].endswith("repro-record.json") for item in output["fields"])
    assert output["fields"][0]["source"]["verified_input_sha256"] == "a" * 64
    assert output["fields"][0]["source"]["locator"] == {"kind": "retained", "path": "dataset.csv"}

    empty_record = write_json(tmp_path / "empty-record.json", {
        "schema": "pws.repro-record/1", "edition": "fixture-edition", "result": "pass",
        "inputs": [], "package_metadata": {"artifacts": []},
    })
    empty = report(run_cli("availability", "--record", str(empty_record), "--manifest", str(manifest_path)))
    assert empty["status"] == "fail"
    assert any("no verified inputs" in gap for gap in empty["gaps"])

    record = json.loads(record_path.read_text(encoding="utf-8"))
    manifest_original = manifest_path.read_text(encoding="utf-8")
    record["inputs"][0]["sha256"] = "d" * 64
    write_json(record_path, record)
    bad_hash = report(run_cli("availability", "--record", str(record_path), "--manifest", str(manifest_path)))
    assert bad_hash["status"] == "fail"
    assert any("dataset" in gap and "sha256" in gap for gap in bad_hash["gaps"])
    assert "Artifact dataset:" not in bad_hash["statement"]

    record["inputs"][0]["sha256"] = "a" * 64
    write_json(record_path, record)
    manifest_path.write_text(manifest_original.replace("path: dataset.csv", "path: moved-dataset.csv"),
                             encoding="utf-8")
    bad_locator = report(run_cli("availability", "--record", str(record_path), "--manifest", str(manifest_path)))
    assert bad_locator["status"] == "fail"
    assert any("dataset" in gap and "locator" in gap for gap in bad_locator["gaps"])
    assert "Artifact dataset:" not in bad_locator["statement"]
    manifest_path.write_text(manifest_original, encoding="utf-8")

    record["package_metadata"]["artifacts"][0].pop("license")
    record["package_metadata"]["artifacts"][1]["dataset_id"] = "unknown"
    write_json(record_path, record)
    failed = run_cli("availability", "--record", str(record_path), "--manifest", str(manifest_path))
    failed_output = report(failed)

    assert failed.returncode == 1
    assert failed_output["status"] == "fail"
    assert any("dataset" in gap and "license" in gap for gap in failed_output["gaps"])
    assert any("analysis-code" in gap and "dataset_id" in gap for gap in failed_output["gaps"])
    assert "TODO" not in failed_output["statement"]
    assert "<" not in failed_output["statement"]

def test_availability_resolves_recorded_relative_locator_from_original_manifest(tmp_path):
    old_dir = tmp_path / "old"
    new_dir = tmp_path / "new"
    old_manifest = old_dir / "evidence.yaml"
    new_manifest = new_dir / "evidence.yaml"

    def write_manifest(path: Path, locator: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "edition: fixture-edition\n"
            "artifacts:\n"
            "  - id: dataset\n"
            f"    sha256: {'a' * 64}\n"
            f"    locator: {{kind: retained, path: {json.dumps(locator)}}}\n"
            "claims:\n"
            "  - id: claim-1\n    statement: Fixture claim.\n    artifacts: [dataset]\n"
            "    intent: test provenance\n    judgment: support\n    reason: fixture evidence\n",
            encoding="utf-8",
        )

    write_manifest(old_manifest, "data.csv")
    write_manifest(new_manifest, "data.csv")
    record_path = write_json(tmp_path / "repro-record.json", {
        "schema": "pws.repro-record/1",
        "edition": "fixture-edition",
        "result": "pass",
        "manifest": str(old_manifest.resolve()),
        "inputs": [{
            "artifact": "dataset",
            "status": "verified",
            "sha256": "a" * 64,
            "path": "clean/data.csv",
            "locator": {"kind": "retained", "path": "data.csv"},
        }],
        "package_metadata": {"artifacts": [{
            "artifact": "dataset", "license": "CC BY 4.0", "dataset_id": "10.5281/zenodo.fixture",
        }]},
    })

    relocated = report(run_cli(
        "availability", "--record", str(record_path), "--manifest", str(new_manifest),
    ))
    assert relocated["status"] == "fail"
    assert any("dataset" in gap and "locator" in gap for gap in relocated["gaps"])
    assert "Artifact dataset:" not in relocated["statement"]

    write_manifest(new_manifest, str(old_dir / "data.csv"))
    absolute_match = report(run_cli(
        "availability", "--record", str(record_path), "--manifest", str(new_manifest),
    ))
    assert absolute_match["status"] == "pass"
    assert "Artifact dataset:" in absolute_match["statement"]

    record = json.loads(record_path.read_text(encoding="utf-8"))
    record.pop("manifest")
    write_json(record_path, record)
    missing_origin = report(run_cli(
        "availability", "--record", str(record_path), "--manifest", str(new_manifest),
    ))
    assert missing_origin["status"] == "fail"
    assert any("original manifest base is unavailable" in gap for gap in missing_origin["gaps"])
    assert "Artifact dataset:" not in missing_origin["statement"]
    record["manifest"] = "old/evidence.yaml"
    write_json(record_path, record)
    relative_origin = report(run_cli(
        "availability", "--record", str(record_path), "--manifest", str(new_manifest),
    ))
    assert relative_origin["status"] == "fail"
    assert any("original manifest base is unavailable" in gap for gap in relative_origin["gaps"])



def test_ai_disclosure_uses_each_venue_regime_and_unknown_venue_is_explicit(tmp_path):
    usage = write_json(tmp_path / "ai-use.json", {
        "use": "substantive",
        "tools": [{"name": "Example Assistant", "model": "Model 1"}],
        "purpose": "language organization",
        "human_review": "The authors verified and edited the generated text.",
        "placement": "Methods",
        "responsibility_statement": "The authors retain responsibility for all content.",
    })
    prb = report(run_cli("disclosure", "--venue", "prb", "--usage", str(usage)))
    npj = report(run_cli("disclosure", "--venue", "npj", "--usage", str(usage)))
    unknown_result = run_cli("disclosure", "--venue", "unknown-journal", "--usage", str(usage))
    unknown = report(unknown_result)

    assert prb["status"] == npj["status"] == "pass"
    assert prb["text"] != npj["text"]
    assert "Example Assistant" in prb["text"] and "responsibility" in prb["text"].lower()
    assert "Methods" in npj["text"] and "language organization" in npj["text"]
    assert unknown_result.returncode == 1
    assert "verify the current policy" in unknown["text"].lower()
    assert "no default" in unknown["text"].lower()

def test_cpc_check_and_disclosure_reject_unmapped_ai_categories(tmp_path):
    base = {
        "article_type": "computational_physics",
        "current_policy_checked_on": "2026-10-24",
        "current_policy_rechecked": True,
    }
    missing_use = write_json(tmp_path / "missing-use.json", base)
    missing = report(run_cli("venue-check", "--venue", "cpc", "--submission", str(missing_use)))
    missing_ai = next(item for item in missing["checks"] if item["id"] == "ai-disclosure")
    assert missing_ai["status"] == "fail"
    assert "ai_use" in missing_ai["detail"]

    unmapped_use = write_json(tmp_path / "unmapped-use.json", {**base, "ai_use": "substantive"})
    unmapped = report(run_cli("venue-check", "--venue", "cpc", "--submission", str(unmapped_use)))
    assert next(item for item in unmapped["checks"] if item["id"] == "ai-disclosure")["status"] == "fail"

    declared_use = write_json(tmp_path / "declared-use.json", {
        **base, "ai_use": "manuscript_preparation", "ai_disclosure": True,
    })
    declared = report(run_cli("venue-check", "--venue", "cpc", "--submission", str(declared_use)))
    assert next(item for item in declared["checks"] if item["id"] == "ai-disclosure")["status"] == "pass"

    usage = write_json(tmp_path / "cpc-ai-use.json", {
        "use": "substantive",
        "tools": [{"name": "Example Assistant", "model": "Model 1"}],
        "purpose": "manuscript preparation",
        "human_review": "The authors verified all generated text.",
        "placement": "Methods",
        "responsibility_statement": "The authors retain responsibility.",
    })
    rejected = run_cli("disclosure", "--venue", "cpc", "--usage", str(usage))
    assert rejected.returncode == 1
    assert "not mapped" in report(rejected)["message"]

    usage_path = write_json(usage, {**json.loads(usage.read_text(encoding="utf-8")),
                                    "use": "manuscript_preparation"})
    accepted = report(run_cli("disclosure", "--venue", "cpc", "--usage", str(usage_path)))
    assert accepted["status"] == "pass"
    assert "Example Assistant" in accepted["text"]


def test_cover_letter_refuses_unapproved_or_missing_plan_and_maps_each_contribution(tmp_path):
    missing = report(run_cli("cover-letter", "--title", "Fixture paper", "--venue", "PRB"))
    assert missing["status"] == "fail"
    assert "approved Paper Plan" in missing["message"]

    plan_path = write_json(tmp_path / "paper-plan.json", {
        "schema": "pws.paper-plan/1",
        "status": "draft",
        "source": "fixture://synthetic-approved-plan",
        "contributions": ["Contribution one"],
    })
    unapproved = run_cli("cover-letter", "--title", "Fixture paper", "--venue", "PRB",
                         "--plan", str(plan_path))
    assert unapproved.returncode == 1
    assert "not approved" in report(unapproved)["message"].lower()

    plan_path = write_json(plan_path, {
        "schema": "pws.paper-plan/1",
        "status": "approved",
        "contributions": ["Contribution one", "Contribution two"],
        "source": "fixture://synthetic-approved-plan",
    })
    result = run_cli("cover-letter", "--title", "Fixture paper", "--venue", "PRB",
                     "--plan", str(plan_path))
    output = report(result)
    assert result.returncode == 0
    assert output["status"] == "pass"
    assert output["contributions"] == ["Contribution one", "Contribution two"]
    assert output["draft"].count("Contribution:") == 2


def test_figure_check_inspects_real_rendered_pdf_and_reports_each_defect(tmp_path):
    good_pdf = tmp_path / "figure-good.pdf"
    render_pdf(good_pdf)
    good_manifest = write_json(tmp_path / "good-figures.json", {
        "figures": [{
            "path": good_pdf.name, "column": "single", "panels": ["a"],
            "panel_regions": {"a": [0, 0, 1, 1]},
        }]
    })
    good = run_cli("figure-check", "--venue", "prb", "--manifest", str(good_manifest))
    good_output = report(good)

    assert good.returncode == 1, good.stderr
    assert good_output["status"] == "manual-required"
    checks = {item["id"]: item for item in good_output["figures"][0]["checks"]}
    assert checks["embedded-title"]["status"] == "manual-required"
    assert checks["panel-placement"]["status"] == "pass"
    assert all(item["status"] != "fail" for item in good_output["figures"][0]["checks"])
    assert {"physical-width", "font-family", "panel-labels", "embedded-title", "format"} <= set(checks)

    bad_pdf = tmp_path / "figure-bad.pdf"
    render_pdf(bad_pdf, width_mm=105, title="Embedded figure title", panel_label=False)
    bad_manifest = write_json(tmp_path / "bad-figures.json", {
        "figures": [{
            "path": bad_pdf.name, "column": "single", "panels": ["a"],
            "panel_regions": {"a": [0, 0, 1, 1]},
        }]
    })
    bad = run_cli("figure-check", "--venue", "prb", "--manifest", str(bad_manifest))
    bad_output = report(bad)

    assert bad.returncode == 1
    checks = {item["id"]: item for item in bad_output["figures"][0]["checks"]}
    assert checks["physical-width"]["status"] == "fail"
    assert checks["panel-labels"]["status"] == "fail"
    assert checks["embedded-title"]["status"] == "fail"


def test_unflagged_lowered_six_point_subscript_requires_manual_review(tmp_path):
    figure = tmp_path / "six-point-subscript.pdf"
    document = pymupdf.open()
    page = document.new_page(width=86 / 25.4 * 72, height=180)
    page.insert_text((18, 40), "Dimensionless x", fontname="helv", fontsize=8)
    page.insert_text((100, 40), "x", fontname="helv", fontsize=8)
    page.insert_text((106, 43), "i", fontname="helv", fontsize=6)
    document.save(figure)
    document.close()

    document = pymupdf.open(figure)
    spans = [
        span for block in document[0].get_text("dict")["blocks"]
        for line in block.get("lines", [])
        for span in line.get("spans", [])
        if span.get("text") == "i"
    ]
    assert len(spans) == 1
    assert abs(float(spans[0]["size"]) - 6) < 0.1
    assert not int(spans[0].get("flags", 0)) & 1
    document.close()

    manifest = write_json(tmp_path / "six-point-subscript.json", {
        "figures": [{"path": figure.name, "column": "single", "panels": []}]
    })
    output = report(run_cli("figure-check", "--venue", "prb", "--manifest", str(manifest)))
    size_check = next(item for item in output["figures"][0]["checks"]
                      if item["id"] == "print-size-legibility")

    assert size_check["status"] == "manual-required"
    assert "unclassified 6–7 pt spans need role review" in size_check["detail"]


def test_png_figure_never_claims_semantic_checks_as_pass(tmp_path):
    figure = tmp_path / "figure.png"
    fig, ax = plt.subplots(figsize=(86 / 25.4, 2.2))
    ax.plot([0, 1], [0, 1], color="#0072B2", linewidth=1.2)
    fig.savefig(figure, format="png", dpi=500)
    plt.close(fig)
    manifest = write_json(tmp_path / "figures.json", {
        "figures": [{"path": figure.name, "column": "single", "panels": ["a"]}]
    })

    result = run_cli("figure-check", "--venue", "prb", "--manifest", str(manifest))
    output = report(result)

    assert result.returncode == 1
    assert output["status"] == "manual-required"
    assert output["figures"][0]["status"] == "manual-required"
    checks = {item["id"]: item["status"] for item in output["figures"][0]["checks"]}
    assert checks["physical-width"] == checks["resolution"] == "pass"
    assert checks["panel-labels"] == checks["embedded-title"] == "manual-required"
    assert output["human_visual_reading"].startswith("required")



def test_panel_labels_use_panel_relative_bounds_for_lower_row(tmp_path):
    figure = tmp_path / "grid.pdf"
    regions = render_grid_pdf(figure)
    manifest = write_json(tmp_path / "grid.json", {
        "figures": [{
            "path": figure.name, "column": "single", "panels": list("abcd"),
            "panel_regions": regions,
        }]
    })

    output = report(run_cli("figure-check", "--venue", "prb", "--manifest", str(manifest)))
    checks = {item["id"]: item for item in output["figures"][0]["checks"]}

    assert checks["panel-labels"]["status"] == "pass"
    assert checks["panel-placement"]["status"] == "pass"
    assert output["status"] == "manual-required"


def test_short_title_absence_is_not_certified_by_text_length_heuristic(tmp_path):
    figure = tmp_path / "short-title.pdf"
    render_pdf(figure, title="DOS")
    manifest = write_json(tmp_path / "short-title.json", {
        "figures": [{
            "path": figure.name, "column": "single", "panels": ["a"],
            "panel_regions": {"a": [0, 0, 1, 1]},
        }]
    })

    output = report(run_cli("figure-check", "--venue", "prb", "--manifest", str(manifest)))
    title_check = next(item for item in output["figures"][0]["checks"] if item["id"] == "embedded-title")

    assert output["status"] == "manual-required"
    assert title_check["status"] == "manual-required"
    assert "short or left-aligned" in title_check["detail"]


def test_unclassified_six_point_text_requires_manual_role_review(tmp_path):
    figure = tmp_path / "small-ordinary-text.pdf"
    render_small_ordinary_text_pdf(figure)
    manifest = write_json(tmp_path / "small-text.json", {
        "figures": [{
            "path": figure.name, "column": "single", "panels": ["a"],
            "panel_regions": {"a": [0, 0, 1, 1]},
        }]
    })

    output = report(run_cli("figure-check", "--venue", "prb", "--manifest", str(manifest)))
    size_check = next(item for item in output["figures"][0]["checks"] if item["id"] == "print-size-legibility")

    assert size_check["status"] == "manual-required"
    assert "unclassified 6–7 pt spans need role review" in size_check["detail"]


def test_text_below_absolute_six_point_floor_fails(tmp_path):
    figure = tmp_path / "below-six-point.pdf"
    render_small_ordinary_text_pdf(figure, fontsize=5.5)
    manifest = write_json(tmp_path / "below-six-point.json", {
        "figures": [{
            "path": figure.name, "column": "single", "panels": ["a"],
            "panel_regions": {"a": [0, 0, 1, 1]},
        }]
    })

    output = report(run_cli("figure-check", "--venue", "prb", "--manifest", str(manifest)))
    size_check = next(item for item in output["figures"][0]["checks"]
                      if item["id"] == "print-size-legibility")

    assert size_check["status"] == "fail"
    assert "absolute 6 pt minimum" in size_check["detail"]


def test_pdf_print_size_stays_manual_when_extracted_text_meets_floor(tmp_path):
    figure = tmp_path / "readable-size.pdf"
    fig, ax = plt.subplots(figsize=(86 / 25.4, 2.2))
    ax.plot([0, 1], [0, 1], color="#0072B2", linewidth=1.2)
    ax.set_xlabel("Dimensionless x", fontsize=8)
    ax.set_ylabel("Dimensionless y", fontsize=8)
    fig.savefig(figure, format="pdf")
    plt.close(fig)
    manifest = write_json(tmp_path / "readable-size.json", {
        "figures": [{"path": figure.name, "column": "single", "panels": []}]
    })

    output = report(run_cli("figure-check", "--venue", "prb", "--manifest", str(manifest)))
    size_check = next(item for item in output["figures"][0]["checks"]
                      if item["id"] == "print-size-legibility")

    assert size_check["status"] == "manual-required"
    assert "completeness is not verified" in size_check["detail"]


def test_valid_viridis_vector_colormap_requires_inspection_not_false_failure(tmp_path):
    figure = tmp_path / "viridis.pdf"
    fig, ax = plt.subplots(figsize=(86 / 25.4, 2.2))
    ax.scatter([0, 0.5, 1], [0.2, 0.8, 0.4], c=[0, 0.5, 1], cmap="viridis")
    ax.set_xlabel("Dimensionless x", fontsize=8)
    ax.set_ylabel("Dimensionless y", fontsize=8)
    fig.savefig(figure, format="pdf")
    plt.close(fig)
    manifest = write_json(tmp_path / "viridis.json", {
        "figures": [{"path": figure.name, "column": "single", "panels": []}]
    })

    output = report(run_cli("figure-check", "--venue", "prb", "--manifest", str(manifest)))
    colors = next(item for item in output["figures"][0]["checks"] if item["id"] == "color-palette")

    assert colors["status"] == "manual-required"
    assert output["status"] == "manual-required"


def test_pdf_raster_images_are_checked_for_resolution_and_visual_color(tmp_path):
    figure = tmp_path / "low-resolution-image.pdf"
    fig, ax = plt.subplots(figsize=(86 / 25.4, 2.2))
    ax.imshow([[0, 1], [1, 0]], cmap="viridis", interpolation="nearest")
    ax.set_xlabel("Dimensionless x")
    ax.set_ylabel("Dimensionless y")
    fig.savefig(figure, format="pdf")
    plt.close(fig)
    manifest = write_json(tmp_path / "raster.json", {
        "figures": [{"path": figure.name, "column": "single", "panels": []}]
    })

    output = report(run_cli("figure-check", "--venue", "prb", "--manifest", str(manifest)))
    checks = {item["id"]: item for item in output["figures"][0]["checks"]}

    assert checks["resolution"]["status"] == "fail"
    assert checks["raster-color-inspection"]["status"] == "manual-required"


def test_inline_pdf_image_is_not_mistaken_for_vector_only_pdf(tmp_path):
    figure = tmp_path / "inline-image.pdf"
    document = pymupdf.open()
    page = document.new_page(width=300, height=220)
    page.draw_line((0, 0), (1, 1))
    content_xref = page.get_contents()[0]
    document.update_stream(
        content_xref,
        b"q 100 0 0 100 50 50 cm BI /W 1 /H 1 /CS /RGB /BPC 8 ID \xff\x00\x00 EI Q",
    )
    document.save(figure)
    document.close()

    document = pymupdf.open(figure)
    page = document[0]
    assert not page.get_images(full=True)
    assert page.get_image_info(xrefs=True)
    document.close()

    manifest = write_json(tmp_path / "inline-image.json", {
        "figures": [{"path": figure.name, "column": "single", "panels": []}]
    })
    output = report(run_cli("figure-check", "--venue", "prb", "--manifest", str(manifest)))
    checks = {item["id"]: item for item in output["figures"][0]["checks"]}

    assert checks["resolution"]["status"] == "fail"
    assert checks["raster-color-inspection"]["status"] == "manual-required"
def test_citation_check_names_missing_key_without_modifying_bibliography(tmp_path):
    tex = tmp_path / "main.tex"
    tex.write_text(
        "% \\cite{commented-out}\nText \\cite[see][p. 4]{known,missing}.\n",
        encoding="utf-8",
    )
    bib = tmp_path / "refs.bib"
    bib.write_text("@article{known, title={Known entry}}\n", encoding="utf-8")
    original = bib.read_bytes()

    result = run_cli("citation-check", "--tex", str(tex), "--bib", str(bib))
    output = report(result)

    assert result.returncode == 1
    assert "missing" in output["missing_keys"]
    assert "known" not in output["missing_keys"]
    assert "metadata agreement does not establish scientific support" in output["caveat"].lower()
    assert bib.read_bytes() == original

def test_lowercase_and_multicite_commands_check_every_citation_group(tmp_path):
    tex = tmp_path / "main.tex"
    tex.write_text(
        r"% \parencite{commented}" "\n"
        r"\parencite{known} \textcite{missing-lower} "
        r"\cites[see]{known}[also][p. 2]{missing-multi}" "\n",
        encoding="utf-8",
    )
    bib = tmp_path / "refs.bib"
    bib.write_text("@article{known, title={Known entry}}\n", encoding="utf-8")
    original = bib.read_bytes()

    result = run_cli("citation-check", "--tex", str(tex), "--bib", str(bib))
    output = report(result)

    assert result.returncode == 1
    assert output["missing_keys"] == ["missing-lower", "missing-multi"]
    assert bib.read_bytes() == original


def test_bibliography_check_uses_real_verifier_without_writes_and_selects_exact_key(tmp_path):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    bib = inputs / "references.bib"
    bib.write_text(
        "@article{alpha,doi={10.1/alpha},title={Alpha paper},author={Doe, Jane},year={2020}}\n"
        "@article{beta,doi={10.1/beta},title={Beta paper},author={Doe, Jane},year={2020}}\n"
        "@article{local,title={Local record}}\n"
        "@article{absent,doi={10.1/absent},title={Absent paper}}\n"
        "@article{broken,doi={10.1/broken},title={Broken paper}}\n",
        encoding="utf-8",
    )
    for name in ("references_fixed.bib", "references_order_changed.bib", "references_cache.json"):
        (inputs / name).write_bytes(b"author-owned sidecar")
    before = {path.name: path.read_bytes() for path in inputs.iterdir()}
    responses = {
        "https://doi.org/10.1/alpha": {
            "status": 200,
            "text": "@article{remote,doi={10.1/alpha},title={Alpha paper},author={Doe, Jane},year={2021}}",
        },
        "https://doi.org/10.1/beta": {
            "status": 200,
            "text": "@article{remote,doi={10.1/beta},title={Beta paper},author={Doe, Jane},year={2020}}",
        },
        "https://doi.org/10.1/absent": {"status": 404},
        "https://doi.org/10.1/broken": None,
    }
    calls = tmp_path / "provider-calls.txt"
    bootstrap = """
import json
import runpy
import sys
from pathlib import Path
from unittest.mock import Mock
import requests
responses = json.loads(sys.argv[1])
calls = Path(sys.argv[2])
sys.argv = sys.argv[3:]
def controlled_get(url, **kwargs):
    with calls.open("a", encoding="utf-8") as stream:
        stream.write(url + "\\n")
    record = responses[url]
    if record is None:
        raise requests.exceptions.Timeout("controlled provider failure")
    return Mock(status_code=record["status"], text=record.get("text", ""))
requests.get = controlled_get
runpy.run_path(sys.argv[0], run_name="__main__")
"""

    def verify(*selection):
        calls.write_text("", encoding="utf-8")
        result = subprocess.run(
            [PYTHON, "-c", bootstrap, json.dumps(responses), str(calls), str(TOOL),
             "bibliography-check", "--bib", str(bib), *selection],
            capture_output=True, text=True, timeout=60,
        )
        output = report(result)
        assert {path.name: path.read_bytes() for path in inputs.iterdir()} == before
        return result, output, calls.read_text(encoding="utf-8").splitlines()

    result, whole, requested = verify()
    assert result.returncode == 1
    assert whole["status"] == "fail"
    assert whole["verification"]["outcome"] == "unverifiable"
    entries = whole["verification"]["entries"]
    assert [entry["key"] for entry in entries] == ["alpha", "beta", "local", "absent", "broken"]
    assert entries[0]["differences"] == [{"field": "year", "original": "2020", "proposed": "2021"}]
    assert [entry["reason"] for entry in entries[2:]] == [
        "missing_identifier", "no_match", "query_failure",
    ]
    assert requested == list(responses)

    result, selected, requested = verify("--key", "alpha")
    assert result.returncode == 1
    assert selected["verification"]["outcome"] == "differences"
    assert [entry["key"] for entry in selected["verification"]["entries"]] == ["alpha"]
    assert selected["verification"]["entries"][0]["differences"] == entries[0]["differences"]
    assert requested == ["https://doi.org/10.1/alpha"]

    result, clean, requested = verify("--key", "beta")
    assert result.returncode == 0
    assert clean["status"] == "pass"
    assert clean["verification"]["outcome"] == "clean"
    assert requested == ["https://doi.org/10.1/beta"]

    result, invalid, requested = verify("--key", "Alpha")
    assert result.returncode == 1
    assert invalid["status"] == "fail"
    assert invalid["verification"]["error"]["code"] == "selection_error"
    assert requested == []
