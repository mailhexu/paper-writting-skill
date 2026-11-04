# Stage Guide: Materials and Planning

Starting from existing research records, organize a materials set and writing plan for a paper. This stage organizes and recommends only: it does not edit the manuscript, run scientific computations, or migrate or rewrite original notes.

## Inputs

- Existing research records: Kosmic project notes, experiment/computation artifacts, and failed attempts (failed records are materials too; they may support methodological boundaries or counterexample arguments).
- Input materials need not already have hashes or machine metadata: numerical results copied from other computations, manually curated tables, hand-drawn diagrams, and hand derivations are all valid materials. When known, record the actual source and transformations honestly (when and where obtained, and how processed); when unknown, say "unknown" rather than inventing run metadata. Hash registration belongs to the later adoption stage, and a hash proves byte identity, not computational reproducibility or scientific validity.
- The author's paper goals: contribution statement and target journal/article type, if already decided.
- The author's existing writing and figure conventions: follow these by default; they are not suggestions.

## Positioning the Paper

Reuse information the author has already supplied to propose a short positioning card: scientific question, target readers and why they care, article type, specific increment, closest prior work, and scope boundaries. This is not a final Abstract or a field-by-field questionnaire; ask only about missing information that would materially change the paper's direction. If a Plan already exists, carry forward its current decisions.

Associate the closest literature with the specific positioning or claim from the outset. Mark unverified sources or novelty claims honestly; do not invent citations or infer scholarly priority from the absence of an implementation in the repository.

## Organizing Material Entries

- **One material = one clear idea**: a conclusion, figure, comparison, or known limitation. It need not correspond to a paragraph or section.
- Record three kinds of information separately for each item; do not conflate them:
  - **Use intent**: why the paper needs it and which step of the argument it serves (specific to this paper);
  - **Evidence status**: source record, freshness, and retrievability; record known status honestly, and mark retrievability "unknown" if it has not been hash-registered (hash registration belongs to a later stage);
  - **Adoption decision**: current state is `candidate / adopted / not adopted`; leave one sentence explaining a "not adopted" decision.
- Counterexamples, limitations, and failed comparisons must be included in the materials set and constrain the plan; do not hide them for narrative smoothness.
- Accepting the scientific content of a material does not mean accepting its original wording; wording belongs to the later drafting stage.

## Permitted Actions in This Stage

- Read relevant records and propose a materials list and organization (including a one-sentence summary of the main line when well-supported).
- Identify evidence gaps and distinguish retrieval/linkage problems from new research, rather than turning every gap into a computation task.
- Confirm the materials list with the author item by item; one confirmation may cover a batch of materials. Do not add a per-card approval process.

## Missing Material and Follow-up

Maintain a TODO in the workbench with explicit source links. Distinguish results that already exist but are not yet linked or need retrieval, genuinely missing evidence, new work needed only if a particular argument is adopted, and work the author has assigned to another executor. State what is missing, who owns it (use "unknown" if not known), and the next action; keep conditional tasks conditional and do not create duplicate tasks.

Delegated work remains pending until returned evidence has been reviewed and adopted; do not rerun it, infer results from the delegation, or implement what is missing. Record author-reported implementation status separately from the source linkage for any given curve.

Numerical claims and dependent figures wait for evidence; supported non-numerical portions may proceed within the approved scope. Verification requirements are not waived because data have not returned, and any scientific computation still requires separate authorization.

## Stage Exit

Record the author-confirmed materials set, a brief paper position, and existing ideas for contributions, figures, and sections on the workbench hub (`review.md`), and link the same Paper Plan. This is the planning input for the drafting reference, not a requirement to deliver a complete Plan first; the main line, sections/figures, and paragraphs are refined in layers and confirmed collaboratively.

## Workbench Hub Convention (`paper/<paper-id>/review.md`)

Use one hub page per paper, located in the vault Project at `Projects/paper-writing-skill/paper/<paper-id>/review.md`. Use a restricted ASCII `<paper-id>` containing letters, digits, and hyphens. The hub is outside OKF `notes/`: it is neither knowledge prose nor a manuscript, only a dynamic organizational view.

- **Cite in place; do not migrate.** Keep atomic notes where they are; cite them from the hub with ordinary wikilinks (when a basename is ambiguous, use the full vault path as the target, e.g. `[[Projects/TB2J/notes/xxx|xxx]]`), and embed with `![[...]]` when useful for review. Do not mirror knowledge prose or create automatic synchronization, watchers, or write-back.
- **Paper-specific material notes are an exception.** Put them in `paper/<paper-id>/pieces/` only when the proposed content needs independent organization or substantial paper-specific explanation. One clear idea per material; do not copy knowledge prose already present in the original note.
- **Separate intent / evidence / decision.** Record each material's three aspects separately beside its link; do not conflate them: use intent (why this paper needs it and which argumentative step it serves); evidence status (source record and freshness; record known status honestly, and use "unknown" for retrievability when not hash-registered); adoption decision (`candidate / adopted / not adopted`, with one sentence for "not adopted" and no repeated recommendation unless there is a substantive new reason).
- **List undecided items separately**; do not presume they are adopted. Accepting scientific content does not mean accepting its original wording.
- **Confirm a group at once.** Do not create a per-card approval system. After the material group and paper position are confirmed, continue in the same Paper Plan with the main line and outline in the order described by [drafting.md](drafting.md); do not demand a complete section/figure/paragraph plan early or treat candidate materials as confirmed inputs.
- **Everything remains a proposal until confirmed.** Before author confirmation, the agent's material organization, use intent, storyline, and figure/style recommendations are not the author's scientific decisions and must not be treated as adopted.
- **Recommend first; do not propagate changes to the manuscript.** Changes to source notes or use intent produce impact recommendations only. If the author requests an intent change or "separation of contributions", first recommend material organization and wait for the author's item-by-item confirmation; never propagate changes to the manuscript. Material changes do not authorize the agent to edit the manuscript, recompute, or automatically update anything already written.

## Boundaries (Intentionally Out of Scope)

- The complete main line and paragraph-level outline belong to the drafting stage; see [drafting.md](drafting.md). Drafting carries forward the confirmed material group and paper position, and does not pre-write manuscript prose during the materials stage or assume scientific decisions are confirmed.
- Evidence version pinning (hashes/manifests) is covered by [evidence-manifest.md](evidence-manifest.md) and the adoption/snapshot interface in `tools/evidence_manifest.py`; this stage does not duplicate registration or verification.
