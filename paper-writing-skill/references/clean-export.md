# Stage Note: Strict Build Gate and Clean-Source Export (Story 014 FR-D3 / Story 009 FR-D5 / STD-005)

Companion deterministic helpers: `tools/evidence_export.py` (export), `tools/build_gate.py` (build gate).
The switch (`\evidencemarginfalse`) controls PDF display only; **the actual removal for submission is done by this export**.

## Strict build gate (Story 014, FR-D3)

A clean build embeds the submission SHA and evidence edition ID in the PDF, freezes the bibliography to a dated
version before drafting, and fails directly on citation errors or pinned-input hash mismatches (Manubot's default
tolerance of citations is a named anti-pattern).

```sh
# Before drafting: freeze the bibliography to a dated version (snapshot bytes + sha256 + date → bib-freeze.yaml)
python tools/build_gate.py freeze refs.bib --record bib-freeze.yaml

# Clean build: preflight verification + macro embedding + real pdflatex/bibtex compilation
python tools/build_gate.py build --tex main.tex --manifest evidence-manifest.yaml \
    --bib refs.bib --freeze-record bib-freeze.yaml --commit <40-hex-SHA> [--output-dir build]
```

Build preflight reuses Story 005/006's `tools/evidence_manifest.py`: each pinned input in the manifest is retrieved
using its recorded locator and its actual bytes are checked against sha256—the hash is not a retrieval method, and
HEAD is not used in place of uncommitted content. A mismatch fails, naming the artifact and expected/actual hashes;
missing files and unresolvable locators also fail.

The submission SHA and edition ID enter the manuscript through the generated macro file `build-info.tex` (the
templates convention is the same as 008, FR-D1: a macro file, not inline strings), via `\buildcommit` and
`\buildedition`, and are rendered with the PDF so they can be recovered using pdftotext. The tool generates the
macro file; do not edit it by hand.

**Bibliography freeze semantics**: `freeze` pins the bib bytes as a dated version; subsequent builds check the
current bib's sha256. A bib modified after freezing is **never silently adopted**—by default, the build fails and
explicitly reports the difference (freeze date, frozen/current hashes); `--use-frozen` explicitly selects building
with the frozen version and prints the same difference report. Re-freezing a new dated version is the only way to
adopt a new bibliography version.

**Failure semantics (no PDF claimed as successful is produced)**: nonzero pdflatex/bibtex exit, log entries such
as `Citation '…' undefined` / undefined citations, or missing bib entries cause build failure, naming the citation
key; every failure path deletes all PDFs in the output directory. The consumer-visible error uses exit code 2 and
one stderr line. Two further checks are required for a green result: the rendered PDF (via pdftotext) actually
contains the commit SHA and edition ID (the manuscript must `\input{build-info.tex}` and use
`\buildcommit`/`\buildedition`, otherwise it does not pass); and the first-pass `.aux` requests exactly the frozen
`--bib` file via `\bibdata`—bibtex's BIBINPUTS points only to the frozen copy in the build directory, and a
request for any other bib fails, with no resolution path outside the freeze.

**Boundary (green ≠ correctness)**: a green build proves plumbing only—it does not prove scientific correctness,
claim–evidence consistency, or language/figure quality. The build gate never runs scientific computation;
the claim–evidence map (FR-A3) sits above the build gate. The reproduction check (FR-D4 clean-environment rebuild)
is Story 015 and outside this gate's scope. This gate does not automatically adopt new material, recompute, or
fetch external citations.

## Usage

```sh
# Generate a clean copy (the working draft is never modified); by default, independently compile the working copy once with pdflatex (--no-compile skips this)
python tools/evidence_export.py export main.tex --output-dir clean-export \
    [--copy refs.bib --copy figures/fig1.pdf] [--strip-metadata evidence-metadata.tex] \
    [--private-marker /private/path/substring]...

# Check the export tree for leaks (consumer-visible pass/fail; failures include file:line)
python tools/evidence_export.py leak-check clean-export [--private-marker STRING]...
```

The export copies the entry `.tex` and local files referenced by its `\input`/`\include` commands (resolution is
restricted to the manuscript directory; escapes are rejected), plus additional files specified with `--copy`
(`.bib`, figures, etc.).

## Stripping boundary (only the dedicated evidence-metadata pattern is recognized; no general TeX transformation)

Strip only:

1. Each `\evidenceblock{ID}` invocation (if the entire line contains only that invocation, preserve the newline);
2. The generated `evidence-metadata.tex` file itself (it is not included in the export; passing it to `--copy` is rejected);
3. The `\input`/`\include` command that includes it—if a metadata-only include shares a line with other TeX, remove
   only the command and preserve the rest of the line exactly.

Files are processed using **binary I/O**: no newline normalization occurs; manuscript CRLF/CR/LF is preserved
byte for byte. If `\input`/`\include` resolves outside the manuscript directory and the target exists, fail loudly
(do not silently omit it).

Public content is preserved byte for byte: body text, public citations, data/code availability statements, figures
and tables, and `--copy` files. An `\evidenceblock` inside a `verbatim`-class environment is not rewritten; instead,
fail loudly and identify its location (evidence blocks are draft margin-note macros, not verbatim content).

## Leak check

Scan the export tree (skipping binary images/PDFs) for fixed markers: `evidenceblock`, `evidence-metadata`,
`evidence-manifest`, `evidence-snapshots`, and private-path substrings explicitly supplied by the caller via
repeatable `--private-marker` arguments—the caller is responsible for passing its own private roots. Any match
fails with exit code 2 and reports each `file:line` and matching pattern; no residue passes. After compilation
succeeds, `export` runs the same check itself (including the same `--private-marker` arguments); a leak fails the
whole operation, leaving the export directory available for inspection.

## Invariants

- Build gate (014): refuses if the output directory already exists (each build uses a fresh build tree); pinned inputs are retrieved by locator and verified; failure prevents compilation; the macro file is generated only by the tool.
- Working-draft bytes remain unchanged (export reads the working copy and writes only a new directory; refuses if `--output-dir` already exists).
- The exported source compiles successfully when compiled independently in its own directory.
- Exporting an ordinary manuscript with no evidence constructs produces body text equivalent to the input, and passes leak checking.
