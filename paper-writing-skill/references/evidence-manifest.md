# Stage Note: Evidence Check — Minimal Manifest Schema and Retrieval Conventions for Three Locator Types

**Implementation status (Story 005)**: This file specifies the minimal `evidence-manifest.yaml` schema, validation
rules, retrieval conventions, and failure semantics for three locator types (`git` / `snapshot` / `retained`); the
companion deterministic helper is `tools/evidence_manifest.py`. Implemented: schema validation and retrieval
(Story 005), verification and snapshotting during adoption (Story 006 `adopt`), and freshness checks with triage
reports (Story 007 `check`). **Outside this stage** (later Stories): TeX projection (008) and clean export (009).

## Principle (ADR-003)

Keep a small `evidence-manifest.yaml` beside the manuscript, recording only the **evidence actually adopted for the
paper**; candidate and not-yet-adopted material stays on the workbench and is not copied into the manifest. Each
artifact must have both a content hash and a retrievable locator. **A hash is never a retrieval method**: an entry
with only `sha256` and no locator is explicitly rejected during validation. The manifest is not a second
maintained copy of knowledge content.

The manifest covers **selected, pinned (adopted) evidence**, not all working material: loose inputs used for
writing (numerical results copied from other computations, manually organized tables, hand-drawn diagrams, manual
derivations) need not have hashes or metadata before they can be used. When material is adopted into the manifest,
hash its bytes as they are at that time; the hash proves consistency with the adopted bytes, not upstream
reproducibility or scientific validity. If the upstream source is genuinely unknown, record it as unknown rather
than inventing run metadata; not all material must be entered in the manifest.

## Manifest schema (evidence-manifest/1)

```yaml
edition: "2026-10-18-draft1"        # Version/content identifier for this evidence edition

artifacts:                          # Adopted evidence only; id must be unique
  - id: "tb2j-run-42"              # Short identifier (ASCII letters/digits/hyphens)
    sha256: "<64 lowercase hexadecimal characters>"    # Exact content hash of the adopted bytes
    locator:                        # Required — one of the following three
      kind: git                     # "git" | "snapshot" | "retained"
      repo: "/absolute/or/relative/path"      # git: recorded repository
      commit: "<full 40-character SHA>"        # git: full immutable commit at adoption (branch/HEAD references are not accepted)
      path: "runs/42/out.dat"       # git: repository-relative path at that commit
  - id: "uncommitted-note"
    sha256: "<64 lowercase hexadecimal characters>"
    locator:
      kind: snapshot
      path: "snapshots/uncommitted-note.dat"   # Snapshot file committed with the record
  - id: "retained-pack"
    sha256: "<64 lowercase hexadecimal characters>"
    locator:
      kind: retained
      path: "/kosmic/retained/pack/..."        # Actual readable location of an existing retained artifact

claims:
  - id: "claim-magnon-lifetimes"
    statement: "A one-sentence statement consistent with the manuscript wording."
    artifacts: ["tb2j-run-42"]      # Must refer to an existing artifact id
    intent: "The role of this evidence in this paper's argument (the paper's intended use)."
    judgment: support               # "support" | "refute" | "insufficient"
    reason: "Why the statement, with this wording, merits this judgment."
```

Validation rules (each violation produces one readable error identifying the field; see the CLI below):

- `edition` must be a non-empty string.
- Each artifact needs a non-empty `id`, a 64-character lowercase hexadecimal `sha256`, and a `locator`; duplicate
  artifact `id`s are rejected. An entry with **a hash but no locator** is rejected with an explicit error:
  "a hash is a content fingerprint, not a retrieval method."
- `locator.kind` must be exactly one of `git` / `snapshot` / `retained`. Missing `repo`, `commit`, or `path` on a
  `git` entry each produce an error; `commit` must be a full 40-character SHA (the exact commit recorded at
  adoption; a branch or HEAD must not be used as a substitute); `snapshot`/`retained` require `path`.
- Each claim needs non-empty `id`, `statement`, `intent`, and `reason`; `artifacts` must be a non-empty list whose
  artifact ids all exist; `judgment` must be one of `support` / `refute` / `insufficient`. Refuting and
  insufficient results are legitimate evidence when recorded as such.
- Unknown additional fields are not validated or rejected by this Story; schema evolution belongs to a later
  approved Story.

## Retrieval conventions and failure semantics

