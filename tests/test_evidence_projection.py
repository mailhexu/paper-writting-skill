"""Story 008: evidence metadata TeX projection (real pdflatex smoke included)."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

import pytest

TOOLS = Path(__file__).resolve().parents[1] / "paper-writing-skill" / "tools"
sys.path.insert(0, str(TOOLS))

import evidence_projection as ep  # noqa: E402

PYTHON = sys.executable
TOOL = str(TOOLS / "evidence_projection.py")
COMMIT = "a" * 40

MANIFEST = """\
edition: "2026-10-19-draft1"
artifacts:
  - id: tb2j-run-42
    sha256: "{sha}"
    locator:
      kind: git
      repo: "./repo"
      commit: {commit}
      path: "runs_42 #1 %v2 out.dat"
  - id: note-snapshot
    sha256: "{sha}"
    locator:
      kind: snapshot
      path: "snapshots/note with spaces.dat"
claims:
  - id: claim-lifetimes
    statement: "Magnon lifetimes agree within 5 percent."
    intent: "isolate the contribution"
    reason: "independent TB2J extraction"
    artifacts: ["tb2j-run-42", "note-snapshot"]
    judgment: support
"""

DRAFT = """\\documentclass{article}
\\usepackage[colorlinks=true,urlcolor=blue,linkcolor=blue]{hyperref}
\\input{evidence-metadata.tex}
\\begin{document}
Magnon lifetimes agree within five percent (see evidence).
\\evidenceblock{tb2j-run-42}
\\evidenceblock{claim-lifetimes}
Data availability: all runs are archived (public statement, kept by export).
\\end{document}
"""


def write_project(tmp_path: Path, manifest: str, draft: str) -> Path:
    (tmp_path / "evidence-manifest.yaml").write_text(manifest, encoding="utf-8")
    (tmp_path / "draft.tex").write_text(draft, encoding="utf-8")
    for artifact in ep.yaml.safe_load(manifest)["artifacts"]:
        locator = artifact["locator"]
        path = (tmp_path / locator["repo"] / locator["path"]
                if locator["kind"] == "git" else tmp_path / locator["path"])
        assert path.is_relative_to(tmp_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"adopted bytes")
    return tmp_path


def run_cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [PYTHON, TOOL, *args], cwd=cwd, capture_output=True, text=True, timeout=60
    )


def generate(tmp_path: Path, extra_args: tuple[str, ...] = ()) -> subprocess.CompletedProcess:
    return run_cli(
        "generate", "evidence-manifest.yaml", "--tex", "draft.tex", "--output", "evidence-metadata.tex", *extra_args,
        cwd=tmp_path,
    )


def compile_pdf(directory: Path, tex: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", tex],
        cwd=directory, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
    )


def pdf_text(directory: Path, pdf: str) -> str:
    result = subprocess.run(
        ["pdftotext", pdf, "-"], cwd=directory, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def pdf_file_uri_targets(pdf) -> set[str]:
    targets = set()
    for page in pdf:
        for link in page.get_links():
            assert pdf.xref_get_key(link["xref"], "A/S") == ("name", "/URI")
            kind, uri = pdf.xref_get_key(link["xref"], "A/URI")
            assert kind == "string" and uri.startswith("file:")
            targets.add(unquote(urlparse(uri).path))
    return targets


@pytest.fixture(scope="module")
def sha() -> str:
    import hashlib

    return hashlib.sha256(b"adopted bytes").hexdigest()


# -- unit level ---------------------------------------------------------------


def test_validate_id_accepts_restricted_ascii():
    assert ep.validate_id("tb2j-run-42", "x") == "tb2j-run-42"


def test_validate_id_rejects_special_characters():
    with pytest.raises(ep.ProjectionError, match="restricted ASCII"):
        ep.validate_id("run_42", "x")
    with pytest.raises(ep.ProjectionError, match="restricted ASCII"):
        ep.validate_id("run #1", "x")


def test_escape_roundtrip():
    inverse = {
        "\\textbackslash{}": "\\",
        "\\{": "{", "\\}": "}", "\\$": "$", "\\&": "&",
        "\\%": "%", "\\#": "#", "\\_": "_",
        "\\textasciicircum{}": "^", "\\textasciitilde{}": "~", "\\ ": " ",
    }
    samples = ["runs_42 #1 %v2 out.dat", "note with spaces.dat", "a\\b{c}$d&e%f^g~h i", "plain-path.dat"]
    for sample in samples:
        escaped = ep.tex_escape(sample)
        # deterministic inverse walk
        out, index = "", 0
        while index < len(escaped):
            for token, char in inverse.items():
                if escaped.startswith(token, index):
                    out += char
                    index += len(token)
                    break
            else:
                out += escaped[index]
                index += 1
        assert out == sample


# -- CLI level ----------------------------------------------------------------


def test_generate_rejects_invalid_id_in_manifest(tmp_path, sha):
    write_project(tmp_path, MANIFEST.format(sha=sha, commit=COMMIT).replace("tb2j-run-42", "tb2j_run_42", 1), DRAFT)
    result = generate(tmp_path)
    assert result.returncode == 2
    assert "restricted ASCII" in result.stderr
    assert not (tmp_path / "evidence-metadata.tex").exists()


def test_generate_rejects_invalid_or_unknown_id_in_draft(tmp_path, sha):
    manifest = MANIFEST.format(sha=sha, commit=COMMIT)
    bad_draft = DRAFT.replace("\\evidenceblock{tb2j-run-42}", "\\evidenceblock{bad_id}")
    write_project(tmp_path, manifest, bad_draft)
    result = generate(tmp_path)
    assert result.returncode == 2
    assert "restricted ASCII" in result.stderr

    unknown_draft = DRAFT.replace("\\evidenceblock{tb2j-run-42}", "\\evidenceblock{not-in-manifest}")
    write_project(tmp_path, manifest, unknown_draft)
    result = generate(tmp_path)
    assert result.returncode == 2
    assert "not in manifest" in result.stderr


def test_generate_deterministic_and_overwrites_hand_edits(tmp_path, sha):
    write_project(tmp_path, MANIFEST.format(sha=sha, commit=COMMIT), DRAFT)
    assert generate(tmp_path).returncode == 0
    first = (tmp_path / "evidence-metadata.tex").read_bytes()
    assert generate(tmp_path).returncode == 0
    assert (tmp_path / "evidence-metadata.tex").read_bytes() == first  # idempotent
    (tmp_path / "evidence-metadata.tex").write_text("hand edit %%%", encoding="utf-8")
    result = generate(tmp_path)
    assert result.returncode == 0
    assert "hand edits are overwritten" in result.stdout or "overwritten" in result.stdout
    assert (tmp_path / "evidence-metadata.tex").read_bytes() == first


# -- real TeX compilation ------------------------------------------------------


@pytest.fixture(scope="module")
def compiled(tmp_path_factory, sha):
    """Compile the draft once per toggle state; return dirs and extracted text."""
    on_dir = tmp_path_factory.mktemp("proj-on")
    off_dir = tmp_path_factory.mktemp("proj-off")
    manifest = MANIFEST.format(sha=sha, commit=COMMIT)
    for directory in (on_dir, off_dir):
        draft = DRAFT if directory == on_dir else DRAFT.replace(
            "\\begin{document}", "\\evidencemarginfalse\n\\begin{document}"
        )
        write_project(directory, manifest, draft)
        assert generate(directory).returncode == 0
    result_on = compile_pdf(on_dir, "draft.tex")
    assert result_on.returncode == 0, result_on.stdout[-2000:]
    # Exercise the public preamble toggle, not a hand edit to generated metadata.
    result_off = compile_pdf(off_dir, "draft.tex")
    assert result_off.returncode == 0, result_off.stdout[-2000:]
    return {"on": on_dir, "off": off_dir}


def test_compact_notes_preserve_source_identity_without_provenance_paragraphs(compiled, sha):
    text = " ".join(pdf_text(compiled["on"], "draft.pdf").split())
    assert "runs_42 #1 %v2 out.dat" in text
    assert "+1 sources" in text and "note with spaces.dat" not in text
    assert sha[:12] in text
    assert "claim-lifetimes" in text and "2026-10-19-draft1" in text
    assert "isolate the contribution" not in text
    assert COMMIT not in text and "snapshots/" not in text
    metadata = (compiled["on"] / "evidence-metadata.tex").read_text()
    records = [json.loads(line.removeprefix("%% evidence ")) for line in metadata.splitlines()
               if line.startswith("%% evidence ")]
    claim = next(record for record in records if record["id"] == "claim-lifetimes")
    assert claim["claim"]["intent"] == "isolate the contribution"
    assert set(claim["artifacts"]) == {"tb2j-run-42", "note-snapshot"}
    assert claim["artifacts"]["tb2j-run-42"]["locator"]["commit"] == COMMIT


def test_toggle_off_removes_all_evidence_content(compiled):
    on_text = pdf_text(compiled["on"], "draft.pdf")
    off_text = pdf_text(compiled["off"], "draft.pdf")
    assert "runs_42" not in off_text
    assert "tb2j-run-42" not in off_text
    assert "isolate the contribution" not in off_text
    assert "Magnon lifetimes agree" in off_text  # rest of the document unchanged
    assert "archived (public statement, kept by export)" in off_text
    for line in ("Magnon lifetimes", "archived (public statement, kept by export)"):
        assert line in on_text and line in off_text


def test_raster_grey_and_toggle_difference(compiled):
    def raster(directory: Path) -> bytes:
        result = subprocess.run(
            ["pdftoppm", "-gray", "-r", "72", "-f", "1", "-l", "1", "-png", "draft.pdf", "page"],
            cwd=directory, capture_output=True, timeout=120,
        )
        assert result.returncode == 0, result.stderr
        return sorted(directory.glob("page*.png"))[0].read_bytes()

    on_png, off_png = raster(compiled["on"]), raster(compiled["off"])
    assert on_png != off_png  # the grey layer is visible on the raster

    # pixel stats from the PGM raster of the toggle-on page
    result = subprocess.run(
        ["pdftoppm", "-gray", "-r", "72", "-f", "1", "-l", "1", "draft.pdf", "pagegrey"],
        cwd=compiled["on"], capture_output=True, timeout=120,
    )
    assert result.returncode == 0, result.stderr
    pgms = sorted(compiled["on"].glob("pagegrey*.pgm"))
    assert pgms, sorted(p.name for p in compiled["on"].iterdir())

    def midtones(directory: Path) -> int:
        runs = subprocess.run(
            ["pdftoppm", "-gray", "-r", "72", "-f", "1", "-l", "1", "draft.pdf", "pgcheck"],
            cwd=directory, capture_output=True, timeout=120,
        )
        assert runs.returncode == 0, runs.stderr
        check = sorted(directory.glob("pgcheck*.pgm"))[0]
        data = check.read_bytes()
        pixels = data[data.index(b"255\n") + 4:]
        check.unlink()
        return sum(1 for value in pixels if 100 <= value <= 210)

    on_grey, off_grey = midtones(compiled["on"]), midtones(compiled["off"])
    assert on_grey > off_grey + 50, (
        "expected the grey evidence paragraph to add mid-tone pixels on the toggle-on page "
        f"(on={on_grey}, off={off_grey})"
    )


def test_aggregate_display_preserves_all_support_and_rejects_unrelated_sources(tmp_path, sha):
    claim_only = DRAFT.replace("\\evidenceblock{tb2j-run-42}\n", "")
    manifest = MANIFEST.format(sha=sha, commit=COMMIT).replace(
        '    judgment: support', '    judgment: support\n    display_artifact: note-snapshot'
    )
    write_project(tmp_path, manifest, claim_only)
    assert generate(tmp_path).returncode == 0
    result = compile_pdf(tmp_path, "draft.tex")
    assert result.returncode == 0, result.stdout[-2000:]
    text = pdf_text(tmp_path, "draft.pdf")
    assert "note with spaces.dat" in text and "runs_42" not in text
    records = [json.loads(line.removeprefix("%% evidence "))
               for line in (tmp_path / "evidence-metadata.tex").read_text().splitlines()
               if line.startswith("%% evidence ")]
    assert set(records[0]["artifacts"]) == {"tb2j-run-42", "note-snapshot"}
    write_project(tmp_path, manifest.replace("display_artifact: note-snapshot", "display_artifact: absent"), claim_only)
    rejected = generate(tmp_path)
    assert rejected.returncode == 2 and "display_artifact" in rejected.stderr


def test_pdf_source_map_links_stay_gray(compiled):
    pymupdf = pytest.importorskip("pymupdf")
    with pymupdf.open(compiled["on"] / "draft.pdf") as doc:
        targets = pdf_file_uri_targets(doc)
        assert targets == {
            str(compiled["on"] / "evidence-manifest.yaml"),
        }
        for page in doc:
            spans = [span for block in page.get_text("dict")["blocks"]
                     for line in block.get("lines", []) for span in line["spans"]]
            for link in page.get_links():
                labels = [span for span in spans if pymupdf.Rect(span["bbox"]).intersects(link["from"])]
                assert labels
                for span in labels:
                    rgb = [(span["color"] >> shift) & 255 for shift in (16, 8, 0)]
                    assert max(rgb) - min(rgb) <= 1 and 120 <= min(rgb) <= 136



def test_same_basename_sources_keep_distinct_full_provenance(tmp_path, sha):
    document = ep.yaml.safe_load(MANIFEST.format(sha=sha, commit=COMMIT))
    document["artifacts"][0]["locator"]["path"] = "one/result.dat"
    document["artifacts"][1]["locator"]["path"] = "two/result.dat"
    document["artifacts"][1]["sha256"] = "f" * 64
    claim_only = DRAFT.replace("\\evidenceblock{tb2j-run-42}\n", "")
    write_project(tmp_path, ep.yaml.safe_dump(document), claim_only)
    assert generate(tmp_path).returncode == 0
    result = compile_pdf(tmp_path, "draft.tex")
    assert result.returncode == 0, result.stdout[-2000:]
    text = " ".join(pdf_text(tmp_path, "draft.pdf").split())
    assert text.count("result.dat") == 1 and "+1 sources" in text
    metadata = (tmp_path / "evidence-metadata.tex").read_text()
    record = next(json.loads(line.removeprefix("%% evidence ")) for line in metadata.splitlines()
                  if line.startswith("%% evidence "))
    assert record["artifacts"]["tb2j-run-42"]["sha256"] == sha
    assert record["artifacts"]["note-snapshot"]["sha256"] == "f" * 64


def test_url_only_manuscript_gets_the_evidence_hyperlinks(tmp_path, sha):
    pymupdf = pytest.importorskip("pymupdf")
    draft = DRAFT.replace(
        "\\usepackage[colorlinks=true,urlcolor=blue,linkcolor=blue]{hyperref}",
        "\\usepackage{url}",
    )
    write_project(tmp_path, MANIFEST.format(sha=sha, commit=COMMIT), draft)
    assert generate(tmp_path).returncode == 0
    result = compile_pdf(tmp_path, "draft.tex")
    assert result.returncode == 0, result.stdout[-2000:]
    with pymupdf.open(tmp_path / "draft.pdf") as pdf:
        targets = pdf_file_uri_targets(pdf)
        assert str(tmp_path / "evidence-manifest.yaml") in targets
        assert "[evidence] claim-lifetimes" in " ".join(page.get_text() for page in pdf)


@pytest.mark.parametrize("hidden", [False, True])
def test_metadata_with_later_hyperref_and_dependent_package(tmp_path, sha, hidden):
    pymupdf = pytest.importorskip("pymupdf")
    draft = DRAFT.replace(
        "\\usepackage[colorlinks=true,urlcolor=blue,linkcolor=blue]{hyperref}\n\\input{evidence-metadata.tex}",
        "\\input{evidence-metadata.tex}\n\\usepackage[colorlinks=true,urlcolor=blue,linkcolor=blue]{hyperref}\n\\usepackage{cleveref}",
    )
    if hidden:
        draft = draft.replace("\\begin{document}", "\\evidencemarginfalse\n\\begin{document}")
    write_project(tmp_path, MANIFEST.format(sha=sha, commit=COMMIT), draft)
    assert generate(tmp_path).returncode == 0
    result = compile_pdf(tmp_path, "draft.tex")
    assert result.returncode == 0, result.stdout[-2000:]
    with pymupdf.open(tmp_path / "draft.pdf") as pdf:
        text = " ".join(page.get_text() for page in pdf)
        assert "Magnon lifetimes agree" in text
        if hidden:
            assert "[evidence]" not in text
        else:
            assert "[evidence] claim-lifetimes" in text
            assert str(tmp_path / "evidence-manifest.yaml") in pdf_file_uri_targets(pdf)


def test_pdf_and_extensionless_sources_keep_exact_uri_targets(tmp_path, sha):
    pymupdf = pytest.importorskip("pymupdf")
    document = ep.yaml.safe_load(MANIFEST.format(sha=sha, commit=COMMIT))
    document["artifacts"][0]["locator"] = {"kind": "retained", "path": "run~old/figure #1_%&.pdf"}
    document["artifacts"][1]["locator"]["path"] = "export~old/RESULT"
    draft = DRAFT.replace("\\evidenceblock{claim-lifetimes}", "\\evidenceblock{note-snapshot}")
    write_project(tmp_path, ep.yaml.safe_dump(document), draft)
    assert generate(tmp_path).returncode == 0
    result = compile_pdf(tmp_path, "draft.tex")
    assert result.returncode == 0, result.stdout[-2000:]
    with pymupdf.open(tmp_path / "draft.pdf") as pdf:
        assert pdf_file_uri_targets(pdf) == {
            str(tmp_path / "run~old/figure #1_%&.pdf"),
            str(tmp_path / "export~old/RESULT"),
        }


def test_git_locator_navigation_is_stable_across_working_file_removal(tmp_path, sha):
    pymupdf = pytest.importorskip("pymupdf")
    write_project(tmp_path, MANIFEST.format(sha=sha, commit=COMMIT), DRAFT)
    assert generate(tmp_path).returncode == 0
    initial = (tmp_path / "evidence-metadata.tex").read_bytes()
    missing = tmp_path / "repo/runs_42 #1 %v2 out.dat"
    missing.unlink()
    assert generate(tmp_path).returncode == 0
    assert (tmp_path / "evidence-metadata.tex").read_bytes() == initial
    result = compile_pdf(tmp_path, "draft.tex")
    assert result.returncode == 0, result.stdout[-2000:]
    text = " ".join(pdf_text(tmp_path, "draft.pdf").split())
    assert "out.dat (locator)" in text
    with pymupdf.open(tmp_path / "draft.pdf") as pdf:
        assert pdf_file_uri_targets(pdf) == {
            str(tmp_path / "evidence-manifest.yaml")
        }
    assert not missing.exists()


def test_symlinked_manifest_links_relative_sources_from_the_real_manifest(tmp_path, sha):
    pymupdf = pytest.importorskip("pymupdf")
    real, alias = tmp_path / "real", tmp_path / "alias"
    real.mkdir()
    alias.mkdir()
    draft = DRAFT.replace("\\evidenceblock{tb2j-run-42}\n", "").replace(
        "\\evidenceblock{claim-lifetimes}", "\\evidenceblock{note-snapshot}"
    )
    write_project(real, MANIFEST.format(sha=sha, commit=COMMIT), draft)
    (alias / "manifest.yaml").symlink_to(real / "evidence-manifest.yaml")
    decoy = alias / "snapshots/note with spaces.dat"
    decoy.parent.mkdir()
    decoy.write_bytes(b"different bytes")
    result = run_cli(
        "generate", str(alias / "manifest.yaml"), "--tex", str(real / "draft.tex"),
        "--output", str(real / "evidence-metadata.tex"), cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    result = compile_pdf(real, "draft.tex")
    assert result.returncode == 0, result.stdout[-2000:]
    with pymupdf.open(real / "draft.pdf") as pdf:
        assert pdf_file_uri_targets(pdf) == {str(real / "snapshots/note with spaces.dat")}


def test_yaml_extension_dates_remain_manifest_only(tmp_path, sha):
    manifest = MANIFEST.format(sha=sha, commit=COMMIT).replace(
        "    locator:", "    reviewed: 2026-10-18\n    locator:"
    )
    manifest = manifest.replace(
        "      kind: snapshot",
        "      kind: snapshot\n      commit: 2026-10-18\n      repo: 2026-10-19",
    )
    write_project(tmp_path, manifest, DRAFT)
    original = (tmp_path / "evidence-manifest.yaml").read_bytes()
    assert generate(tmp_path).returncode == 0
    result = compile_pdf(tmp_path, "draft.tex")
    assert result.returncode == 0, result.stdout[-2000:]
    assert sha[:12] in pdf_text(tmp_path, "draft.pdf")
    assert (tmp_path / "evidence-manifest.yaml").read_bytes() == original


def test_default_many_source_summary_is_bounded_without_losing_support(tmp_path, sha):
    document = ep.yaml.safe_load(MANIFEST.format(sha=sha, commit=COMMIT))
    for index in range(10):
        artifact_id = f"extra-{index}"
        document["artifacts"].append({
            "id": artifact_id, "sha256": sha,
            "locator": {"kind": "retained", "path": f"extra/{index}.dat"},
        })
        document["claims"][0]["artifacts"].append(artifact_id)
    draft = DRAFT.replace("\\evidenceblock{tb2j-run-42}\n", "")
    write_project(tmp_path, ep.yaml.safe_dump(document), draft)
    assert generate(tmp_path).returncode == 0
    result = compile_pdf(tmp_path, "draft.tex")
    assert result.returncode == 0, result.stdout[-2000:]
    text = " ".join(pdf_text(tmp_path, "draft.pdf").split())
    assert text.count(sha[:12]) == 1 and "+11 sources" in text
    metadata = (tmp_path / "evidence-metadata.tex").read_text()
    record = next(json.loads(line.removeprefix("%% evidence ")) for line in metadata.splitlines()
                  if line.startswith("%% evidence "))
    assert set(record["artifacts"]) == set(document["claims"][0]["artifacts"])

def test_commented_calls_are_not_calls(tmp_path, sha):
    """A call after an unescaped % is inert TeX: generation succeeds without that id."""
    commented = DRAFT.replace(
        "Data availability:",
        "% \\evidenceblock{not-in-manifest} and \\evidenceblock{bad_id} are only comments\nData availability:",
    )
    write_project(tmp_path, MANIFEST.format(sha=sha, commit=COMMIT), commented)
    assert generate(tmp_path).returncode == 0
    escaped = DRAFT.replace("Data availability:", "\\% not a comment marker \\evidenceblock{tb2j-run-42}\nData availability:")
    write_project(tmp_path, MANIFEST.format(sha=sha, commit=COMMIT), escaped)
    assert generate(tmp_path).returncode == 0
    # active calls are still validated: an active unknown id keeps failing
    active_unknown = commented.replace("\\evidenceblock{tb2j-run-42}", "\\evidenceblock{still-unknown}")
    write_project(tmp_path, MANIFEST.format(sha=sha, commit=COMMIT), active_unknown)
    result = generate(tmp_path)
    assert result.returncode == 2
    assert "still-unknown" in result.stderr


def test_output_errors_are_consumer_visible(tmp_path, sha):
    write_project(tmp_path, MANIFEST.format(sha=sha, commit=COMMIT), DRAFT)
    (tmp_path / "output-dir").mkdir()
    result = run_cli(
        "generate", "evidence-manifest.yaml", "--tex", "draft.tex", "--output", "output-dir", cwd=tmp_path
    )
    assert result.returncode == 2
    assert result.stderr.startswith("evidence-projection: error: ")
    assert "Traceback" not in result.stderr

    blocked = tmp_path / "locked.tex"
    blocked.write_text("stale", encoding="utf-8")
    blocked.chmod(0o000)
    if os.geteuid() == 0:  # root ignores file modes; the check would not bite
        blocked.chmod(0o644)
        pytest.skip("running as root: unreadable-file case not reproducible")
    result = run_cli(
        "generate", "evidence-manifest.yaml", "--tex", "draft.tex", "--output", "locked.tex", cwd=tmp_path
    )
    assert result.returncode == 2
    assert result.stderr.startswith("evidence-projection: error: ")
    assert "Traceback" not in result.stderr
    blocked.chmod(0o644)


def test_cli_generate_stdout(tmp_path, sha):
    write_project(tmp_path, MANIFEST.format(sha=sha, commit=COMMIT), DRAFT)
    result = run_cli("generate", "evidence-manifest.yaml", "--tex", "draft.tex", "--output", "-", cwd=tmp_path)
    assert result.returncode == 0
    assert result.stdout.startswith(ep.GENERATED_MARKER)
