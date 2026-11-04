# Paper-Writing Skill

A staged workflow for turning existing physics and scientific-software research records into a journal manuscript. The package supplies guidance and read-only/checking tools; it is not a scientific-computing engine, manuscript build system, or submission service.

## Start here

Read [`paper-writing-skill/SKILL.md`](paper-writing-skill/SKILL.md). It is the workflow router: inspect the paper's existing Plan, workbench, and decisions; identify the first unresolved, authorized task; then open only the linked reference for that stage. The router and references are the skill package. This repository does not install the skill into an agent, publish it globally, or authorize installation.

The workflow builds on prior decisions rather than restarting:

1. **Position and gather materials.** Confirm the paper's question, audience, contribution, scope, and author-selected materials. See [Materials and Planning](paper-writing-skill/references/material-plan.md).
2. **Develop the argument from the top down.** Continue the same Paper Plan from storyline to section and figure roles, paragraph arguments, and reader-facing prose; preserve the existing confirmation points. See [Drafting](paper-writing-skill/references/drafting.md).
3. **Check evidence when needed.** Validate, retrieve, adopt, or freshness-check evidence through the [evidence manifest guide](paper-writing-skill/references/evidence-manifest.md). For manuscript margin notes, use [evidence projection](paper-writing-skill/references/evidence-projection.md). For figure conventions and final-size visual checks, see [figure style](paper-writing-skill/references/figure-style.md).
4. **Review and prepare the package.** Follow the [editorial review](paper-writing-skill/references/editorial-review.md), [clean export/build gate](paper-writing-skill/references/clean-export.md), and [reproduction check](paper-writing-skill/references/repro-check.md) as applicable. Use [submission preparation](paper-writing-skill/references/submission.md) for venue, availability, disclosure, cover-letter, figure-file, citation-key, and bibliography checks.

Scientific meaning and evidence choices remain under author control. The skill does not run scientific computations, invent sources or results, silently change the manuscript, or submit a paper. Missing evidence is reported for follow-up rather than recomputed. A mechanical pass is limited to the checks it actually performs; it is not scientific validation or author approval.

### Example conversation

Point your agent at `paper-writing-skill/SKILL.md`, then give it the existing notes, manuscript location, and current decisions:

> Use this skill for a methods paper based on these research records. First help me agree on the paper's question and storyline; do not draft the manuscript yet.

Continue with concrete requests such as “Define the section roles and figure briefs,” “Show a checkbox skeleton with the key points,” and “Draft the approved Methods section.” For an existing paper, provide its current Plan and say “Continue from the next unresolved item.” The agent should reuse confirmed decisions, ask only about material choices, and keep missing calculations on the follow-up list.

## Using the command-line tools

Run commands from the repository root with the Python environment already used for the paper. There is no package-wide installer. The evidence-manifest CLI requires Python 3.11+ and PyYAML; Git-based retrieval also requires `git` on `PATH`. The optional submission PDF/PNG checks use the dependencies in [`requirements-submission.txt`](paper-writing-skill/requirements-submission.txt); PDF font checks additionally require Poppler's `pdffonts` on `PATH`. Bibliography metadata verification requires an installed BibCheck package exposing its supported read-only `verify_bib_file` interface. Consult each reference for a command's inputs, dependencies, and limits.

TeX projection/export/build exercises also need a working LaTeX installation (`pdflatex`, and `bibtex` where used); PDF verification uses Poppler's `pdftotext`. The helpers are script entrypoints, not an installed Python library with a promised public import API.

Validate or retrieve pinned evidence:

```sh
python paper-writing-skill/tools/evidence_manifest.py validate evidence-manifest.yaml
python paper-writing-skill/tools/evidence_manifest.py retrieve evidence-manifest.yaml artifact-id --output retrieved.dat
```

Generate the TeX evidence-note metadata from a manifest and draft; the generated metadata file is not edited by hand:

```sh
python paper-writing-skill/tools/evidence_projection.py generate evidence-manifest.yaml --tex main.tex --output evidence-metadata.tex
```

If using packages that require hyperref first, load hyperref explicitly before them. For example:

```latex
\usepackage[colorlinks=true,urlcolor=blue]{hyperref}
\usepackage{cleveref} % optional; requires hyperref first
\input{evidence-metadata.tex}
```

Multi-source claims show one source plus a short `+N sources` link to the complete manifest. Git sources always use an explicitly labeled `(locator)` link to their recorded provenance, independent of checkout state; the evidence CLI retrieves the pinned bytes. Snapshot/retained sources link to their recorded local files.

Draft calls use `\evidenceblock{claim-id}` and include the generated file once with `\input{evidence-metadata.tex}` in the preamble. The generated gray note is intentionally brief: it identifies the claim and evidence edition and links the source by basename with a short SHA. The manifest remains the authoritative full provenance record. `\evidencemarginfalse` hides these notes in the PDF only; it does not remove their source from the TeX. To create a clean source export, use the dedicated export tool, which removes the evidence annotations and generated metadata while preserving public manuscript content:

```sh
python paper-writing-skill/tools/evidence_export.py export main.tex --output-dir clean-export
python paper-writing-skill/tools/evidence_export.py leak-check clean-export
```

For submission checks, see the complete command list and schemas in the [submission reference](paper-writing-skill/references/submission.md). For example:

```sh
python paper-writing-skill/tools/submission.py citation-check --tex main.tex --bib references.bib
python paper-writing-skill/tools/submission.py figure-check --venue prb --manifest figures.json
```

These checks do not submit the package, rewrite the bibliography, or replace manual figure inspection. Venue rules must be rechecked against current publisher guidance and recorded in the input. Other tools such as the strict build gate and clean-environment reproduction check have their own required setup and input contracts; use their references rather than assuming defaults.

## Package map

- [`SKILL.md`](paper-writing-skill/SKILL.md) — stage router and authorial boundaries.
- [`references/`](paper-writing-skill/references/) — stage-specific procedures and safety limits.
- [`tools/`](paper-writing-skill/tools/) — command-line helpers; see each reference for supported use.
- [`configs/venue-profiles.json`](paper-writing-skill/configs/venue-profiles.json) — venue check profiles and their cited sources.
- [`templates/`](paper-writing-skill/templates/) — generated metadata/build templates; do not hand-edit generated outputs.