`retrieve` retrieves the pinned bytes and **checks `sha256` before declaring success**; a hash mismatch is a
consumer-visible failure, and retrieved bytes are never output as though they were the adopted version.

- **git** — Use `git cat-file` to retrieve historical bytes from the recorded repository at the recorded commit;
  first confirm that commit object exists in that repository. **Do not read the current working-tree file**: if the
  path does not exist at that commit, retrieval fails with an explicit report and current file bytes are not used as
  a substitute. Missing repository, missing commit, and missing path each produce an error identifying the locator
  field.
- **snapshot** — Read the snapshot file committed with the record; an unreadable path or hash mismatch fails with a
  report.
- **retained** — Read from the actual location in retained storage; failure semantics are the same.
- Relative path resolution: if `repo` and `path` are relative, resolve them relative to the **directory containing
  the manifest file**; use absolute paths as given. A missing repository (`repo` unavailable) and a missing commit
  produce separate errors identifying the corresponding field.

A pin whose bytes cannot be retrieved fails just like any missing artifact (Research Handoff, FR-K3): this skill
never claims that an edition whose content cannot be retrieved is "reproducible," and never recomputes or substitutes
for it.

## CLI

```sh
python tools/evidence_manifest.py validate  evidence-manifest.yaml   # Exit code 0; echo each artifact's retrieval path
python tools/evidence_manifest.py retrieve  evidence-manifest.yaml tb2j-run-42 --output out.dat
```

Any validation or retrieval failure returns exit code 2 and a one-line readable error identifying the field.
Dependencies: Python 3.11+ and PyYAML; a `git` locator requires `git` on PATH.

## Adoption (Story 006: `adopt`)

```sh
python tools/evidence_manifest.py adopt <current-file> \
    --repo REPO --commit <full 40-character SHA> --git-path PATH \
    [--snapshot-dir evidence-snapshots] [--artifact-id ID] \
    [--output-manifest-fragment FILE]
```

`adopt` performs only an **adoption decision already made by the author**: it verifies bytes and emits a YAML
fragment compatible with the Story 005 schema (`id` / `sha256` / `locator`); it makes no adoption judgment.

- **Match**: current file bytes exactly match the git blob at the recorded commit → pass; record the `git` locator
  (`repo`/`commit`/`path`), with `sha256` derived from the actual bytes.
- **Mismatch** (typically uncommitted/unpushed content): **never substitute HEAD bytes**. First distinguish two
  kinds of mismatch: if current bytes **match** the blob at the same path in HEAD (meaning the difference has been
  committed), fail explicitly (exit code 2) and report both the recorded commit and HEAD commit—neither version
  may be silently recorded, and no snapshot is created. Snapshot only if current bytes differ from both the blob at
  the recorded commit and the HEAD blob (or the path exists in neither, meaning genuinely uncommitted content).
  For a snapshot, copy current bytes into `--snapshot-dir` (create that directory only in this case; derive the
  filename from `--artifact-id` or the content hash, using safe ASCII), record a `snapshot` locator and the current
  bytes' sha256, and prominently print the snapshot path—**the snapshot must be committed with the record**. If the
  snapshot path exists with different bytes, reject (idempotent; use another `--artifact-id`); identical bytes pass
  idempotently.
- **Recorded commit cannot be retrieved** (garbage SHA / pruned): consumer-visible failure explaining why; never
  "fill in an old snapshot from the current file"; leave the manifest unchanged.
- If the current file does not exist → fail and identify `current-file`.

Invariant: `adopt` never misrepresents current bytes as content from the recorded commit; every failure returns
exit code 2 and a one-line readable error identifying the field.

## Freshness check and triage (Story 007: `check`)

```sh
python tools/evidence_manifest.py check evidence-manifest.yaml \
    [--report FILE]   # Prints to stdout by default
    [--records-dir DIR]
```

`check` is a **read-only command**: it asserts that manifest bytes are unchanged before and after running; it never
writes the manifest, automatically replaces anything, or chooses the preferred story. Replacing any adopted
edition requires the author's explicit approval (approval is an author-owned record action).

Deterministic layer (ADR-004, layer 1), retrieves and compares each artifact:

- `unchanged` — the recorded commit's blob matches the pin, and the same path in repository HEAD and the current
  working-tree file (if present) still match the pin.
