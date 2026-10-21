"""Story 014: strict build gate — embedding, bib freeze, citation/hash failure paths (real pdflatex smoke included)."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1] / "paper-writing-skill" / "tools"
sys.path.insert(0, str(TOOLS))

from build_gate import BuildGateError, citation_errors, render_build_info  # noqa: E402

PYTHON = sys.executable
TOOL = str(TOOLS / "build_gate.py")
MANIFEST_TOOL = str(TOOLS / "evidence_manifest.py")

COMMIT = "a" * 40
EDITION = "edition-2026-10-21"


def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([PYTHON, TOOL, *args], capture_output=True, text=True, timeout=600)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


BIB = """% frozen bibliography edition
@article{ref2026one,
  author = {One, A.},
  title = {Recorded result one},
  journal = {Journal of Recorded Results},
  year = {2026},
}
"""

MAIN_TEX = """\\documentclass{article}
\\input{build-info.tex}
\\begin{document}
This build was made at \\buildcommit{} for evidence edition \\buildedition{}.
\\nocite{*}
\\bibliographystyle{plain}
\\bibliography{refs}
\\end{document}
"""

MAIN_TEX_UNDEFINED = MAIN_TEX.replace("\\nocite{*}", "\\cite{nosuchkey2026}")

MANIFEST = """edition: edition-2026-10-21
artifacts:
  - id: demo-note
    sha256: {sha}
    locator:
      kind: snapshot
      path: evidence-snapshots/demo-note.md
claims:
  - id: claim-1
    statement: Demo claim tied to the pinned note.
    intent: Gate fixture claim.
    reason: Fixture for the build gate smoke.
    artifacts: [demo-note]
    judgment: support
