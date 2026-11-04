# Stage Note: One-Time Pre-Submission Clean-Environment Reproduction Check and Package Metadata Record (Story 015, FR-D4 / FR-E1)

Companion deterministic helper: `tools/repro_check.py`; fixed-input retrieval reuses `tools/evidence_manifest.py`
(Story 005/006), and ignore-table comparison is implemented in `repro_check.py`. Run this check **once, only at the
submission-package stage**; do not run it for every draft iteration (Epic 004 Out of Scope).

## Clean-environment definition

A fresh directory (`<record directory>/clean`; refuse if it already exists—each check uses a fresh rebuild tree):
except for pinned inputs retrieved by their recorded locator and verified by sha256, **carry no working-tree state**.
Step processes use a restricted environment (PATH only, optionally plus an explicitly declared plan
`source_date_epoch`); the working directory is the clean directory. Environment variables are not inherited and
workspace files are not visible—if a step depends on an ambient input that is not pinned, it naturally fails inside
the clean directory. That is the gap the check is meant to expose, not an obstacle to bypass.

## Plan schema (pws.repro-plan/1)

```yaml
schema: pws.repro-plan/1
edition: "2026-10-21-submission1"
source_date_epoch: 1767225600        # Optional; only explicitly declared values enter the step environment
inputs:                              # Each pinned input = manifest artifact id + destination path in clean directory
  - artifact: result-data
    path: data/result.csv
  - artifact: macro-script
    path: make_macros.py
  - artifact: figure-script
    path: make_fig1.py
  - artifact: main-tex
    path: main.tex
steps:                               # At least one of each kind: re-extract macros + redraw figures + recompile
  - {id: macros, kind: macro, command: ["python", "make_macros.py"]}
  - {id: fig1,   kind: plot,  command: ["python", "make_fig1.py"]}
  - {id: pass1,  kind: tex,   command: ["pdflatex", "-interaction=nonstopmode", "main.tex"]}
  - {id: pass2,  kind: tex,   command: ["pdflatex", "-interaction=nonstopmode", "main.tex"]}
intermediates:                       # Declared compilation intermediates; no undeclared files may appear in the clean tree
  - macros.tex
  - main.aux
  - main.log
declared_outputs:                    # Declared output set (PDF + key figures) + explicit ignore table
  - path: main.pdf
    reference: references/main.pdf          # Reference copy (artifact from submission-package build)
    reference_sha256: "<sha256 after ignore-table normalization>"
    ignore:                                  # Individually named non-deterministic bytes; never ignore PDF differences wholesale
      - 'CreationDate \(D:[^)]*\)'
      - 'ModDate \(D:[^)]*\)'
      - '(?s)/ID \[<[0-9A-Fa-f]*> ?<[0-9A-Fa-f]*>\]'
  - path: fig1.pdf
    reference: references/fig1.pdf
    reference_sha256: "<…>"
    ignore: ['CreationDate \(D:[^)]*\)']
package_metadata:                    # FR-E1: record license and dataset ID per artifact in the same record
  artifacts:
    - {artifact: result-data, license: "CC BY 4.0", dataset_id: "10.5281/zenodo.xxxxxxx"}
    - {artifact: macro-script, license: "MIT", dataset_id: "not-applicable-private"}
    - {artifact: figure-script, license: "MIT", dataset_id: "not-applicable-private"}
    - {artifact: main-tex, license: "unknown", dataset_id: "unknown"}
```

Validation rules: missing any of `schema`/`edition`/`steps`/`inputs`/`declared_outputs`/`intermediates`/
`package_metadata` is a failure. Step `kind` must be `macro`/`plot`/`tex`, with **at least one of each kind**,
and order must put macro extraction/plotting before TeX compilation (compilation must consume re-extracted macros
and redrawn figures); there must be a tex step compiling the pinned manuscript source, and its stem must correspond
to a declared `.pdf` output. `tex` steps allow only bare `pdflatex`/`bibtex` plus **bounded allowlisted flags**
(`nonstopmode`/`batchmode`/`errorstopmode`/`scrollmode`, `halt-on-error`, `file-line-error`)—output redirection,
shell-escape, and engine/format switching are all rejected; `.tex`/`.bib` arguments must be declared pinned inputs.
`macro`/`plot` steps allow only a **bare-name** interpreter running a declared pinned script path (reject `-c` and
similar options, and interpreters with a path). Input/output/intermediate/`reference` paths must be relative, contain
no `..`, and be mutually distinct after normalization; plan `edition` must match manifest `edition`. Every pinned
input must have a package metadata entry; `license`/`dataset_id` must be non-empty and not placeholders (`todo`/
`tbd`/`<…>`, etc.); if genuinely unknown, write `unknown` truthfully rather than inventing compliance information.