- `content-changed` (modified-in-place) — bytes at the locator differ from the pin hash; or the recorded commit
  verifies but the bytes at the same path in HEAD have changed (pending text gives the HEAD commit and hashes on
  both sides); or HEAD and the recorded commit both match the pin but the current working-tree file bytes differ
  (pending explicitly identifies `working-tree` and its hash); or the path no longer exists in HEAD and the pinned
  content was not found in the HEAD tree. A missing working-tree path alone does not mean the source is invalid
  (the recorded commit may still be retrievable).
- `path-moved` — two triggers: (a) when the recorded locator cannot be retrieved from its commit, scan the
  **recorded commit tree**; (b) when the recorded locator verifies but HEAD no longer contains that path, scan the
  **HEAD tree** (current state). Tree scanning uses one `git ls-tree -z -r` (NUL-delimited; escaped paths are
  reported as their real paths) plus one `git cat-file --batch` to read blobs in a batch—complexity is bounded by
  tree size, with absolutely no process per blob. Report old locator path → new path.
- `source-lost` — the source is wholly unretrievable (including garbage commit, missing snapshot/retained file);
  write the failure reason to the report; **never fall back to any current file**. Mark affected claims in the
  report; never delete them or recommend deletion.
- `scientific-invalidation` — comes **only** from an explicit record marker (frontmatter
  `scientific_invalidation: true` + target + reason); the tool never infers this category itself.

Lifecycle channel (optional fields, backward-compatible; manifests omitting them continue to validate normally):

- Embedded in the manifest: `superseded_by` (id or text, string/list), `deprecated` (boolean; when `true`,
  `deprecated_reason` is required), and `counter_evidence` (text/list); may appear on an artifact or claim.
- `--records-dir DIR` (or explicitly skip with `--no-records-dir`; if neither is supplied, return exit code 2,
  because vault-record checking is part of the FR-D6 freshness workflow): a pilot **deterministic record-check
  layer**—scans only YAML frontmatter in `*.md` files (no full-text semantics), recognizing `superseded_by` /
  `deprecated` (**strict boolean**; string values are silently skipped; targets resolve as `artifact:` /
  `claim:` / `id:`, with explicit `artifact:` / `claim:` taking precedence over the record `id`; may include
  `reason` / `deprecated_reason`) / `contrary_evidence` (may have `artifact:` / `claim:` / `id:` subkeys) /
  `scientific_invalidation: true` (explicit markers only) / `status: superseded|deprecated`. Record-channel
  `contrary_evidence` and manifest-embedded `counter_evidence` are both labeled as candidates by
  `classify_counter_evidence`. Matching records enter the triage report. Files with no frontmatter or invalid
  formatting are silently skipped—they are not evidence about the manuscript.

Counter-evidence candidate labels (FR-A3 / SPEC-004): `classify_counter_evidence(text)` produces **purely
descriptive, deterministic candidate labels**, not scientific judgments—if text contains both failure wording and
a scope limitation, return `candidate-admissible (scoped-failure wording; requires claim-wording comparison
by reviewer)`; otherwise return `candidate-review-required`. **This layer never issues an "admissible/inadmissible"
verdict**: admissibility can only be decided after the agent/author compares the evidence, item by item, with the
wording and scope of the specific manuscript claim (the report explicitly states this under each
counter-evidence item). The literal word "SUPPORT" is never required.

Triage report format (fixed layout): for each finding, give the category (`path-moved` / `content-changed` /
`source-lost` / `superseded` / `deprecated` / `counter-evidence` / `scientific-invalidation`) and show
`CURRENT ADOPTED` (`id`, `sha256`, `locator`) alongside `PENDING CHANGE`; `content-changed` / `path-moved` /
`superseded` / `deprecated` / `counter-evidence` / `scientific-invalidation` each include a `COMPARABILITY TRIAGE`
block with fixed fields (`research question` / `structure` / `parameters` / `approximation` / `processing
conditions` / `scope`—all left open for the agent/author to fill; only the deterministic adopted-vs-pending basis
is prefilled). Artifact-level lifecycle/counter-evidence findings are resolved to manifest entries and list affected
claims (marked, never deleted; `review status: paused pending author review`; unmatched targets retain record-level
attribution). Source-loss findings include an FR-K3-style `REQUEST (draft)` recovery-request draft (plain text, no
approval automation). The report ends with a fixed replacement-policy statement: replacement requires the author's
explicit approval; `check` never writes manifest bytes (`--report` is rejected if its target resolves to the
manifest itself or a hard link to the same inode); and FR-D6 requires records before declaring "no change"
(agent layer-2 judgment). Scientific comparability is an agent judgment, not a rules engine.