"""


def make_project(tmp_path: Path, tex: str = MAIN_TEX) -> Path:
    (tmp_path / "refs.bib").write_text(BIB, encoding="utf-8")
    (tmp_path / "main.tex").write_text(tex, encoding="utf-8")
    snaps = tmp_path / "evidence-snapshots"
    snaps.mkdir()
    (snaps / "demo-note.md").write_text("pinned note bytes\n", encoding="utf-8")
    (tmp_path / "evidence-manifest.yaml").write_text(
        MANIFEST.format(sha=hashlib.sha256(b"pinned note bytes\n").hexdigest()), encoding="utf-8"
    )
    return tmp_path


def freeze_bib(tmp_path: Path) -> None:
    result = run_cli("freeze", str(tmp_path / "refs.bib"), "--record", str(tmp_path / "bib-freeze.yaml"))
    assert result.returncode == 0, result.stderr


# -- freeze --------------------------------------------------------------------


def test_freeze_requires_readable_bib(tmp_path):
    result = run_cli("freeze", str(tmp_path / "missing.bib"), "--record", str(tmp_path / "r.yaml"))
    assert result.returncode == 2
    assert "unreadable" in result.stderr


def test_freeze_is_idempotent_and_snapshots_exact_bytes(tmp_path):
    make_project(tmp_path)
    freeze_bib(tmp_path)
    record = (tmp_path / "bib-freeze.yaml").read_text(encoding="utf-8")
    assert digest(tmp_path / "refs.bib")[:12] in record
    first_snapshot = sorted((tmp_path / "bib-freeze").glob("*.bib"))[0].read_bytes()
    freeze_bib(tmp_path)  # same bytes: unchanged, no second record state
    assert sorted((tmp_path / "bib-freeze").glob("*.bib"))[0].read_bytes() == first_snapshot


# -- macro embedding (FR-D1: generated macro file, escaped) --------------------


def test_rendered_build_info_carries_commit_and_edition_escaped():
    rendered = render_build_info(COMMIT, "edition_with_underscore")
    assert COMMIT in rendered
    assert "edition\\_with\\_underscore" in rendered
    assert "{BUILD_COMMIT}" not in rendered and "{BUILD_EDITION}" not in rendered


# -- build gate failure paths (before TeX) --------------------------------------


def test_build_rejects_bad_commit_and_existing_output_dir(tmp_path):
    make_project(tmp_path)
    freeze_bib(tmp_path)
    result = run_cli("build", "--tex", str(tmp_path / "main.tex"), "--manifest",
                     str(tmp_path / "evidence-manifest.yaml"), "--bib", str(tmp_path / "refs.bib"),
                     "--freeze-record", str(tmp_path / "bib-freeze.yaml"),
                     "--commit", "HEAD", "--output-dir", str(tmp_path / "build"))
    assert result.returncode == 2
    assert "40-hex" in result.stderr  # HEAD is never a surrogate for declared bytes
    (tmp_path / "build").mkdir()
    result = run_cli("build", "--tex", str(tmp_path / "main.tex"), "--manifest",
                     str(tmp_path / "evidence-manifest.yaml"), "--bib", str(tmp_path / "refs.bib"),
                     "--freeze-record", str(tmp_path / "bib-freeze.yaml"),
                     "--commit", COMMIT, "--output-dir", str(tmp_path / "build"))
    assert result.returncode == 2 and "already exists" in result.stderr


def test_build_fails_on_missing_freeze_record(tmp_path):
    make_project(tmp_path)
    result = run_cli("build", "--tex", str(tmp_path / "main.tex"), "--manifest",
                     str(tmp_path / "evidence-manifest.yaml"), "--bib", str(tmp_path / "refs.bib"),
                     "--freeze-record", str(tmp_path / "bib-freeze.yaml"),
                     "--commit", COMMIT, "--output-dir", str(tmp_path / "build"))
    assert result.returncode == 2
    assert "freeze" in result.stderr


def test_build_fails_on_pinned_input_hash_mismatch(tmp_path):
    make_project(tmp_path)
    freeze_bib(tmp_path)
    (tmp_path / "evidence-snapshots" / "demo-note.md").write_text("TAMPERED bytes\n", encoding="utf-8")
    result = run_cli("build", "--tex", str(tmp_path / "main.tex"), "--manifest",
                     str(tmp_path / "evidence-manifest.yaml"), "--bib", str(tmp_path / "refs.bib"),
                     "--freeze-record", str(tmp_path / "bib-freeze.yaml"),
                     "--commit", COMMIT, "--output-dir", str(tmp_path / "build"))
    assert result.returncode == 2
    assert "demo-note" in result.stderr
    expected = hashlib.sha256(b"pinned note bytes\n").hexdigest()
    actual = hashlib.sha256(b"TAMPERED bytes\n").hexdigest()
    assert expected in result.stderr and actual in result.stderr
    assert not (tmp_path / "build" / "main.pdf").exists()


def test_build_fails_on_drifted_bib_and_never_adopts_silently(tmp_path):
    make_project(tmp_path)
    freeze_bib(tmp_path)
    (tmp_path / "refs.bib").write_text(BIB + "@article{late,{...}\n", encoding="utf-8")
    result = run_cli("build", "--tex", str(tmp_path / "main.tex"), "--manifest",
                     str(tmp_path / "evidence-manifest.yaml"), "--bib", str(tmp_path / "refs.bib"),
                     "--freeze-record", str(tmp_path / "bib-freeze.yaml"),
                     "--commit", COMMIT, "--output-dir", str(tmp_path / "build"))
    assert result.returncode == 2
    assert "DRIFT" in result.stderr
    frozen_snapshot = sorted((tmp_path / "bib-freeze").glob("*.bib"))[0]
    frozen_sha = digest(frozen_snapshot)
    assert frozen_sha[:12] in (tmp_path / "bib-freeze.yaml").read_text(encoding="utf-8")
    assert frozen_sha in result.stderr and digest(tmp_path / "refs.bib") in result.stderr
    # explicit opt-in builds from the frozen edition and reports the drift, not silently
    result = run_cli("build", "--tex", str(tmp_path / "main.tex"), "--manifest",
                     str(tmp_path / "evidence-manifest.yaml"), "--bib", str(tmp_path / "refs.bib"),
                     "--freeze-record", str(tmp_path / "bib-freeze.yaml"),
                     "--commit", COMMIT, "--output-dir", str(tmp_path / "build-frozen"),
                     "--use-frozen")
    assert result.returncode == 0, result.stderr
    assert "DRIFT" in result.stdout


# -- real TeX smoke: success and citation-failure paths -------------------------


def test_build_success_embeds_commit_and_edition_in_rendered_pdf(tmp_path):
    make_project(tmp_path)
    freeze_bib(tmp_path)
    result = run_cli("build", "--tex", str(tmp_path / "main.tex"), "--manifest",
                     str(tmp_path / "evidence-manifest.yaml"), "--bib", str(tmp_path / "refs.bib"),
                     "--freeze-record", str(tmp_path / "bib-freeze.yaml"),
                     "--commit", COMMIT, "--output-dir", str(tmp_path / "build"))
    assert result.returncode == 0, result.stderr
    assert COMMIT in result.stdout and EDITION in result.stdout
    pdf = tmp_path / "build" / "main.pdf"
    text = subprocess.run(["pdftotext", str(pdf), "-"], capture_output=True, text=True, timeout=120).stdout
    assert COMMIT in text
    assert EDITION in text


def test_build_fails_on_undefined_citation_naming_key_and_leaving_no_pdf(tmp_path):
    make_project(tmp_path, tex=MAIN_TEX_UNDEFINED)
    freeze_bib(tmp_path)
    result = run_cli("build", "--tex", str(tmp_path / "main.tex"), "--manifest",
                     str(tmp_path / "evidence-manifest.yaml"), "--bib", str(tmp_path / "refs.bib"),
                     "--freeze-record", str(tmp_path / "bib-freeze.yaml"),
                     "--commit", COMMIT, "--output-dir", str(tmp_path / "build"))
    assert result.returncode == 2
    assert "nosuchkey2026" in result.stderr
    assert not (tmp_path / "build" / "main.pdf").exists()
    assert not list((tmp_path / "build").glob("*.pdf"))


def test_citation_error_extraction_covers_log_and_bibtex_sources():
    log = "Package rerunfilecheck Warning\nCitation `keyA' on page 1 undefined on input line 3.\nThere were undefined references.\n"
    assert citation_errors(log, None) == ["keyA"]
    assert citation_errors("clean log", "I didn't find a database entry for `keyB'\n") == ["keyB"]
    assert citation_errors("clean log", "I was expecting a `}'\n") == ["<bibtex error reported>"]
    assert citation_errors("clean log", "clean blg") == []


def test_build_fails_when_pdf_does_not_embed_provenance(tmp_path):
    tex = MAIN_TEX.replace(
        "This build was made at \\buildcommit{} for evidence edition \\buildedition{}.",
        "Provenance macros omitted from the body.",
    )
    make_project(tmp_path, tex=tex)
    freeze_bib(tmp_path)
    result = run_cli("build", "--tex", str(tmp_path / "main.tex"), "--manifest",
                     str(tmp_path / "evidence-manifest.yaml"), "--bib", str(tmp_path / "refs.bib"),
                     "--freeze-record", str(tmp_path / "bib-freeze.yaml"),
                     "--commit", COMMIT, "--output-dir", str(tmp_path / "build"))
    assert result.returncode == 2
    assert "does not contain the" in result.stderr and "\\buildcommit" in result.stderr
    assert not list((tmp_path / "build").glob("*.pdf"))


def test_build_fails_when_manuscript_requests_another_bibliography(tmp_path):
    (tmp_path / "refs.bib").write_text(BIB, encoding="utf-8")
    (tmp_path / "other.bib").write_text(BIB, encoding="utf-8")
    (tmp_path / "main.tex").write_text(
        MAIN_TEX.replace("\\bibliography{refs}", "\\bibliography{other}"), encoding="utf-8"
    )
    snaps = tmp_path / "evidence-snapshots"
    snaps.mkdir()
    (snaps / "demo-note.md").write_bytes(b"pinned note bytes\n")
    (tmp_path / "evidence-manifest.yaml").write_text(
        MANIFEST.format(sha=hashlib.sha256(b"pinned note bytes\n").hexdigest()), encoding="utf-8"
    )
    freeze_bib(tmp_path)  # freezes refs.bib only
    result = run_cli("build", "--tex", str(tmp_path / "main.tex"), "--manifest",
                     str(tmp_path / "evidence-manifest.yaml"), "--bib", str(tmp_path / "refs.bib"),
                     "--freeze-record", str(tmp_path / "bib-freeze.yaml"),
                     "--commit", COMMIT, "--output-dir", str(tmp_path / "build"))
    assert result.returncode == 2
    assert "['other']" in result.stderr and "frozen input is 'refs'" in result.stderr
    assert not list((tmp_path / "build").glob("*.pdf"))


def test_relative_output_dir_resolves_against_caller_not_manuscript_dir(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    make_project(work)
    freeze_bib(work)
    result = subprocess.run(
        [PYTHON, TOOL, "build", "--tex", str(work / "main.tex"), "--manifest",
         str(work / "evidence-manifest.yaml"), "--bib", str(work / "refs.bib"),
         "--freeze-record", str(work / "bib-freeze.yaml"),
         "--commit", COMMIT, "--output-dir", "rel-build"],
        capture_output=True, text=True, timeout=600, cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert COMMIT in result.stdout


def test_freeze_record_without_frozen_at_is_rejected(tmp_path):
    make_project(tmp_path)
    freeze_bib(tmp_path)
    record = tmp_path / "bib-freeze.yaml"
    record.write_text(
        "\n".join(line for line in record.read_text(encoding="utf-8").splitlines()
                  if not line.startswith("frozen_at")) + "\n", encoding="utf-8")
    result = run_cli("build", "--tex", str(tmp_path / "main.tex"), "--manifest",
                     str(tmp_path / "evidence-manifest.yaml"), "--bib", str(tmp_path / "refs.bib"),
                     "--freeze-record", str(record),
                     "--commit", COMMIT, "--output-dir", str(tmp_path / "build"))
    assert result.returncode == 2
    assert "missing frozen_at" in result.stderr


def test_frozen_edition_unrestorable_fails_loudly(tmp_path):
    make_project(tmp_path)
    freeze_bib(tmp_path)
    for snapshot in (tmp_path / "bib-freeze").glob("*.bib"):
        snapshot.unlink()
    # current bytes still match the pin: freeze deterministically restores the dated snapshot
    result = run_cli("freeze", str(tmp_path / "refs.bib"), "--record", str(tmp_path / "bib-freeze.yaml"))
    assert result.returncode == 0
    assert len(list((tmp_path / "bib-freeze").glob("*.bib"))) == 1
    # snapshot lost AND bib drifted since the freeze point: no frozen bytes exist -> loud failure
    for snapshot in (tmp_path / "bib-freeze").glob("*.bib"):
        snapshot.unlink()
    (tmp_path / "refs.bib").write_text(BIB + "@article{late,{...}\n", encoding="utf-8")
    result = run_cli("build", "--tex", str(tmp_path / "main.tex"), "--manifest",
                     str(tmp_path / "evidence-manifest.yaml"), "--bib", str(tmp_path / "refs.bib"),
                     "--freeze-record", str(tmp_path / "bib-freeze.yaml"),
                     "--commit", COMMIT, "--output-dir", str(tmp_path / "build"), "--use-frozen")
    assert result.returncode == 2
    assert "unreadable" in result.stderr and "re-run `freeze`" in result.stderr
