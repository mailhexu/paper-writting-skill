#!/usr/bin/env python3
"""One-shot pre-submission reproduction check (Story 015, FR-D4).

Rebuilds the declared output set (PDF + key figures) in a clean environment
from the pinned evidence edition: every input is retrieved by its recorded
locator (Story 005/006 semantics) and hash-verified; macro re-extraction and
figure re-rendering run only declared scripts on pinned data; LaTeX is
recompiled; the declared outputs are compared against their reference copies
under an explicit per-output ignore list for nondeterministic bytes. Package
metadata (per-artifact license, dataset ID) is recorded in the same step for
the availability statements (FR-E1).

Boundary (this file never crosses it): reproduction is not re-running
science. Only recorded macro-extraction, plot-rendering, and TeX commands are
permitted; a missing or hash-mismatched pinned input fails the check, names
the artifact, and drafts a research handoff (FR-K3) — it is never recomputed
and never replaced with current working-tree bytes (ADR-003). A green result
certifies build-product reproduction only, not scientific correctness; this
is not an OS sandbox, only a declared-command and declared-input discipline.

Usage:
    repro_check.py check --plan repro-plan.yaml --manifest evidence-manifest.yaml --record repro-record.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from evidence_manifest import ManifestError, load_manifest, retrieve_bytes  # noqa: E402

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - dependency notice
    sys.stderr.write("repro-check: error: PyYAML is required (pip install pyyaml)\n")
    raise SystemExit(2)

ERROR_PREFIX = "repro-check: error: "
PLAN_SCHEMA = "pws.repro-plan/1"
RECORD_SCHEMA = "pws.repro-record/1"
STEP_KINDS = ("macro", "plot", "tex")
TEX_EXECUTABLES = ("pdflatex", "bibtex")
INTERPRETERS = ("python", "python3")
# Bounded TeX flag allowlist: everything else (output redirection, shell-out,
# format/engine switching, recorders, …) is refused — the rebuild runs only the
# recorded compilation commands inside the clean tree.
TEX_ALLOWED_FLAGS = (
    "-interaction=nonstopmode", "-interaction=batchmode", "-interaction=errorstopmode",
    "-interaction=scrollmode", "-halt-on-error", "-file-line-error",
)
PLACEHOLDER = re.compile(r"^(todo|tbd|fixme|xxx+|placeholder|<[^>]*>)$", re.IGNORECASE)
UNKNOWN = "unknown"


class ReproCheckError(Exception):
    """Consumer-visible reproduction-check failure (exit 2)."""


def _fail(message: str) -> "ReproCheckError":
    return ReproCheckError(f"{ERROR_PREFIX}{message}")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _relative_inside(value: str, where: str, field: str) -> str:
    if Path(value).is_absolute() or ".." in Path(value).parts:
        raise _fail(f"{where}: {field} must be a relative path without '..' (resolved: '{value}')")
    return value


def _norm(value: str) -> str:
    return os.path.normpath(value)


# -- plan ----------------------------------------------------------------------


def load_plan(plan_path: str, raw: bytes | None = None) -> dict:
    path = Path(plan_path)
    if raw is None:
        try:
            raw = path.read_bytes()
        except OSError as error:
            raise _fail(f"plan '{plan_path}': unreadable: {error}") from None
    try:
        plan = yaml.safe_load(raw.decode("utf-8"))
    except (yaml.YAMLError, UnicodeDecodeError) as error:
        raise _fail(f"plan '{plan_path}': not parseable YAML: {error}") from None
    if not isinstance(plan, dict) or plan.get("schema") != PLAN_SCHEMA:
        raise _fail(f"plan '{plan_path}': not a {PLAN_SCHEMA} document")
    base = path.resolve().parent
    if not isinstance(plan.get("edition"), str) or not plan["edition"].strip():
        raise _fail(f"plan '{plan_path}': missing edition")
    steps = plan.get("steps")
    if not isinstance(steps, list) or not steps:
        raise _fail(f"plan '{plan_path}': missing steps")
    seen_steps: set[str] = set()
    kinds_present: set[str] = set()
    for index, step in enumerate(steps):
        where = f"plan '{plan_path}' step[{index}]"
        if not isinstance(step, dict):
            raise _fail(f"{where}: not a mapping")
        for field in ("id", "kind", "command"):
            if field not in step:
                raise _fail(f"{where}: missing {field}")
        if step["id"] in seen_steps:
            raise _fail(f"{where}: duplicate step id '{step['id']}'")
        seen_steps.add(step["id"])
        if step["kind"] not in STEP_KINDS:
            raise _fail(f"{where}: kind must be one of {', '.join(STEP_KINDS)}")
        kinds_present.add(step["kind"])
        command = step["command"]
        if not isinstance(command, list) or not command or not all(isinstance(part, str) for part in command):
            raise _fail(f"{where}: command must be a non-empty list of strings")
        if step["kind"] == "tex":
            if Path(command[0]).name != command[0] or Path(command[0]).name not in TEX_EXECUTABLES:
                raise _fail(
                    f"{where}: tex step must run one of {', '.join(TEX_EXECUTABLES)} by bare name, not '{command[0]}'"
                )
            for argument in command[1:]:
                if argument.startswith("-") and argument not in TEX_ALLOWED_FLAGS:
                    raise _fail(
                        f"{where}: tex step argument '{argument}' is not in the bounded TeX flag allowlist "
                        f"({', '.join(TEX_ALLOWED_FLAGS)}); flags that redirect output, shell out, or switch "
                        f"engines are refused — only recorded compilation commands inside the clean tree are permitted"
                    )
        else:
            if Path(command[0]).name != command[0] or Path(command[0]).name not in INTERPRETERS:
                raise _fail(
                    f"{where}: {step['kind']} step must run a pinned script via bare-name "
                    f"{'/'.join(INTERPRETERS)} resolved on PATH, not '{command[0]}'"
                )
            if len(command) < 2 or not isinstance(command[1], str):
                raise _fail(f"{where}: {step['kind']} step must name a declared pinned script path")
            if command[1].startswith("-"):
                raise _fail(
                    f"{where}: {step['kind']} step script operand '{command[1]}' is an interpreter option; "
                    f"a declared pinned script file path is required"
                )
    missing_kinds = [kind for kind in STEP_KINDS if kind not in kinds_present]
    if missing_kinds:
        raise _fail(
            f"plan '{plan_path}': the submission rebuild requires at least one step of each kind "
            f"{', '.join(STEP_KINDS)} (macro re-extraction, plot re-render, TeX recompilation); "
            f"missing: {', '.join(missing_kinds)}"
        )
    first_tex = next(index for index, step in enumerate(steps) if step["kind"] == "tex")
    late = [
        step["id"] for index, step in enumerate(steps)
        if step["kind"] in ("macro", "plot") and index > first_tex
    ]
    if late:
        raise _fail(
            f"plan '{plan_path}': macro/plot step(s) {', '.join(late)} run after TeX compilation; the "
            f"rebuild order is macro re-extraction → plot re-rendering → LaTeX recompilation, and the "
            f"compiled PDF must consume the re-extracted macros and re-rendered figures"
        )
    inputs = plan.get("inputs")
    if not isinstance(inputs, list) or not inputs:
        raise _fail(f"plan '{plan_path}': missing inputs")
    seen_paths: set[str] = set()
    for index, entry in enumerate(inputs):
        where = f"plan '{plan_path}' input[{index}]"
        if not isinstance(entry, dict) or not isinstance(entry.get("artifact"), str) or not entry["artifact"].strip():
            raise _fail(f"{where}: missing artifact id")
        target = entry.get("path")
        if not isinstance(target, str) or not target.strip():
            raise _fail(f"{where} (artifact '{entry.get('artifact')}'): missing target path")
        _relative_inside(target, where, "target path")
        if _norm(target) in seen_paths:
            raise _fail(f"{where}: target path collides with an earlier input at '{_norm(target)}'")
        seen_paths.add(_norm(target))
    declared_outputs = plan.get("declared_outputs")
    if not isinstance(declared_outputs, list) or not declared_outputs:
        raise _fail(f"plan '{plan_path}': missing declared_outputs")
    seen_outputs: set[str] = set()
    has_pdf_output = False
    for index, entry in enumerate(declared_outputs):
        where = f"plan '{plan_path}' declared_outputs[{index}]"
        if not isinstance(entry, dict):
            raise _fail(f"{where}: not a mapping")
        for field in ("path", "reference", "reference_sha256"):
            if not isinstance(entry.get(field), str) or not entry[field].strip():
                raise _fail(f"{where}: missing {field}")
        _relative_inside(entry["path"], where, "path")
        _relative_inside(entry["reference"], where, "reference")
        if _norm(entry["path"]) in seen_paths:
            raise _fail(f"{where}: declared output '{entry['path']}' collides with a pinned input target")
        if _norm(entry["path"]) in seen_outputs:
            raise _fail(f"{where}: duplicate declared output path '{entry['path']}'")
        seen_outputs.add(_norm(entry["path"]))
        if entry["path"].lower().endswith(".pdf"):
            has_pdf_output = True
        ignore = entry.get("ignore", [])
        if not isinstance(ignore, list) or not all(isinstance(pattern, str) for pattern in ignore):
            raise _fail(f"{where}: ignore must be a list of regex strings")
        for pattern in ignore:
            try:
                compiled = re.compile(pattern.encode("utf-8"))
            except re.error as error:
                raise _fail(f"{where}: ignore pattern {pattern!r}: invalid regex: {error}") from None
            probes = (b"", b"a", b"abcdefg", b"x" * 64, b"x" * 512)
            if all(compiled.fullmatch(probe) is not None for probe in probes) or (
                compiled.fullmatch(b"a") is not None and compiled.fullmatch(b"x" * 512) is not None
            ):
                raise _fail(
                    f"{where}: ignore pattern {pattern!r} can match spans of arbitrary length; the ignore "
                    f"list names specific nondeterministic byte spans and must never blanket-mask a declared output"
                )
    if not has_pdf_output:
        raise _fail(
            f"plan '{plan_path}': the declared output set must include the compiled manuscript PDF; "
            f"no declared output ends in .pdf"
        )
    pinned_targets = set(seen_paths)
    compiled_tex_stems = set()
    for step in steps:
        if step["kind"] == "tex":
            for argument in step["command"][1:]:
                if argument.lower().endswith(".tex") and _norm(argument) in pinned_targets:
                    compiled_tex_stems.add(Path(argument).stem)
    manuscript_outputs = {
        Path(entry["path"]).stem for entry in declared_outputs if entry["path"].lower().endswith(".pdf")
    }
    if not compiled_tex_stems or not (compiled_tex_stems & manuscript_outputs):
        raise _fail(
            f"plan '{plan_path}': no tex step compiles a pinned manuscript source whose stem matches a "
            f"declared .pdf output (compiled: {sorted(compiled_tex_stems)}, declared pdf stems: "
            f"{sorted(manuscript_outputs)}); the check rebuilds the manuscript, not just figures"
        )
    intermediates = plan.get("intermediates", [])
    if not isinstance(intermediates, list) or not all(isinstance(item, str) for item in intermediates):
        raise _fail(f"plan '{plan_path}': intermediates must be a list of relative paths")
    for index, item in enumerate(intermediates):
        _relative_inside(item, f"plan '{plan_path}' intermediates[{index}]", "path")
    metadata = plan.get("package_metadata")
    if not isinstance(metadata, dict) or not isinstance(metadata.get("artifacts"), list):
        raise _fail(f"plan '{plan_path}': missing package_metadata.artifacts")
    pinned_ids = {entry["artifact"] for entry in inputs}
    for index, entry in enumerate(metadata["artifacts"]):
        where = f"plan '{plan_path}' package_metadata.artifacts[{index}]"
        if not isinstance(entry, dict) or not isinstance(entry.get("artifact"), str) or not entry["artifact"].strip():
            raise _fail(f"{where}: missing artifact id")
        for field in ("license", "dataset_id"):
            value = entry.get(field)
            if not isinstance(value, str) or not value.strip():
                raise _fail(f"{where} (artifact '{entry['artifact']}'): missing {field}")
            if PLACEHOLDER.match(value.strip()):
                raise _fail(
                    f"{where} (artifact '{entry['artifact']}'): {field} is a placeholder ('{value.strip()}'); "
                    f"record the actual value or the literal '{UNKNOWN}' when it is genuinely unknown"
                )
        if entry["artifact"] not in pinned_ids:
            raise _fail(
                f"plan '{plan_path}': package metadata names artifact '{entry['artifact']}' "
                f"which is not a declared input"
            )
    for entry in inputs:
        if entry["artifact"] not in {item["artifact"] for item in metadata["artifacts"]}:
            raise _fail(
                f"plan '{plan_path}': pinned input '{entry['artifact']}' has no package metadata entry "
                f"(license/dataset_id are recorded in the same step, FR-E1)"
            )
    pinned_targets = set(seen_paths)
    for step in steps:
        if step["kind"] in ("macro", "plot"):
            if _norm(step["command"][1]) not in pinned_targets:
                raise _fail(
                    f"plan '{plan_path}' step '{step['id']}': script '{step['command'][1]}' is not a declared "
                    f"pinned input path; only pinned scripts may run"
                )
        else:
            for argument in step["command"][1:]:
                if not argument.startswith("-") and _norm(argument) not in pinned_targets:
                    raise _fail(
                        f"plan '{plan_path}' step '{step['id']}': TeX operand '{argument}' is not a declared "
                        f"pinned input path; the rebuild reads only pinned manuscript inputs inside the clean tree"
                    )
    plan["_base"] = str(base)
    return plan


# -- ignore-list masking -------------------------------------------------------


def mask(payload: bytes, patterns: list[re.Pattern[bytes]]) -> bytes:
    """Length-preserving masking of ignored byte spans, so byte offsets in
    formats like PDF stay comparable on both sides."""
    for pattern in patterns:
        payload = pattern.sub(lambda match: b"~" * len(match.group(0)), payload)
    return payload


def _mask_with_coverage(payload: bytes, patterns: list[re.Pattern[bytes]]) -> tuple[bytes, float]:
    """Return the masked bytes and the fraction of input bytes covered by
    ignore matches (counted per match, not per replacement byte — a literal
    `~` in the document is never counted as masked)."""
    total = 0
    current = payload
    for pattern in patterns:
        total += sum(len(match.group(0)) for match in pattern.finditer(current))
        current = pattern.sub(lambda match: b"~" * len(match.group(0)), current)
    fraction = (total / len(payload)) if payload else 0.0
    return current, fraction


# -- check ---------------------------------------------------------------------


def _toolchain_versions() -> dict[str, str]:
    versions: dict[str, str] = {"python": sys.version.split()[0]}
    for executable in TEX_EXECUTABLES:
        try:
            result = subprocess.run(
                [executable, "--version"], capture_output=True, text=True, timeout=60
            )
            first = result.stdout.splitlines()[0] if result.stdout.splitlines() else ""
            versions[executable] = first or f"exit {result.returncode}"
        except (OSError, subprocess.TimeoutExpired):
            versions[executable] = "unavailable"
    return versions


def _restricted_env(plan: dict) -> dict[str, str]:
    env = {"PATH": os.environ.get("PATH", "")}
    epoch = plan.get("source_date_epoch")
    if epoch is not None:
        env["SOURCE_DATE_EPOCH"] = str(epoch)
        env["FORCE_SOURCE_DATE"] = "1"
    return env


def check(plan_path: str, manifest_path: str, record_path: str) -> None:
    try:
        raw_plan = Path(plan_path).read_bytes()
    except OSError as error:
        raise _fail(f"plan '{plan_path}': unreadable: {error}") from None
    plan = load_plan(plan_path, raw_plan)  # validates before anything runs
    base = Path(plan["_base"])
    record_file = Path(record_path)
    if not record_file.parent.is_dir():
        raise _fail(f"--record parent directory '{record_file.parent}' does not exist")
    clean = record_file.parent / "clean"
    if clean.exists():
        raise _fail(
            f"clean environment '{clean}' already exists; every check rebuilds a fresh tree — "
            f"remove the previous run directory instead of re-running in place"
        )

    record: dict = {
        "schema": RECORD_SCHEMA,
        "plan": plan_path,
        "plan_sha256": _sha256(raw_plan),  # digest of the exact bytes parsed above
        "manifest": manifest_path,
        "ran_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "edition": plan["edition"],
        "toolchain": _toolchain_versions(),
        "inputs": [],
        "steps": [],
        "declared_outputs": [],
        "package_metadata": plan["package_metadata"],
        "result": None,
        "frk3_handoff": None,
    }

    def finish(result: str, message: str | None = None, frk3: str | None = None) -> None:
        record["result"] = result
        record["failure"] = message
        record["frk3_handoff"] = frk3
        try:
            record_file.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        except OSError as error:
            raise _fail(f"check record '{record_path}': unwritable: {error}") from None
        if result == "pass":
            print(f"repro-check: PASS — declared output set reproduced in a clean environment from pinned edition '{plan['edition']}'")
            print("repro-check: green certifies build-product reproduction only, not scientific correctness; science is never re-run")
        else:
            assert message is not None
            sys.stderr.write(f"{ERROR_PREFIX}{message}\n")
            raise SystemExit(2)

    # 1. pinned inputs: locator-retrieved, hash-verified bytes only (no working-tree state)
    try:
        document = load_manifest(manifest_path)
    except ManifestError as error:
        finish("fail", f"manifest: {error}")
        return
    if document["edition"] != plan["edition"]:
        finish(
            "fail",
            f"plan edition '{plan['edition']}' does not match manifest edition '{document['edition']}'; "
            f"the check rebuilds one declared evidence edition, not a mix",
        )
        return
    manifest_base = Path(manifest_path).resolve().parent  # locators resolve against the manifest
    by_id = {artifact["id"]: artifact for artifact in document["artifacts"]}
    for entry in plan["inputs"]:
        artifact_id = entry["artifact"]
        artifact = by_id.get(artifact_id)
        if artifact is None:
            draft = _write_frk3_draft(
                record_file.parent, artifact_id, None, None,
                f"artifact is not registered in manifest '{manifest_path}'",
            )
            record["inputs"].append({"artifact": artifact_id, "status": "missing"})
            finish(
                "fail",
                f"pinned input '{artifact_id}': not found in manifest '{manifest_path}'; "
                f"the check never recomputes science and never substitutes current file bytes (ADR-003) — "
                f"research handoff drafted",
                frk3=draft,
            )
            return
        try:
            payload = retrieve_bytes(artifact["locator"], artifact_id, manifest_base)
        except ManifestError as error:
            draft = _write_frk3_draft(
                record_file.parent, artifact_id, artifact["locator"], artifact["sha256"],
                f"locator could not be retrieved: {error}",
            )
            record["inputs"].append({"artifact": artifact_id, "status": "missing", "locator": artifact["locator"]})
            finish(
                "fail",
                f"pinned input '{artifact_id}': retrieval failed ({error}); the check never recomputes "
                f"science and never substitutes current file bytes (ADR-003) — research handoff drafted",
                frk3=draft,
            )
            return
        actual = _sha256(payload)
        expected = artifact["sha256"]
        if actual != expected:
            draft = _write_frk3_draft(
                record_file.parent, artifact_id, artifact["locator"], expected,
                f"retrieved bytes hash {actual} does not match the pinned sha256",
            )
            record["inputs"].append({"artifact": artifact_id, "status": "hash-mismatch", "expected": expected, "actual": actual})
            finish(
                "fail",
                f"pinned input '{artifact_id}': sha256 mismatch: expected {expected}, actual {actual}; "
                f"no recomputation is attempted and the input is NOT declared reproduced — research handoff drafted",
                frk3=draft,
            )
            return
        target = clean / entry["path"]
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
        except OSError as error:
            finish("fail", f"pinned input '{artifact_id}': could not materialize '{entry['path']}': {error}")
            return
        record["inputs"].append(
            {"artifact": artifact_id, "status": "verified", "sha256": actual, "path": entry["path"],
             "locator": artifact["locator"]}
        )

    # 2. reference copies: verified before anything is rebuilt
    compiled_outputs = []
    for entry in plan["declared_outputs"]:
        reference = base / entry["reference"]
        try:
            reference_bytes = reference.read_bytes()
        except OSError as error:
            finish("fail", f"declared output '{entry['path']}': reference copy '{entry['reference']}' unreadable: {error}")
            return
        patterns = [re.compile(pattern.encode("utf-8")) for pattern in entry.get("ignore", [])]
        normalized_sha = _sha256(mask(reference_bytes, patterns))
        if normalized_sha != entry["reference_sha256"]:
            finish(
                "fail",
                f"declared output '{entry['path']}': reference copy '{entry['reference']}' does not match the "
                f"recorded normalized sha256 (expected {entry['reference_sha256']}, actual {normalized_sha}); "
                f"the comparison baseline is incomplete",
            )
            return
        compiled_outputs.append((entry, patterns, normalized_sha))

    # 3. declared steps only — recorded macro extraction, plot rendering, TeX compilation
    env = _restricted_env(plan)
    for step in plan["steps"]:
        command = list(step["command"])
        if step["kind"] in ("macro", "plot") and not (clean / step["command"][1]).is_file():
            finish("fail", f"step '{step['id']}': script '{step['command'][1]}' is not among the pinned inputs; ambient working-tree state is never carried into the clean environment")
            return
        try:
            result = subprocess.run(
                command, cwd=clean, env=env, capture_output=True, text=True, timeout=600
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            finish("fail", f"step '{step['id']}': {type(error).__name__}: {error}")
            return
        record["steps"].append(
            {
                "id": step["id"],
                "kind": step["kind"],
                "command": command,
                "exit": result.returncode,
                "stdout_tail": result.stdout[-2000:],
                "stderr_tail": result.stderr[-2000:],
            }
        )
        if result.returncode != 0:
            tail = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else f"exit {result.returncode}"
            finish("fail", f"step '{step['id']}' ({step['kind']}) failed: {tail}")
            return

    # 4. declared-output comparison under the explicit ignore list
    for entry, patterns, expected_sha in compiled_outputs:
        built = clean / entry["path"]
        if built.is_symlink() or not built.is_file():
            finish("fail", f"declared output '{entry['path']}' was not produced as a regular file by the recorded steps")
            return
        try:
            built_bytes = built.read_bytes()
        except OSError as error:
            finish("fail", f"declared output '{entry['path']}': unreadable after rebuild: {error}")
            return
        masked, coverage = _mask_with_coverage(built_bytes, patterns)
        if coverage > 0.5:
            finish(
                "fail",
                f"declared output '{entry['path']}': the ignore list masks {coverage:.0%} of the output; "
                f"it names nondeterministic byte spans, not substantive content — narrow the patterns to the "
                f"actual nondeterministic bytes (timestamps, IDs) instead of masking most of the file",
            )
            return
        actual_sha = _sha256(masked)
        match = actual_sha == expected_sha
        record["declared_outputs"].append(
            {"path": entry["path"], "match": match, "expected_sha256": expected_sha, "actual_sha256": actual_sha,
             "ignore": entry.get("ignore", [])}
        )
        if not match:
            finish(
                "fail",
                f"declared output '{entry['path']}' does not reproduce the reference edition "
                f"(normalized sha256 expected {expected_sha}, actual {actual_sha}); the ignore list does not "
                f"cover the difference — name the real nondeterministic bytes explicitly instead of widening it blindly",
            )
            return

    # 5. clean-tree footprint: declared inputs + declared outputs + declared intermediates, nothing else
    declared = {_norm(entry["path"]) for entry in plan["inputs"]}
    declared |= {_norm(entry["path"]) for entry in plan["declared_outputs"]}
    declared |= {_norm(item) for item in plan.get("intermediates", [])}
    undeclared = sorted(
        found for found in (
            str(path.relative_to(clean)) for path in clean.rglob("*")
            if path.is_symlink() or (path.is_file() and not path.is_symlink())
        ) if _norm(found) not in declared or (clean / found).is_symlink()
    )
    if undeclared:
        finish(
            "fail",
            f"clean tree contains undeclared or symlinked file(s): {', '.join(undeclared)}; every clean-tree "
            f"entry must be a declared regular file (input, output, or intermediate) — a symlink into the "
            f"working tree is never a rebuilt product",
        )
        return

    finish("pass")


def _write_frk3_draft(directory: Path, artifact_id: str, locator: dict | None,
                      expected: str | None, reason: str) -> str:
    path = directory / f"repro-frk3-draft-{artifact_id}.md"
    lines = [
        "# FR-K3 research handoff (draft — owner approval required before execution)",
        "",
        f"- artifact: {artifact_id}",
        f"- pinned sha256: {expected if expected is not None else '(not registered)'}",
        f"- locator: {json.dumps(locator, ensure_ascii=False) if locator is not None else '(none recorded)'}",
        f"- problem: {reason}",
        "",
        "REQUEST (draft): the pre-submission reproduction check could not retrieve the pinned",
        "edition of this artifact. No scientific computation was re-run and no current file",
        "bytes were substituted (ADR-003). The owning Project's author should approve a",
        "research/recovery handoff to restore or re-pin the adopted edition before the",
        "submission package may claim reproducibility.",
        "",
    ]
    try:
        path.write_text("\n".join(lines), encoding="utf-8")
    except OSError as error:
        raise _fail(f"FR-K3 handoff draft for '{artifact_id}': unwritable: {error}") from None
    return str(path)


# -- CLI -----------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="repro-check", description="One-shot pre-submission clean-environment reproduction check (FR-D4)"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    check_parser = commands.add_parser("check", help="run the one-shot reproduction check")
    check_parser.add_argument("--plan", required=True)
    check_parser.add_argument("--manifest", required=True)
    check_parser.add_argument("--record", required=True)
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "check":
            check(arguments.plan, arguments.manifest, arguments.record)
    except (ReproCheckError, ManifestError) as error:
        sys.stderr.write(f"{error}\n")
        return 2
    except OSError as error:
        sys.stderr.write(f"{ERROR_PREFIX}{type(error).__name__}: {error}\n")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
