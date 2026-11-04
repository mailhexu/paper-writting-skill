---
name: paper-writing-skill
description: >
  Prepare journal papers from recorded physics and scientific-software research: refine
  the paper's positioning, storyline, sections and figures, paragraphs, and reader-facing
  prose. Load material/plan, drafting, evidence, editorial-review, graphics, or submission
  guidance as needed, and carry forward confirmed decisions.
  Scientific facts and evidence come only from existing research records; this skill
  performs no scientific computation and does not alter research data.
---

# Paper-Writing Skill — Entry Router

## Purpose

This skill organizes writing from research records to journal paper: it gives stage-specific
guidance and checklists, does not mirror research knowledge, introduce a scientific-computing
engine, or replace the paper's existing build system (LaTeX/figure build commands remain
responsible for macros, figures, and PDFs). Scientific content stays in its original records
(Kosmic notes/artifacts); references here explain how to use those records without copying
their content.

## Authorial boundaries (apply at every stage)

1. **Only the author decides scientific content.** Before changing scientific meaning,
deleting/merging/downgrading content, or replacing key evidence, offer a reasoned proposal;
execute only after the author confirms each item. The agent does not make linked manuscript
changes on its own.
2. **Do not run scientific computations automatically.** If evidence is missing or a result
is doubtful, report the issue and propose a Research Handoff; do not recompute, fill in data,
or select evidence to suit a narrative.
3. **Do not fabricate.** Create no citations, numbers, figures, or "to be filled" placeholders.
Report an unimplemented stage as undelivered; do not pretend its guidance exists.
4. **Keep knowledge single-sourced.** Add only use intent and adoption/candidate decisions to
material entries; do not rewrite or copy original notes, which would create a second body of
knowledge.
5. **Do not install or publish globally.** The files in this skill package are its complete
capabilities; installation/publication requires separate approval.

## Choose a stage

First read the paper's existing Plan, workspace, and current decisions; identify the first
unresolved, authorized task, then **load only the reference needed now**. Carry prior work
forward rather than starting over. After completion, load the next reference only if
continuation is authorized; do not preload the whole workflow.

| Stage | Reference | Status |
|------|-----------|--------|
| Materials/plan | [references/material-plan.md](references/material-plan.md) | Available |
| Drafting (storyline, section/figure design, paragraphs, prose) | [references/drafting.md](references/drafting.md) | Available: top-down planning and confirmation points, living skeleton, section drafting, FR-B4 language completeness, FR-B5 whole-draft language pass and Vale promotion threshold |
| Evidence check (manifest validation, retrieval verification) | [references/evidence-manifest.md](references/evidence-manifest.md) | Available: manifest schema validation and retrieval through three locator types (Story 005); byte verification and snapshot at adoption (Story 006 `adopt`); freshness checks and triage report (Story 007 `check`), all via `tools/evidence_manifest.py`. TeX projection is below (Story 008); clean export is Story 009. |
| Evidence margin annotations (TeX projection) | [references/evidence-projection.md](references/evidence-projection.md) | Available: generated `evidence-metadata.tex` projection and `\evidenceblock`/`\evidencemarginfalse` controls via `tools/evidence_projection.py` |
| Editorial review (science/editorial checklists, prune, figure gate) | [references/editorial-review.md](references/editorial-review.md) | Available: typed finding format, independent science/editorial checklists, prune proposals and rejection records, figure-review pilot gate (Story 012). The post-structural-revision whole-draft language pass (FR-B5) belongs to drafting and is covered by [references/drafting.md](references/drafting.md); record its results here in finding format. |
| Figures (design and verification) | [references/figure-style.md](references/figure-style.md) | Available (global defaults; paper-specific conventions may override, with explicit deferral in the reference) |
| Submission (build gate, clean export, reproducibility check, compliance) | [references/clean-export.md](references/clean-export.md), [references/repro-check.md](references/repro-check.md), [references/submission.md](references/submission.md) | Tools available: `build_gate.py`, `evidence_export.py`, `repro_check.py`; `submission.py` provides venue, availability statement, AI disclosure, cover letter, figure-file, citation-key, and BibCheck whole-file/single-key read-only metadata checks. Required figure inspection and actual submission remain the author's responsibility. |

**Manuscript integration trigger:** whenever authorized work assembles or revises the manuscript,
preserve existing adjacent evidence-block calls and their generated metadata; rebuild the metadata
from the current evidence manifest and draft, and load [references/evidence-projection.md](references/evidence-projection.md).
Treat this as part of manuscript integration, not an optional independent evidence stage.

For an unimplemented stage, tell the user plainly that its capability has not been delivered and
requires an approved Story before implementation. Do not cite nonexistent files or substitute
generic writing advice for stage guidance.

Ask one specific question only when existing records and the user's request do not determine the
next step and the choice would change the work; do not ask for stage labels or reconfirm known
answers.

## Usage rules

- "Next / continue" means the next evidence-based task within the approved scope; it does not
  approve unseen scientific conclusions, designs, or computations. Respond with current progress,
  concrete output/change, and next action; ask only about material unresolved issues.
- Record outputs and decisions in the project's existing Kosmic records/workspace, not as
  paper-specific state accumulated inside this skill package.
- Defer by default to the author's existing conventions (figures, style, journal practices).
  Raise conflicts before proceeding; do not override them unilaterally.
