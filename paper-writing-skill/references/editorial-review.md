---
description: Editorial-review stage guide — typed scientific and editorial checklists, finding format, prune proposals, and figure-review pilot gate
---

# Stage guide: Editorial review — typed scientific/editorial review, prune proposals, figure review (FR-A6/A7, FR-C1/C3 pilot gate)

This reference covers structural review of a complete draft: checklist passes for independent
scientific and independent editorial review (FR-A6), itemized prune proposals for author
confirmation (FR-A7), and the figure-review pilot gate (FR-C1 overlay + built-in checklist +
final-size visual inspection). Reviews produce findings and proposals for the author to decide;
they do not edit the manuscript, adjudicate scientific content, promote permanent rules, or add
mechanical checkers.

## Inputs

- The complete draft after structural revision and the whole-draft language pass in `drafting.md`.
- The confirmed Paper Plan: contribution statement, paragraph-level outline (intended point of
  each paragraph), and claim–evidence map.
- Artifact IDs in the evidence manifest (FR-D2/D5), adjacent `\evidenceblock` IDs in the draft,
  and their recorded intent/provenance in the manifest or generated non-rendered JSON metadata.
- The paper-specific figure-convention overlay, if any; otherwise the global figure defaults in
  `figure-style.md`.

## Finding format (FR-A6, shared by both review types)

Record each finding separately:

- **Location:** quote the key sentence verbatim and identify its manuscript sentence or paragraph.
- **Supporting reference:** a Plan item (outline entry) and/or artifact ID—**only when it truly
  exists**. For pure language, structure, or clarity issues, explicitly mark "language/editorial;
  no artifact association"; do not invent an ID.
- **Type:** `scientific` or `editorial`.
- **Issue:** describe the specific wording/scope/language/structure defect.
- **Recommendation:** proposed revision; a scientific recommendation must not change scientific
  content itself.

Scientific and editorial reviews run **independently** and produce separate lists. A single
integrating writer then consolidates them into a non-conflicting set of integration
recommendations. The writer integrates only; they do not unilaterally adjudicate scientific
disagreements (mark a disagreement finding `author-arbitration`, list the grounds on each side,
and refer it to the author), disguise editorial recommendations as scientific judgments, or
lower the evidence level of any finding during integration.

## Scientific review checklist (FR-A3/SPEC-004 boundary)

Check each item and either produce a finding or record that it passes:

1. Each conclusion-bearing statement matches evidence in the claim–evidence map; wording strength
   does not exceed the supported scope (state comparison conditions, approximation order, and
   system range accurately).
2. Labels assess the **wording and scope of the manuscript statement**, not the truth of an
   underlying assumption. Scientific review does not redo the science or demand deletion because
   a reviewer dislikes a conclusion.
3. Use refuting/negative results according to their recorded admissibility. If a negative result
   under a REFUTE label is used by the manuscript to argue for a "method boundary/applicability
   limitation," **retain that argument**: a counterexample can support a boundary statement and is
   not a defect.
4. Supersession: where new results make old ones obsolete, check whether the manuscript reflects
   the currently adopted version. Refer an unupdated statement as a finding to the author; do not
   rewrite it automatically.
5. State unverified mechanisms explicitly as hypotheses/speculation; fluent wording must not raise
   their evidence level.
6. Keep the specificity of the Abstract/Conclusion consistent with the evidence; no unsupported
   numbers or generality.

## Editorial review checklist

Check each item. Use the FR-B4/B5 language-completeness defect classes and exemptions in
`drafting.md`; record issues here in finding format rather than repeating that guidance:

1. Do all sections advance the same storyline, and does each paragraph serve its intended point
   in the outline?
