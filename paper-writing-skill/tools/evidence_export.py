#!/usr/bin/env python3
"""Clean submission-source export and leak check (Story 009, FR-D5 / STD-005).

Generates a submission copy of a manuscript from the working copy:
strips ONLY the dedicated evidence metadata — every `\evidenceblock{ID}` call,
the generated `evidence-metadata.tex` file itself, and the `\input`/`\include`
lines that pull it in. Public content (body, citations, data/code availability
statements, figures) is preserved byte-for-byte. The working copy is never
modified. The toggle `\evidencemarginfalse` controls PDF display only; this
export is the real sanitization.

A call found inside a `verbatim` environment is not rewritten (no blanket TeX
transforms); export fails loudly instead.

Usage:
    evidence_export.py export <main.tex> --output-dir DIR [--copy RELPATH]... [--strip-metadata evidence-metadata.tex] [--no-compile]
    evidence_export.py leak-check <export-dir>
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

ERROR_PREFIX = "evidence-export: error: "
EVIDENCEBLOCK_CALL = re.compile(r"\\evidenceblock\s*\{[^{}]*\}")
VERBATIM_BEGIN = re.compile(r"\\begin\{(verbatim|verbatim\*|lstlisting|alltt)\}")
LEAK_PATTERNS = ("evidenceblock", "evidence-metadata", "evidence-manifest", "evidence-snapshots")
DEFAULT_METADATA = "evidence-metadata.tex"


class ExportError(Exception):
    """Consumer-visible export or leak-check failure (exit 2)."""


METADATA_INPUT_CALL = re.compile(r"\\(?:input|include)\s*\{([^{}]*)\}")


def _is_metadata_input(target: str, metadata_name: str) -> bool:
    if target.endswith(".tex"):
        target = target[: -len(".tex")]
    return Path(target).name == Path(metadata_name).with_suffix("").name


def strip_tex(text: str, metadata_name: str, source_name: str) -> str:
    """Strip evidenceblock calls and the metadata input command; nothing else.

    A dedicated metadata input sharing its line with other TeX is removed
    in place (the rest of the line is kept); only when nothing else remains
    on the line is the line break all that survives.
    """
    out_lines: list[str] = []
    verbatim: str | None = None
    for line in text.splitlines(keepends=True):
        original = line.rstrip("\r\n")
        newline = line[len(original):]
        if verbatim is None:
            begin = VERBATIM_BEGIN.search(original)
            if begin:
                verbatim = begin.group(1)
        else:
            if f"\\end{{{verbatim}}}" in original:
                verbatim = None
            if EVIDENCEBLOCK_CALL.search(original):
                raise ExportError(
                    f"{source_name}: \\evidenceblock call inside verbatim environment '{verbatim}'; "
                    f"evidence calls are draft margin macros, not verbatim content — move the call out"
                )
            out_lines.append(line)
            continue

        def drop_input(match: re.Match[str]) -> str:
            return "" if _is_metadata_input(match.group(1).strip(), metadata_name) else match.group(0)

        stripped = METADATA_INPUT_CALL.sub(drop_input, original)
        stripped = EVIDENCEBLOCK_CALL.sub("", stripped)
        if stripped.strip() == "" and original.strip() != "":
            out_lines.append(newline)  # the line held only stripped constructs: keep the line break
        else:
            out_lines.append(stripped + newline)
    return "".join(out_lines)


def _local_inputs(text: str, root: Path, source_name: str) -> list[Path]:
    found: list[Path] = []
    for match in METADATA_INPUT_CALL.finditer(text):
        target = match.group(1).strip()
        for candidate in (target, target + ".tex"):
            path = (root / candidate).resolve()
            if path.is_file() and path != root.resolve():
                if root.resolve() not in path.parents:
                    raise ExportError(
                        f"{source_name}: \\input '{target}' resolves outside the manuscript directory "
                        f"'{root}'; refusing unsafe copy"
                    )
                found.append(path)
                break
    return found


def export(main_tex: str, output_dir: str, copy: list[str], metadata_name: str, compile_pdf: bool, private_markers: list[str]) -> None:
    entry = Path(main_tex).resolve()
    if not entry.is_file():
        raise ExportError(f"main tex: '{main_tex}' not found")
    root = entry.parent
    destination = Path(output_dir)
    if destination.exists():
        raise ExportError(f"--output-dir: '{output_dir}' already exists; export always creates a fresh copy")
    try:
        destination.mkdir(parents=True)
    except OSError as error:
        raise ExportError(f"--output-dir: cannot create '{output_dir}': {error}") from error

    metadata_abs = (root / metadata_name).resolve()
    pending: list[Path] = [entry]
    visited: set[Path] = set()
    while pending:
        source = pending.pop(0).resolve()
        if source in visited:
            continue
        visited.add(source)
        if not (source == entry or root.resolve() in source.parents):
            raise ExportError(f"input '{source}' resolves outside the manuscript directory; refusing unsafe copy")
        if source == metadata_abs:
            continue  # the generated metadata file never enters the export
        try:
            raw = source.read_bytes()
            text = raw.decode("utf-8")  # binary read: line endings are preserved untouched
        except UnicodeDecodeError as error:
            raise ExportError(f"{source.name}: not UTF-8 text: {error}") from error
        except OSError as error:
            raise ExportError(f"{source.name}: unreadable: {error}") from error
        stripped = strip_tex(text, metadata_name, source.name)
        target = destination / source.relative_to(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(stripped.encode("utf-8"))
        for referenced in _local_inputs(text, root, source.name):
            if referenced != metadata_abs:
                pending.append(referenced)

    for relative in copy:
        source = (root / relative).resolve()
        if not source.is_file():
            raise ExportError(f"--copy '{relative}': not found under the manuscript directory")
        if source == metadata_abs:
            raise ExportError(
                f"--copy '{relative}': this is the generated metadata file; it never enters the export"
            )
        if not (source == entry or root.resolve() in source.parents):
            raise ExportError(f"--copy '{relative}': resolves outside the manuscript directory")
        target = destination / source.relative_to(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)

    if compile_pdf:
        result = subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", entry.name],
            cwd=destination,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
        )
        if result.returncode != 0:
            detail = result.stdout.strip().splitlines()[-5:]
            raise ExportError(
                "standalone compile of the exported source failed; the export dir is kept for inspection: "
                + " | ".join(line.strip() for line in detail)
            )
        print(f"export compiled standalone: {destination / (entry.stem + '.pdf')}")

    leaked = leak_findings(destination, private_markers)
    if leaked:
        for location in leaked:
            print(f"leak: {location}", file=sys.stderr)
        raise ExportError(
            f"leak check failed with {len(leaked)} finding(s) in '{destination}'; "
            f"the export dir is kept for inspection"
        )
    print(f"export clean: {len(visited)} tex file(s) copied to {destination}; leak check passed")


def leak_findings(directory: str, private_markers: list[str] | None = None) -> list[str]:
    """Scan the tree for the fixed metadata markers plus caller-supplied private
    path substrings (the caller passes the private roots that must not leak)."""
    root = Path(directory)
    if not root.is_dir():
        raise ExportError(f"leak-check: '{directory}' is not a directory")
    patterns = list(LEAK_PATTERNS) + [marker for marker in (private_markers or []) if marker]
    findings: list[str] = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        if path.suffix.lower() in (".pdf", ".png", ".jpg", ".jpeg", ".eps", ".zip"):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            for pattern in patterns:
                if pattern in line:
                    findings.append(f"{path.relative_to(root)}:{number}: contains '{pattern}'")
    return findings


def leak_check(directory: str, private_markers: list[str] | None = None) -> None:
    findings = leak_findings(directory, private_markers)
    if findings:
        for location in findings:
            print(f"leak: {location}", file=sys.stderr)
        raise ExportError(f"leak check FAILED: {len(findings)} finding(s) in '{directory}'")
    print(f"leak check passed: no evidence metadata residue in '{directory}'")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="evidence_export.py", description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    export_parser = commands.add_parser("export", help="generate a clean submission copy (working copy untouched)")
    export_parser.add_argument("main_tex")
    export_parser.add_argument("--output-dir", required=True)
    export_parser.add_argument("--copy", action="append", default=[], help="extra file to carry over (e.g. refs.bib, figure.pdf)")
    export_parser.add_argument("--strip-metadata", default=DEFAULT_METADATA, help="generated metadata file to strip (default: evidence-metadata.tex)")
    export_parser.add_argument("--no-compile", action="store_true", help="skip the standalone pdflatex compile of the export")
    export_parser.add_argument("--private-marker", action="append", default=[], help="private path substring that must not leak (repeatable)")
    leak_parser = commands.add_parser("leak-check", help="scan an export tree for evidence metadata residue")
    leak_parser.add_argument("directory")
    leak_parser.add_argument("--private-marker", action="append", default=[], help="private path substring that must not leak (repeatable)")
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "export":
            export(arguments.main_tex, arguments.output_dir, arguments.copy, arguments.strip_metadata, not arguments.no_compile, arguments.private_marker)
        else:
            leak_check(arguments.directory, arguments.private_marker)
    except ExportError as error:
        sys.stderr.write(ERROR_PREFIX + str(error) + "\n")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
