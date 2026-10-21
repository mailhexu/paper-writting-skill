"""Story 015: FR-D4 clean-environment reproduction check — output-set comparison, ignore-list semantics, failure paths (real pdflatex smoke included)."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1] / "paper-writing-skill" / "tools"
sys.path.insert(0, str(TOOLS))

from repro_check import ReproCheckError, _mask_with_coverage, load_plan, mask  # noqa: E402

PYTHON = sys.executable
TOOL = str(TOOLS / "repro_check.py")

IGNORE_MAIN = [
    r"CreationDate \(D:[^)]*\)",
    r"ModDate \(D:[^)]*\)",
    r"(?s)/ID \[<[0-9A-Fa-f]*> ?<[0-9A-Fa-f]*>\]",
]
IGNORE_FIG = [r"D:\d{14}"]
INTERMEDIATES = ["macros.tex", "main.aux", "main.log"]

DATA_CSV = "quantity,value\nmass,1.234\n"

MACRO_SCRIPT = (
    "import csv\n"
    "rows = list(csv.DictReader(open(\"data/result.csv\")))\n"
    "value = [r for r in rows if r[\"quantity\"] == \"mass\"][0][\"value\"]\n"
    "open(\"macros.tex\", \"w\").write(\"\\\\newcommand\\\\resultmass{%s}\\n\" % value)\n"
)

# A minimal real PDF generator: one page carrying the pinned data value and an
# embedded timestamp. The wall-clock variant feeds the uncovered-timestamp
# failure test; it never inherits a declared epoch, so its bytes really vary.
FIGURE_SCRIPT_WALL = r'''
import time

def esc(text):
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

epoch = int(time.time())
stamp = time.strftime("D:%Y%m%d%H%M%S", time.gmtime(epoch))
value = open("data/result.csv").read().splitlines()[1].split(",")[1]
content = (
    "BT /F1 12 Tf 40 700 Td (result mass = " + esc(value) + ") Tj "
    "0 -20 Td (rendered " + esc(stamp) + ") Tj ET"
).encode()
objects = [
    b"<< /Type /Catalog /Pages 2 0 R >>",
    b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 400 200] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
    b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
    b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    b"<< /Title (pinned-data figure) /CreationDate (" + stamp.encode() + b") >>",
]
out = bytearray(b"%PDF-1.4\n")
offsets = []
for index, body in enumerate(objects, start=1):
    offsets.append(len(out))
    out += f"{index} 0 obj\n".encode() + body + b"\nendobj\n"
xref = len(out)
out += f"xref\n0 {len(objects)+1}\n".encode() + b"0000000000 65535 f \n"
for offset in offsets:
    out += f"{offset:010d} 00000 n \n".encode()
out += (
    f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R /Info 6 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
)
open("fig1.pdf", "wb").write(bytes(out))
'''

MAIN_TEX = """\\documentclass{article}
\\input{macros.tex}
\\begin{document}
The pinned result mass is \\resultmass{}.
\\end{document}
"""

EDITION = "edition-2026-10-21-sub1"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalized_sha(path: Path, ignore: list[str]) -> str:
    patterns = [re.compile(pattern.encode()) for pattern in ignore]
    return sha(mask(path.read_bytes(), patterns))


def write_snapshot(root: Path, artifact_id: str, payload: bytes) -> str:
    target = root / "evidence-snapshots" / artifact_id
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    return f"""
  - id: {artifact_id}
    sha256: {sha(payload)}
    locator:
      kind: snapshot
      path: evidence-snapshots/{artifact_id}"""


def write_manifest(root: Path, blocks: str, artifact_ids: list[str] | None = None) -> None:
    referenced = artifact_ids if artifact_ids is not None else ["result-data"]
    (root / "evidence-manifest.yaml").write_text(
        f"edition: {EDITION}\nartifacts:{blocks}\n"
        "claims:\n  - id: claim-1\n    statement: Fixture claim tied to the pinned data.\n"
        "    intent: Reproduction-check fixture.\n    reason: Fixture for the FR-D4 check.\n"
        f"    artifacts: {json.dumps(referenced)}\n    judgment: support\n",
        encoding="utf-8",
    )


def base_plan(reference_dir: Path, fig_ignore: list[str], main_ignore: list[str] | None = IGNORE_MAIN) -> dict:
    return {
        "schema": "pws.repro-plan/1",
        "edition": EDITION,
        "inputs": [
            {"artifact": "result-data", "path": "data/result.csv"},
            {"artifact": "macro-script", "path": "make_macros.py"},
            {"artifact": "figure-script", "path": "make_fig1.py"},
            {"artifact": "main-tex", "path": "main.tex"},
        ],
        "steps": [
            {"id": "macros", "kind": "macro", "command": ["python", "make_macros.py"]},
            {"id": "fig1", "kind": "plot", "command": ["python", "make_fig1.py"]},
            {"id": "pass1", "kind": "tex", "command": ["pdflatex", "-interaction=nonstopmode", "main.tex"]},
            {"id": "pass2", "kind": "tex", "command": ["pdflatex", "-interaction=nonstopmode", "main.tex"]},
        ],
        "intermediates": list(INTERMEDIATES),
        "declared_outputs": [
            {
                "path": "fig1.pdf",
                "reference": "references/fig1.pdf",
                "reference_sha256": normalized_sha(reference_dir / "fig1.pdf", fig_ignore),
                "ignore": fig_ignore,
            },
            {
                "path": "main.pdf",
                "reference": "references/main.pdf",
                "reference_sha256": normalized_sha(reference_dir / "main.pdf", main_ignore),
                "ignore": main_ignore,
            },
        ],
        "package_metadata": {
            "artifacts": [
                {"artifact": "result-data", "license": "CC BY 4.0", "dataset_id": "10.5281/zenodo.fixture"},
                {"artifact": "macro-script", "license": "MIT", "dataset_id": "not-applicable-private"},
                {"artifact": "figure-script", "license": "MIT", "dataset_id": "not-applicable-private"},
                {"artifact": "main-tex", "license": "unknown", "dataset_id": "unknown"},
            ]
        },
    }


def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([PYTHON, TOOL, *args], capture_output=True, text=True, timeout=600)


def run_check(root: Path) -> subprocess.CompletedProcess:
    return run_cli(
        "check",
        "--plan", str(root / "repro-plan.yaml"),
        "--manifest", str(root / "evidence-manifest.yaml"),
        "--record", str(root / "records" / "repro-record.json"),
    )


def build_reference_outputs(root: Path, fig_script: str = FIGURE_SCRIPT_WALL) -> Path:
    """Compile the manuscript once in a scratch copy to obtain reference outputs."""
    work = root / "_reference-build"
    (work / "data").mkdir(parents=True)
    (work / "data" / "result.csv").write_text(DATA_CSV, encoding="utf-8")
    (work / "make_macros.py").write_text(MACRO_SCRIPT, encoding="utf-8")
    (work / "make_fig1.py").write_text(fig_script, encoding="utf-8")
    (work / "main.tex").write_text(MAIN_TEX, encoding="utf-8")
    for command in (["python", "make_macros.py"], ["python", "make_fig1.py"]):
        subprocess.run(command, cwd=work, check=True, capture_output=True)
    for _ in range(2):
        result = subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", "main.tex"],
            cwd=work, capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr
    refs = root / "references"
    refs.mkdir()
    shutil.copy(work / "main.pdf", refs / "main.pdf")
    shutil.copy(work / "fig1.pdf", refs / "fig1.pdf")
    return refs


def fixture_artifacts(fig_script: str = FIGURE_SCRIPT_WALL) -> dict[str, bytes]:
    return {
        "result-data": DATA_CSV.encode(),
        "macro-script": MACRO_SCRIPT.encode(),
        "figure-script": fig_script.encode(),
        "main-tex": MAIN_TEX.encode(),
    }


def make_project(root: Path, fig_ignore: list[str] | None = IGNORE_FIG) -> Path:
    """Full fixture: manifest + snapshots + real reference outputs + plan + record dir."""
    root.mkdir(parents=True, exist_ok=True)
    refs = build_reference_outputs(root)
    blocks = "".join(write_snapshot(root, aid, payload) for aid, payload in fixture_artifacts().items())
    write_manifest(root, blocks)
    (root / "repro-plan.yaml").write_text(
        json.dumps(base_plan(refs, fig_ignore or [])), encoding="utf-8"
    )
    (root / "records").mkdir()
    return root


def make_plan_only_project(root: Path) -> Path:
    """TeX-free fixture for retrieval/validation failure tests: the plan declares the
    full pipeline, but the checks under test fail before any step runs, so the
    reference copies are plain stand-in bytes with recorded normalized hashes."""
    root.mkdir(parents=True, exist_ok=True)
    refs = root / "references"
    refs.mkdir()
    (refs / "fig1.pdf").write_bytes(b"%PDF-1.4 stand-in figure\n")
    (refs / "main.pdf").write_bytes(b"%PDF-1.4 stand-in manuscript\n")
    blocks = "".join(write_snapshot(root, aid, payload) for aid, payload in fixture_artifacts().items())
    write_manifest(root, blocks)
    (root / "repro-plan.yaml").write_text(
        json.dumps(base_plan(refs, IGNORE_FIG)), encoding="utf-8"
    )
    (root / "records").mkdir()
    return root


# -- unit-level helper paths -----------------------------------------------------


def test_mask_is_length_preserving_and_covers_all_matches():
    data = b"CreationDate (D:20261021000000) tail CreationDate (D:20261021000001)"
    masked = mask(data, [re.compile(rb"CreationDate \(D:[^)]*\)")])
    assert len(masked) == len(data)
    assert b"CreationDate" not in masked
    assert masked.count(b"~") == 2 * len(b"CreationDate (D:20261021000000)")


def test_plan_rejects_unknown_step_kind(tmp_path):
    (tmp_path / "p.yaml").write_text(
        json.dumps({"schema": "pws.repro-plan/1", "edition": "e",
                    "steps": [{"id": "s", "kind": "simulate", "command": ["python", "x.py"]}],
                    "inputs": [], "declared_outputs": [], "package_metadata": {"artifacts": []}}),
        encoding="utf-8",
    )
    with pytest.raises(ReproCheckError) as excinfo:
        load_plan(str(tmp_path / "p.yaml"))
    assert "kind must be one of" in str(excinfo.value)


def test_plan_requires_macro_plot_and_tex_steps(tmp_path):
    plan = {
        "schema": "pws.repro-plan/1", "edition": "e",
        "steps": [{"id": "fig", "kind": "plot", "command": ["python", "f.py"]}],
        "inputs": [{"artifact": "f", "path": "f.py"}],
        "declared_outputs": [{"path": "fig.pdf", "reference": "r.pdf", "reference_sha256": "x"}],
        "package_metadata": {"artifacts": [{"artifact": "f", "license": "MIT", "dataset_id": "d"}]},
    }
    (tmp_path / "p.yaml").write_text(json.dumps(plan), encoding="utf-8")
    with pytest.raises(ReproCheckError) as excinfo:
        load_plan(str(tmp_path / "p.yaml"))
    assert "at least one step of each kind" in str(excinfo.value) and "macro" in str(excinfo.value)


def test_plan_requires_a_declared_pdf_output(tmp_path):
    plan = {
        "schema": "pws.repro-plan/1", "edition": "e",
        "steps": [{"id": "m", "kind": "macro", "command": ["python", "m.py"]},
                  {"id": "f", "kind": "plot", "command": ["python", "f.py"]},
                  {"id": "t", "kind": "tex", "command": ["pdflatex", "main.tex"]}],
        "inputs": [{"artifact": "m", "path": "m.py"}, {"artifact": "f", "path": "f.py"},
                   {"artifact": "t", "path": "main.tex"}],
        "declared_outputs": [{"path": "fig1.eps", "reference": "r", "reference_sha256": "x"}],
        "package_metadata": {"artifacts": [{"artifact": "m", "license": "MIT", "dataset_id": "d"}]},
    }
    (tmp_path / "p.yaml").write_text(json.dumps(plan), encoding="utf-8")
    with pytest.raises(ReproCheckError) as excinfo:
        load_plan(str(tmp_path / "p.yaml"))
    assert "compiled manuscript PDF" in str(excinfo.value)


def test_plan_rejects_placeholder_metadata(tmp_path):
    plan = {
        "schema": "pws.repro-plan/1", "edition": "e",
        "steps": [{"id": "m", "kind": "macro", "command": ["python", "m.py"]},
                  {"id": "f", "kind": "plot", "command": ["python", "f.py"]},
                  {"id": "t", "kind": "tex", "command": ["pdflatex", "main.tex"]}],
        "inputs": [{"artifact": "m", "path": "m.py"}, {"artifact": "f", "path": "f.py"},
                   {"artifact": "t", "path": "main.tex"}],
        "declared_outputs": [{"path": "main.pdf", "reference": "r", "reference_sha256": "x"}],
        "package_metadata": {"artifacts": [{"artifact": "m", "license": "TODO", "dataset_id": "10.1/z"}]},
    }
    (tmp_path / "p.yaml").write_text(json.dumps(plan), encoding="utf-8")
    with pytest.raises(ReproCheckError) as excinfo:
        load_plan(str(tmp_path / "p.yaml"))
    assert "placeholder" in str(excinfo.value)


def test_plan_rejects_tex_command_outside_allowlist(tmp_path):
    plan = {
        "schema": "pws.repro-plan/1", "edition": "e",
        "steps": [{"id": "s", "kind": "tex", "command": ["latexmk", "-pdf", "main.tex"]}],
        "inputs": [], "declared_outputs": [], "package_metadata": {"artifacts": []},
    }
    (tmp_path / "p.yaml").write_text(json.dumps(plan), encoding="utf-8")
    with pytest.raises(ReproCheckError) as excinfo:
        load_plan(str(tmp_path / "p.yaml"))
    assert "pdflatex" in str(excinfo.value)


def test_plan_rejects_tex_output_redirection_flag(tmp_path):
    plan = {
        "schema": "pws.repro-plan/1", "edition": "e",
        "steps": [{"id": "m", "kind": "macro", "command": ["python", "m.py"]},
                  {"id": "f", "kind": "plot", "command": ["python", "f.py"]},
                  {"id": "t", "kind": "tex",
                   "command": ["pdflatex", "-interaction=nonstopmode", "-output-directory=/tmp/elsewhere", "main.tex"]}],
        "inputs": [{"artifact": "m", "path": "m.py"}, {"artifact": "f", "path": "f.py"},
                   {"artifact": "t", "path": "main.tex"}],
        "declared_outputs": [{"path": "main.pdf", "reference": "r", "reference_sha256": "x"}],
        "package_metadata": {"artifacts": [{"artifact": "m", "license": "MIT", "dataset_id": "d"}]},
    }
    (tmp_path / "p.yaml").write_text(json.dumps(plan), encoding="utf-8")
    with pytest.raises(ReproCheckError) as excinfo:
        load_plan(str(tmp_path / "p.yaml"))
    assert "bounded TeX flag allowlist" in str(excinfo.value)


def test_plan_rejects_suffixless_absolute_tex_operand(tmp_path):
    plan = {
        "schema": "pws.repro-plan/1", "edition": "e",
        "steps": [{"id": "m", "kind": "macro", "command": ["python", "m.py"]},
                  {"id": "f", "kind": "plot", "command": ["python", "f.py"]},
                  {"id": "t", "kind": "tex",
                   "command": ["pdflatex", "-interaction=nonstopmode", "/tmp/external", "main.tex"]}],
        "inputs": [{"artifact": "m", "path": "m.py"}, {"artifact": "f", "path": "f.py"},
                   {"artifact": "t", "path": "main.tex"}],
        "declared_outputs": [{"path": "main.pdf", "reference": "r", "reference_sha256": "x"}],
        "package_metadata": {"artifacts": [{"artifact": "m", "license": "MIT", "dataset_id": "d"},
                                           {"artifact": "f", "license": "MIT", "dataset_id": "d"},
                                           {"artifact": "t", "license": "MIT", "dataset_id": "d"}]},
    }
    (tmp_path / "p.yaml").write_text(json.dumps(plan), encoding="utf-8")
    with pytest.raises(ReproCheckError) as excinfo:
        load_plan(str(tmp_path / "p.yaml"))
    assert "not a declared pinned input path" in str(excinfo.value)


def test_plan_rejects_compilation_before_macro_and_plot_stages(tmp_path):
    steps = [
        {"id": "pass1", "kind": "tex", "command": ["pdflatex", "-interaction=nonstopmode", "main.tex"]},
        {"id": "macros", "kind": "macro", "command": ["python", "make_macros.py"]},
        {"id": "fig1", "kind": "plot", "command": ["python", "make_fig1.py"]},
        {"id": "pass2", "kind": "tex", "command": ["pdflatex", "-interaction=nonstopmode", "main.tex"]},
    ]
    plan = {
        "schema": "pws.repro-plan/1", "edition": "e",
        "steps": steps,
        "inputs": [{"artifact": "m", "path": "make_macros.py"}, {"artifact": "f", "path": "make_fig1.py"},
                   {"artifact": "t", "path": "main.tex"}],
        "declared_outputs": [{"path": "main.pdf", "reference": "r", "reference_sha256": "x"}],
        "package_metadata": {"artifacts": [{"artifact": "m", "license": "MIT", "dataset_id": "d"}]},
    }
    (tmp_path / "p.yaml").write_text(json.dumps(plan), encoding="utf-8")
    with pytest.raises(ReproCheckError) as excinfo:
        load_plan(str(tmp_path / "p.yaml"))
    assert "run after TeX compilation" in str(excinfo.value)


def test_plan_rejects_path_qualified_interpreter_and_noncompiling_tex_step(tmp_path):
    plan = {
        "schema": "pws.repro-plan/1", "edition": "e",
        "steps": [{"id": "m", "kind": "macro", "command": ["./python", "m.py"]},
                  {"id": "f", "kind": "plot", "command": ["python", "f.py"]},
                  {"id": "t", "kind": "tex", "command": ["bibtex", "refs"]}],
        "inputs": [{"artifact": "m", "path": "m.py"}, {"artifact": "f", "path": "f.py"},
                   {"artifact": "t", "path": "main.tex"}],
        "declared_outputs": [{"path": "main.pdf", "reference": "r", "reference_sha256": "x"},
                             {"path": "fig1.pdf", "reference": "r2", "reference_sha256": "y"}],
        "package_metadata": {"artifacts": [{"artifact": "m", "license": "MIT", "dataset_id": "d"},
                                           {"artifact": "f", "license": "MIT", "dataset_id": "d"},
                                           {"artifact": "t", "license": "MIT", "dataset_id": "d"}]},
    }
    (tmp_path / "p.yaml").write_text(json.dumps(plan), encoding="utf-8")
    with pytest.raises(ReproCheckError) as excinfo:
        load_plan(str(tmp_path / "p.yaml"))
    assert "bare-name" in str(excinfo.value)
    plan["steps"][0]["command"] = ["python", "m.py"]
    (tmp_path / "p.yaml").write_text(json.dumps(plan), encoding="utf-8")
    with pytest.raises(ReproCheckError) as excinfo:
        load_plan(str(tmp_path / "p.yaml"))
    assert "compiles a pinned manuscript source" in str(excinfo.value)


def test_near_blanket_ignore_pattern_is_refused_at_comparison_time():
    pattern = re.compile(rb"(?s)^.*(?=%%EOF)")
    payload = b"x" * 100 + b"%%EOF"
    masked, coverage = _mask_with_coverage(payload, [pattern])
    assert len(masked) == len(payload) and masked != b"~" * len(masked)  # passes full-masking probes
    assert coverage > 0.5  # the match span covers essentially the whole file
    # a genuinely narrow pattern stays far under the guard on realistic sizes,
    # and literal tildes in the document are never counted as masked coverage
    narrow_bytes = b"CreationDate (D:20261021000000)" + b"~" * 1000 + b"z" * 1000
    masked, coverage = _mask_with_coverage(narrow_bytes, [re.compile(rb"CreationDate \(D:[^)]*\)")])
    assert coverage < 0.05


@pytest.mark.skipif(shutil.which("pdflatex") is None, reason="pdflatex required")
def test_symlinked_declared_output_fails(tmp_path):
    root = make_project(tmp_path)
    # replace the pinned plot script with one that symlinks the declared output
    # to the working-tree reference copy: the comparison must refuse it instead
    # of hashing reference bytes as a "rebuilt" figure
    import hashlib as _h
    rogue = (
        "import os\n"
        "os.symlink(os.path.abspath(\"../../references/fig1.pdf\"), \"fig1.pdf\")\n"
        "assert os.path.exists(\"fig1.pdf\")\n"
    )
    (root / "evidence-snapshots" / "figure-script").write_bytes(rogue.encode())
    plan = json.loads((root / "repro-plan.yaml").read_text(encoding="utf-8"))
    plan["package_metadata"]["artifacts"][2]["license"] = "MIT"  # unchanged, keep valid
    (root / "repro-plan.yaml").write_text(json.dumps(plan), encoding="utf-8")
    manifest = (root / "evidence-manifest.yaml").read_text(encoding="utf-8")
    start = manifest.index("  - id: figure-script")
    end = manifest.index("  - id:", start + 10)
    manifest = (
        manifest[:start]
        + f"  - id: figure-script\n    sha256: {_h.sha256(rogue.encode()).hexdigest()}\n"
          "    locator:\n      kind: snapshot\n      path: evidence-snapshots/figure-script\n"
        + manifest[end:]
    )
    (root / "evidence-manifest.yaml").write_text(manifest)
    result = run_check(root)
    assert result.returncode == 2
    assert "regular file" in result.stderr or "symlink" in result.stderr
    record = json.loads((root / "records" / "repro-record.json").read_text(encoding="utf-8"))
    assert record["result"] == "fail"


def test_plan_rejects_interpreter_option_as_script_operand(tmp_path):
    plan = {
        "schema": "pws.repro-plan/1", "edition": "e",
        "steps": [{"id": "m", "kind": "macro", "command": ["python", "-c", "print(1)"]},
                  {"id": "f", "kind": "plot", "command": ["python", "f.py"]},
                  {"id": "t", "kind": "tex", "command": ["pdflatex", "main.tex"]}],
        "inputs": [{"artifact": "f", "path": "f.py"}, {"artifact": "t", "path": "main.tex"}],
        "declared_outputs": [{"path": "main.pdf", "reference": "r", "reference_sha256": "x"}],
        "package_metadata": {"artifacts": [{"artifact": "f", "license": "MIT", "dataset_id": "d"}]},
    }
    (tmp_path / "p.yaml").write_text(json.dumps(plan), encoding="utf-8")
    with pytest.raises(ReproCheckError) as excinfo:
        load_plan(str(tmp_path / "p.yaml"))
    assert "interpreter option" in str(excinfo.value)


def test_plan_rejects_tex_step_referencing_unpinned_manuscript_and_shell_escape(tmp_path):
    plan = {
        "schema": "pws.repro-plan/1", "edition": "e",
        "steps": [{"id": "m", "kind": "macro", "command": ["python", "m.py"]},
                  {"id": "f", "kind": "plot", "command": ["python", "f.py"]},
                  {"id": "t", "kind": "tex", "command": ["pdflatex", "-shell-escape", "/etc/main.tex"]}],
        "inputs": [{"artifact": "m", "path": "m.py"}, {"artifact": "f", "path": "f.py"},
                   {"artifact": "t", "path": "main.tex"}],
        "declared_outputs": [{"path": "main.pdf", "reference": "r", "reference_sha256": "x"}],
        "package_metadata": {"artifacts": [{"artifact": "m", "license": "MIT", "dataset_id": "d"}]},
    }
    (tmp_path / "p.yaml").write_text(json.dumps(plan), encoding="utf-8")
    with pytest.raises(ReproCheckError) as excinfo:
        load_plan(str(tmp_path / "p.yaml"))
    assert "refused" in str(excinfo.value)


def test_plan_rejects_blanket_ignore_pattern_and_absolute_output_path(tmp_path):
    plan = {
        "schema": "pws.repro-plan/1", "edition": "e",
        "steps": [{"id": "m", "kind": "macro", "command": ["python", "m.py"]},
                  {"id": "f", "kind": "plot", "command": ["python", "f.py"]},
                  {"id": "t", "kind": "tex", "command": ["pdflatex", "main.tex"]}],
        "inputs": [{"artifact": "m", "path": "m.py"}, {"artifact": "f", "path": "f.py"},
                   {"artifact": "t", "path": "main.tex"}],
        "declared_outputs": [{"path": "main.pdf", "reference": "r", "reference_sha256": "x",
                              "ignore": ["(?s).*"]}],
        "package_metadata": {"artifacts": [{"artifact": "m", "license": "MIT", "dataset_id": "d"}]},
    }
    (tmp_path / "p.yaml").write_text(json.dumps(plan), encoding="utf-8")
    with pytest.raises(ReproCheckError) as excinfo:
        load_plan(str(tmp_path / "p.yaml"))
    assert "arbitrary length" in str(excinfo.value)
    plan["declared_outputs"][0]["ignore"] = []
    plan["declared_outputs"][0]["path"] = "/etc/passwd-main.pdf"
    (tmp_path / "p.yaml").write_text(json.dumps(plan), encoding="utf-8")
    with pytest.raises(ReproCheckError) as excinfo:
        load_plan(str(tmp_path / "p.yaml"))
    assert "relative path" in str(excinfo.value)


def test_plan_rejects_normalized_input_path_collision(tmp_path):
    plan = {
        "schema": "pws.repro-plan/1", "edition": "e",
        "steps": [{"id": "m", "kind": "macro", "command": ["python", "m.py"]},
                  {"id": "f", "kind": "plot", "command": ["python", "./f.py"]},
                  {"id": "t", "kind": "tex", "command": ["pdflatex", "main.tex"]}],
        "inputs": [{"artifact": "m", "path": "m.py"}, {"artifact": "f", "path": "f.py"},
                   {"artifact": "f2", "path": "./f.py"},
                   {"artifact": "t", "path": "main.tex"}],
        "declared_outputs": [{"path": "main.pdf", "reference": "r", "reference_sha256": "x"}],
        "package_metadata": {"artifacts": [{"artifact": "m", "license": "MIT", "dataset_id": "d"}]},
    }
    (tmp_path / "p.yaml").write_text(json.dumps(plan), encoding="utf-8")
    with pytest.raises(ReproCheckError) as excinfo:
        load_plan(str(tmp_path / "p.yaml"))
    assert "collides" in str(excinfo.value)


# -- real clean-environment smoke: success path ---------------------------------


@pytest.mark.skipif(shutil.which("pdflatex") is None, reason="pdflatex required")
def test_clean_rebuild_reproduces_declared_output_set_with_ignore_list(tmp_path):
    root = make_project(tmp_path)
    result = run_check(root)
    assert result.returncode == 0, result.stderr
    record = json.loads((root / "records" / "repro-record.json").read_text(encoding="utf-8"))
    assert record["result"] == "pass"
    assert all(item["match"] for item in record["declared_outputs"])
    assert all(item["status"] == "verified" for item in record["inputs"])
    clean = root / "records" / "clean"
    assert (clean / "main.pdf").is_file() and (clean / "fig1.pdf").is_file()
    assert (clean / "macros.tex").read_text(encoding="utf-8").strip() == "\\newcommand\\resultmass{1.234}"
    # ambient working-tree files are not carried in: only pinned inputs exist
    assert not (clean / "repro-plan.yaml").exists() and not (clean / "evidence-manifest.yaml").exists()
    # clean-tree footprint: every file is a declared input, output, or declared intermediate
    declared = {os.path.normpath(p) for p in INTERMEDIATES} | {"fig1.pdf", "main.pdf", "data/result.csv",
               "make_macros.py", "make_fig1.py", "main.tex"}
    found = {os.path.normpath(str(p.relative_to(clean))) for p in clean.rglob("*") if p.is_file()}
    assert found == declared
    # package metadata recorded verbatim in the same step (FR-E1)
    meta = {item["artifact"]: item for item in record["package_metadata"]["artifacts"]}
    assert meta["result-data"]["license"] == "CC BY 4.0"
    assert meta["main-tex"]["dataset_id"] == "unknown"


@pytest.mark.skipif(shutil.which("pdflatex") is None, reason="pdflatex required")
def test_undeclared_build_product_fails_the_footprint_check(tmp_path):
    root = make_project(tmp_path)
    plan = json.loads((root / "repro-plan.yaml").read_text(encoding="utf-8"))
    plan["intermediates"] = ["macros.tex", "main.aux"]  # main.log left undeclared
    (root / "repro-plan.yaml").write_text(json.dumps(plan), encoding="utf-8")
    result = run_check(root)
    assert result.returncode == 2
    assert "undeclared or symlinked" in result.stderr and "main.log" in result.stderr
    record = json.loads((root / "records" / "repro-record.json").read_text(encoding="utf-8"))
    assert record["result"] == "fail"


@pytest.mark.skipif(shutil.which("pdflatex") is None, reason="pdflatex required")
def test_uncovered_timestamp_bytes_fail_comparison_then_pass_after_explicit_ignore(tmp_path):
    root = make_project(tmp_path, fig_ignore=[])
    time.sleep(1.1)  # the wall-clock stamp must differ between reference and clean rebuild
    result = run_check(root)
    assert result.returncode == 2
    assert "fig1.pdf" in result.stderr and "normalized sha256" in result.stderr
    record = json.loads((root / "records" / "repro-record.json").read_text(encoding="utf-8"))
    fig = [item for item in record["declared_outputs"] if item["path"] == "fig1.pdf"]
    assert fig and fig[0]["match"] is False and fig[0]["actual_sha256"] != fig[0]["expected_sha256"]
    assert fig[0]["ignore"] == []
    # second run (fresh record dir): the explicitly named ignore entry covers the timestamp
    shutil.rmtree(root / "records")
    (root / "records").mkdir()
    refs = root / "references"
    plan = base_plan(refs, IGNORE_FIG)
    (root / "repro-plan.yaml").write_text(json.dumps(plan), encoding="utf-8")
    result = run_check(root)
    assert result.returncode == 0, result.stderr
    record = json.loads((root / "records" / "repro-record.json").read_text(encoding="utf-8"))
    assert all(item["match"] for item in record["declared_outputs"])


# -- failure paths: mismatch, missing, ambient script, footprint -----------------


def test_pinned_input_hash_mismatch_fails_and_drafts_frk3_without_tex(tmp_path):
    root = make_plan_only_project(tmp_path)
    snapshot = root / "evidence-snapshots" / "result-data"
    snapshot.write_bytes(snapshot.read_bytes() + b"tampered\n")  # drift the snapshot bytes
    result = run_check(root)
    assert result.returncode == 2
    assert "result-data" in result.stderr and "sha256 mismatch" in result.stderr
    record = json.loads((root / "records" / "repro-record.json").read_text(encoding="utf-8"))
    assert record["result"] == "fail" and record["inputs"][0]["status"] == "hash-mismatch"
    draft = root / "records" / "repro-frk3-draft-result-data.md"
    assert draft.is_file() and "owner approval required" in draft.read_text(encoding="utf-8")
    assert record["frk3_handoff"] == str(draft)
    assert not (root / "records" / "clean").exists()  # nothing was rebuilt or declared reproduced
    assert record["steps"] == []  # no step ran after the pinned-input failure


def test_missing_pinned_input_fails_without_substituting_current_bytes(tmp_path):
    root = make_plan_only_project(tmp_path)
    (root / "evidence-snapshots" / "figure-script").unlink()  # locator unresolvable
    # ambient copy of the same script exists in the working tree next to the plan
    (root / "make_fig1.py").write_text(FIGURE_SCRIPT_WALL, encoding="utf-8")
    result = run_check(root)
    assert result.returncode == 2
    assert "figure-script" in result.stderr and "never substitutes current file bytes" in result.stderr
    record = json.loads((root / "records" / "repro-record.json").read_text(encoding="utf-8"))
    assert record["inputs"][-1]["status"] == "missing"
    assert (root / "records" / "repro-frk3-draft-figure-script.md").is_file()


def test_artifact_absent_from_manifest_drafts_frk3(tmp_path):
    root = make_plan_only_project(tmp_path)
    blocks = "".join(write_snapshot(tmp_path / "_unused", aid, payload)
                     for aid, payload in fixture_artifacts().items() if aid != "figure-script")
    # rebuild the manifest without figure-script (id not registered at all)
    (root / "evidence-snapshots" / "figure-script").unlink()
    write_manifest(root, blocks)
    result = run_check(root)
    assert result.returncode == 2
    assert "figure-script" in result.stderr and "not found in manifest" in result.stderr
    assert (root / "records" / "repro-frk3-draft-figure-script.md").is_file()
    record = json.loads((root / "records" / "repro-record.json").read_text(encoding="utf-8"))
    assert record["inputs"][-1] == {"artifact": "figure-script", "status": "missing"}


def test_plan_edition_must_match_manifest_edition(tmp_path):
    root = make_plan_only_project(tmp_path)
    plan = json.loads((root / "repro-plan.yaml").read_text(encoding="utf-8"))
    plan["edition"] = "edition-someother"
    (root / "repro-plan.yaml").write_text(json.dumps(plan), encoding="utf-8")
    result = run_check(root)
    assert result.returncode == 2
    assert "does not match manifest edition" in result.stderr


def test_ambient_unpinned_script_is_absent_in_clean_environment(tmp_path):
    root = make_plan_only_project(tmp_path)
    # drop figure-script from the plan inputs but keep the step; the script exists
    # only in the ambient working tree -> the clean run must fail, not fall back
    plan = json.loads((root / "repro-plan.yaml").read_text(encoding="utf-8"))
    plan["inputs"] = [item for item in plan["inputs"] if item["artifact"] != "figure-script"]
    plan["package_metadata"]["artifacts"] = [
        item for item in plan["package_metadata"]["artifacts"] if item["artifact"] != "figure-script"
    ]
    (root / "repro-plan.yaml").write_text(json.dumps(plan), encoding="utf-8")
    result = run_check(root)
    # validation refuses first: a step script that is not a declared pinned input
    assert result.returncode == 2 and "not a declared" in result.stderr


def test_existing_clean_tree_is_refused(tmp_path):
    root = make_plan_only_project(tmp_path)
    (root / "records" / "clean").mkdir()
    result = run_check(root)
    assert result.returncode == 2 and "already exists" in result.stderr


def test_missing_reference_copy_fails(tmp_path):
    root = make_plan_only_project(tmp_path)
    (root / "references" / "fig1.pdf").unlink()
    result = run_check(root)
    assert result.returncode == 2 and "reference copy" in result.stderr


def test_drifted_reference_copy_fails(tmp_path):
    root = make_plan_only_project(tmp_path)
    reference = root / "references" / "fig1.pdf"
    reference.write_bytes(reference.read_bytes() + b"% drift\n")
    result = run_check(root)
    assert result.returncode == 2 and "normalized sha256" in result.stderr