2. Argument order: question/comparison conditions before evidence interpretation; no residue of
   research-log order. Use the [audience-shift check in drafting.md](drafting.md#from-plan-to-prose-changing-the-audience)
   to distinguish scientific argument from internal design narration. Does the Introduction
   explain motivation, prior work, and contribution, and close with a section route rather than a
   figure catalog? Are figure briefs, approvals, and TODOs kept in the workspace, with necessary
   scientific qualifications retained?
3. Are observation and interpretation distinguished, with limitations and applicability
   boundaries explicit in the Discussion?
4. Repetition: is the same argument developed in multiple sections? Handle this through a prune
   proposal; do not delete directly.
5. Division between figure and prose: does the prose avoid restating tables line by line or
   reading curves point by point? Do captions explain how to read the figure? Are implementation
   names absent from captions (script/package/format details belong in Methods)?
6. Are terms defined before use, pronouns unambiguous, and tense consistent? Record any remaining
   finding from the FR-B5 whole-draft pass in this format.
7. Does the draft match the current Plan/skeleton rather than superseded designs? Agreement on a
   design does not mean data, output, or visual review is complete. Refer items dependent on
   scientific disagreement to the author; do not reopen unrelated confirmed content.
8. **Evidence adjacency and rendered annotations:** for every actual figure, table, and
   load-bearing numerical claim, check that the corresponding adopted source is represented by
   an adjacent evidence block. A successful compile does not demonstrate evidence coverage. Check
   that gray annotations are readable at their rendered size, and that the display-off/export
   behavior works as specified in [the evidence-projection guide](evidence-projection.md).
   Record gaps or rendering failures as findings; do not treat projection as automatic adoption
   or certification of evidence coverage.

## Prune proposal (FR-A7)

Trigger once at the end of each complete-draft revision cycle and once before submission packaging.

**Read intent before proposing a prune (FR-D5):** resolve each candidate's block ID against
the authoritative claim–evidence manifest (or generated non-rendered JSON), rather than looking
for intent in the short rendered note. Similar-looking passages may serve different purposes.
Content whose intent still matches the text/evidence is **not proposed as orphaned/redundant**.
If intent and text/evidence differ, mark "intent requires author confirmation"; do not silently
redefine or delete it. Select "no intent annotation" only when the underlying record has none.

Record each proposal separately:

- **Location:** section/paragraph/figure/table.
- **Reason:** repetition of another passage (identify its location) / superseded by a later finding
  / temporary scaffolding / orphan claim (no longer needed for a confirmed contribution) / value
  below the length budget.
- **Proposed action:** delete / merge (state destination) / downgrade (for example, move to SI or
  appendix).
- **Intent check:** intent matches (do not propose) / intent requires author confirmation / no
  intent annotation.

**Confirmation granularity:** the author confirms proposals individually or in a batch of
explicitly listed items; do not bundle unlisted items into a batch. **Record rejections:** retain
the rejected item, reason, and rejection date. Do not propose it again in a later cycle unless
there is a new reason; state how that reason differs from the original.

Word-count reduction, successful compilation, or absence of lint warnings does not prove that
pruning is correct or that the writing is good.

## Figure review (FR-C1/FR-C3 pilot gate)

For every figure, proceed as follows:

1. **Paper-specific overlay first:** use the paper's figure-convention overlay when one exists;
   otherwise fall back to global defaults (`figure-style.md`) where the overlay is silent. Review
   against the overlay decision; do not renegotiate conventions already decided by the author.
2. **FR-C1 convention checklist:** no in-figure title; panel labels bold at upper left and `(a)/(b)`
   consistent throughout; no per-bar labels/marker labels/background reference lines (except
   physical features introduced in the caption); no implementation names in captions.
3. **Review actual rendered output:** inspect the real image after compile/export, not source code
   as a substitute.
4. **Final-size visual check (documented pilot gate):** render at the target layout's column width
   (86/90/89 mm) and visually inspect at actual size. Record whether type size, line width, and
   colors are readable at final size.
5. **`figure-gate`, if installed, is optional comparative input only:** append its output as
   findings alongside the built-in checklist. Tool availability does not require running it; PASS
   does not replace visual inspection. Do not build a duplicate JSON checker (SPEC-001).

Figure review proposes findings and changes; it does not redraw or edit figures automatically.
Treat equations, axis labels, and conventional caption titles according to the exemptions in
`drafting.md`; do not report them as defects.

## Boundary (intentionally outside this reference)

- Whole-draft language-pass guidance and FR-B4/B5 defect/exemption lists: drafting
  (`references/drafting.md`); record its results here in finding format.
- Manuscript file edits, scientific adjudication, automatic deletion/revision, Vale-rule promotion,
  or new checkers: out of scope. Keep review reports separate from author decisions
  (architecture ADR-004/ADR-006).
- Evidence-version pinning and freshness checks: evidence-check stage
  (`references/evidence-manifest.md`); cite its artifact IDs rather than repeating its
  verification. Manuscript integration still preserves/rebuilds adjacent evidence blocks and
  generated metadata; use `evidence-projection.md` and the editorial checklist above to assess
  rendered annotations and actual source adjacency.
