"""Story 008: evidence metadata TeX projection (real pdflatex smoke included)."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

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
        write_project(directory, manifest, DRAFT)
        assert generate(directory).returncode == 0
    (on_dir / "evidence-metadata.tex").write_text(
        (on_dir / "evidence-metadata.tex").read_text(encoding="utf-8"), encoding="utf-8"
    )
    result_on = compile_pdf(on_dir, "draft.tex")
    assert result_on.returncode == 0, result_on.stdout[-2000:]
    # toggle off: display only — no source change beyond the single toggle
    # the toggle is a single switch: set \evidencemarginfalse after the \input in the preamble
    metadata_off = (off_dir / "evidence-metadata.tex").read_text(encoding="utf-8").replace(
        "\\evidencemargintrue", "\\evidencemarginfalse", 1
    )
    (off_dir / "evidence-metadata.tex").write_text(metadata_off, encoding="utf-8")
    result_off = compile_pdf(off_dir, "draft.tex")
    assert result_off.returncode == 0, result_off.stdout[-2000:]
    return {"on": on_dir, "off": off_dir}


def test_draft_compile_renders_fields_verbatim(compiled):
    text = pdf_text(compiled["on"], "draft.pdf")
    assert "runs_42 #1 %v2 out.dat" in text  # special characters round-trip
    assert "note with spaces.dat" in text
    assert "tb2j-run-42" in text
    assert "claim-lifetimes" in text
    assert "isolate the contribution" in text
    assert "edition 2026-10-19-draft1" in text  # FR-D5: block carries the evidence edition
    assert "Magnon lifetimes agree" in text  # body intact


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


def test_claim_id_block_renders_all_cited_sources(tmp_path, sha):
    """\\evidenceblock resolves claim ids: intent + every cited artifact's source; no traceback."""
    claim_only = DRAFT.replace("\\evidenceblock{tb2j-run-42}\n", "").replace(
        "\\evidenceblock{claim-lifetimes}", "\\evidenceblock{claim-lifetimes}"
    )
    write_project(tmp_path, MANIFEST.format(sha=sha, commit=COMMIT), claim_only)
    result = generate(tmp_path)
    assert result.returncode == 0, result.stderr
    metadata = (tmp_path / "evidence-metadata.tex").read_text(encoding="utf-8")
    assert "evdblock@claim-lifetimes" in metadata
    assert "isolate\\ the\\ contribution" in metadata  # intent rendered with escaped spaces
    assert "runs\\_42\\ \\#1\\ \\%v2\\ out.dat" in metadata  # multi-artifact claim: source 1
    assert "snapshots/note\\ with\\ spaces.dat" in metadata  # multi-artifact claim: source 2
    assert "sha256 " + sha[:12] in metadata


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