`intermediates` (optional) declares compilation intermediates (`main.aux`, `main.log`, etc.); after the rebuild,
verify the clean tree's footprint: every file present must be a **regular file** declared as an input, declared
output, or declared intermediate—undeclared files and symlinks (such as a symlink to a working-tree reference
copy) fail. Every non-flag operand in a TeX step (including suffixless/absolute paths) must be a declared pinned
input. The ignore table uses individual regexes and length-preserving masks; patterns matching spans of arbitrary
length are rejected during validation. Verify based on **matched-byte coverage**—a comparison fails if coverage
exceeds half the output, regardless of pattern shape; native `~` bytes in the document do not count toward
coverage—**there is no "ignore all PDF differences" switch**.

## Steps and comparison

1. **Verify pinned inputs** (reuse Story 005/006): retrieve each input's actual bytes using its recorded locator and
   verify sha256—the hash is not a retrieval method; missing or mismatched content is never replaced by the current
   file (ADR-003). Resolve relative locators relative to the **directory containing the manifest file**; plan
   `edition` must match manifest `edition`.
2. **Verify reference copies**: normalize each declared output's reference copy using the ignore table, then compare
   with its recorded `reference_sha256`; an incomplete baseline fails.
3. **Record commands**: execute in order in the clean directory; nonzero exit/timeout fails and names the step.
   Reproduction ≠ rerunning science—macro extraction, plotting (running only pinned scripts on pinned data), and TeX
   compilation are derived operations permitted by FR-D1. Any case requiring recomputation to produce a figure/data
   fails and opens an FR-K3 handoff; never silently degrade.
4. **Compare declared outputs**: the ignore table consists of **individual regexes and length-preserving masks**
   (byte offsets remain unchanged after masking, so PDFs remain comparable); a normalized sha256 mismatch fails and
   names the file and expected/actual hashes. Known TeX metadata noise (`CreationDate`, `ModDate`, `/ID`) must be
   explicitly listed individually in the ignore table—**there is no "ignore all PDF differences" switch**.
5. **Verify clean-tree footprint**: after rebuilding, every file in the clean tree must be a declared input, declared
   output, or declared intermediate; any undeclared file fails and is named (build intermediates must be recorded in
   the plan, not silently tolerated).
6. **Record package metadata** (FR-E1): write `package_metadata` unchanged into the check record
   (`pws.repro-record/1` JSON) for Story 016 availability statements to consume; the tool does not verify scientific
   truth, and only rejects placeholders or missing values.

## Failure semantics (FR-K3)

If a pinned input is missing (including an artifact not registered in the manifest or an unretrievable locator) or
its hash mismatches, the check fails, names the artifact and expected/actual hashes, and writes a handoff draft
`repro-frk3-draft-<artifact>.md` in the record directory (a plain-text request, executed only after owner approval;
no approval automation). **Never rerun scientific computation, never substitute current-file bytes for a missing
old version, and never fabricate missing data to make the pipeline look "complete"**; a mismatched input is not
declared "reproduced." All failures return exit code 2 with a one-line readable stderr error, and the check record
is still written (`result: fail` and failure details).

## Invariants

- Read pinned inputs only (by locator); write only declared outputs in the clean directory and the check record/handoff draft in the record directory; no repository-wide scanning and no other side effects.
- The ignore table applies only to declared outputs and masks only explicitly listed patterns; verify comparison baselines (reference + normalized hash) before use.
- Reproduction ≠ correctness: green proves only that the submission package can be rebuilt from pinned inputs using the recorded commands; it does not prove scientific correctness, claim–evidence consistency (FR-A3 sits above this), or venue compliance (Story 016).
