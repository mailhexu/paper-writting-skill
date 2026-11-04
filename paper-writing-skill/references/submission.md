# Stage Guide: Submission Preparation and Checks (Story 016)

Companion tool: `tools/submission.py`; venue parameters: `configs/venue-profiles.json`.
This stage prepares and checks a submission-ready package only. It does not submit the paper, choose a venue for the author, confirm scientific content, or change the bibliography.

## Invariants and Status

- **A complete package is not necessarily ready to submit; the author submits and records the actual submission.** Every JSON report carries this boundary statement. Passing means only that the items checked by this tool passed; it does not certify editorial compliance, scientific conclusions, or author approval to submit.
- The source and `checked_on` date for venue requirements accompany each check output. The tool does not fetch policy updates. Before running it, the author must verify each current requirement and explicitly record the verification date and `current_policy_rechecked: true` in the input. Mechanical checks of article types and quantity limits apply only to fields with explicit supporting sources; failure to find a limit does not prove that no limit exists.
- Do not substitute generic defaults for an unknown venue. The CPC article-type details in the configuration come from historical guidance and **are not verified current submission requirements**; recheck current guidance before use.
- PDF supports semantic and size-extraction checks; text, font, and palette checks for PNG are `manual-required`. Vector/extraction rules do not replace final-size visual inspection; the pilot visual inspections in Stories 018/019 remain required.
- `pass` in any report means only that an explicitly checked mechanical rule or author-supplied rule passed. Consistent source metadata does not mean a bibliography entry is real, that the literature supports a claim, or that the claim itself is true.

## Commands

Run from the repository root:

```sh
python paper-writing-skill/tools/submission.py venue-check --venue prb --submission submission.json --figure-manifest figures.json
python paper-writing-skill/tools/submission.py availability --record repro-record.json --manifest evidence-manifest.yaml
python paper-writing-skill/tools/submission.py disclosure --venue npj --usage ai-use.json
python paper-writing-skill/tools/submission.py cover-letter --title 'Manuscript title' --venue 'Physical Review B' --plan paper-plan.json
python paper-writing-skill/tools/submission.py figure-check --venue prb --manifest figures.json
python paper-writing-skill/tools/submission.py citation-check --tex main.tex --bib references.bib
python paper-writing-skill/tools/submission.py bibliography-check --bib references.bib
python paper-writing-skill/tools/submission.py bibliography-check --bib references.bib --key Smith2020
```

Each command emits JSON `pws.submission-report/1` to stdout. Exit code `0` means success; check failure, unknown venue, or an outstanding manual check returns `1`; argument errors are reported by argparse. Invalid input also produces a JSON failure report with the boundary statement. The tool reads but does not submit or rewrite the manuscript or `.bib`, and does not recommend automatic bibliography edits.

## Venue Checklist Input

`venue-check` accepts a JSON object through `--submission`. Field names and enumerated values are determined by the rules listed in the parameter file. Each check reports `pass` / `fail` / `manual-required`, a detailed reason, source URL, verification date, and caveat. Missing required fields, invalid types/values, or an indeterminate article type fail. The current profiles cover:

- `prb`: `article_type` (`regular_article` or `letter`), `word_count`, `body_stands_alone_without_supplement`, `current_policy_checked_on`, and `current_policy_rechecked`. Letter uses the configured 4500-word limit; regular article length is recorded, but no other requirement is inferred from the absence of a located overall limit. `ai_use` is `none` / `basic` / `substantive`; the profile requires `ai_disclosure: true` for substantive use.
- `cpc`: `article_type` (`computer_programs_in_physics` or `computational_physics`), `current_policy_checked_on`, `current_policy_rechecked`, and required `ai_use` (`none` / `manuscript_preparation` / `research_process`); both generative-AI use categories also require `ai_disclosure: true`. The Computer Programs in Physics type also requires `program_summary`. Article type and abstract rules are based on historical guidance and must be rechecked when submitting.
- `npj`: non-negative integer `word_count`, non-empty string `data_statement`, `central_custom_code`, `supplementary_methods`, `figure_legend_words`, and policy recheck fields. When `central_custom_code: true`, a non-empty `code_statement` is required; Methods must not be moved to Supplementary Methods; figure legend text must not exceed the configured 350 words. `ai_use` may be `none` / `basic` / `manuscript_preparation` / `research_process` / `substantive`; non-`none` use requires `ai_disclosure_location`.

AI categories are explicitly mapped in each venue profile to either "disclose" or "no disclosure required"; an unmapped venue/category combination fails rather than defaulting to an exemption. AI-use scope must reflect the author's record of actual use; do not guess that there was no use. For details and sources, consult `venue-profiles.json`; do not duplicate this explanation as a second editable policy table.

## Availability Statement (FR-D4 Package Metadata)

`availability` consumes a Story 015 `pws.repro-record/1` JSON record and its evidence manifest. The record must have `result: pass`, an edition matching the manifest, and at least one pinned input. Every input must be `verified`, with its recorded `sha256` and locator checked against the corresponding artifact's hash and location in the supplied manifest. Resolve a record locator relative to the directory of the absolute original `manifest` path recorded in that record; resolve a supplied-manifest locator relative to that manifest's directory. If the record lacks a usable absolute original manifest path, the base for relative locators cannot be established and a gap must be reported. The field report gives the record JSON Pointer, the verified hash/locator, and the manifest locator.

Every input artifact must also have non-empty, non-placeholder `license` and `dataset_id` values in `package_metadata.artifacts`. Missing fields, `unknown`, placeholders, missing manifest entries, unverified inputs, and hash/locator mismatches are reported as individual `gaps`; no placeholder text is generated. This result traces recorded metadata; it does not prove a URL is accessible, a license determination is correct, or that data/code have been made public.

## AI Disclosure

The `disclosure` JSON input must explicitly specify `use`. Each profile lists categories that do not require disclosure and categories that do; only explicitly exempted categories return an empty text result. An unmapped category fails rather than being silently exempted. When disclosure is required, the author must also supply `tools` (`[{"name":"...","model":"..."}]`), `purpose`, `human_review`, `responsibility_statement`, and `placement`; the tool fills the venue-specific template from these facts. Missing facts cause failure; the tool does not invent them. An unknown venue explicitly requests current policy verification and does not apply any template.

## Cover Letter

The command requires a `pws.paper-plan/1` JSON adapter with at least the following fields; the minimal shape is:

```json
{
  "schema": "pws.paper-plan/1",
  "status": "approved",
  "source": "<author-approved Paper Plan record locator>",
  "contributions": ["<approved contribution item>"]
}
```

`source` must identify the authoritative, author-approved Paper Plan record, and `contributions` must transcribe its approved contributions verbatim, item by item. The tool rejects a missing plan, schema mismatch, non-`approved` status, or missing source/contributions. The generated draft lists contributions individually and returns the adapter path and source locator.

**This JSON is a consumer adapter for passing approved record content; it is not a Kosmic record type or approval mechanism. The tool checks only adapter fields; it does not verify the source record, approver, or authenticity of approval. Do not present a manually fabricated or unapproved adapter as an approved plan.** The current skill materials stage does not provide a machine-readable Paper Plan exporter; an author/integrator must first construct the adapter from the real approved record. Preserve this source-authenticity boundary; never claim that the tool certifies author approval.

## Figure File Checks

`figure-check` and `venue-check --figure-manifest` accept a JSON manifest with relative paths; for example:

```json
{"figures":[{"path":"figures/fig1.pdf","column":"single","panels":["a"],"panel_regions":{"a":[0,0,1,1]}}]}
```

Paths must not be absolute, contain `..`, or resolve outside the manifest directory. Each file must declare `column` and explicitly list expected `panels` (use `[]` when there are no panels); optional `panel_style` is `parenthesized` (default, `(a)`) or `bare`. To check relative panel positions automatically, `panel_regions` may supply normalized `[x0,y0,x1,y1]` rectangles keyed by panel letter, with the origin at the page's upper-left; labels must fall in the upper-left quadrant of their corresponding panels. If a panel's bounds are missing, its position report is `manual-required`; do not infer lower-row placement from whole-page height. For CPC figures containing raster content, specify `artwork_type` (`halftone` / `combination` / `line_art`) to select the resolution threshold.

- Only single-page PDF/PNG files in configured formats are checked. Checks include physical page width, title candidates in extracted text, panel presence/boldness, sans-serif families, font size, and configured palettes. No title candidate does not prove the absence of a left-aligned or short title, or a title below a panel: in that case `embedded-title` is `manual-required`; a candidate title fails. Panel position is checked against declared panel bounds; missing bounds require manual review. PDF font-size checks screen only extractable text: an explicitly identified superscript below 6 pt, or text below 6 pt without a superscript flag, fails. Text between 6 and 7 pt without a superscript flag may be subscript, so it is `manual-required`; `flags` are not used to infer subscript semantics. Missing configured 8 pt body text also fails. Other font-size checks with no detected defect remain `manual-required` because text extraction completeness and visual font size cannot be proven. PNG text and font size always require manual review.
- PDF font embedding is checked with `pdffonts`. If vector/text content includes non-neutral colors outside the categorical palette, color review is `manual-required`, not failure, to allow viridis/Crameri continuous maps while avoiding false assurance about unknown colors. PDF raster DPI and manual color review use PyMuPDF `get_image_info(xrefs=True)` to enumerate displayed images, including inline images; the DPI threshold allows 0.01 dpi for floating-point/resolution-metadata rounding.
- PNG checks actual PNG format, embedded DPI, and calculated physical width. Text, font, panels, print-size legibility, and color are all `manual-required`; overall status therefore cannot incorrectly report `pass`.
- The current profiles set single-column widths at 86 mm for PRB, 90 mm for CPC, and 89 mm for npj; CPC additionally supports 140/190 mm, npj 183 mm, and PRB 172 mm. Consult venue profiles and `figure-style.md` for font, palette, resolution settings, and sources. A mechanical result is not a completed print-size visual review.

Final-size visual inspection must also check that content such as axis labels is not clipped by page edges; complete extracted text or no mechanical failures cannot replace this check.

Optional PDF/PNG checking dependencies can be installed with:

```sh
python -m pip install -r paper-writing-skill/requirements-submission.txt
```

PDF checks also require Poppler `pdffonts` on the system `PATH`; the tool does not install it. If font embedding cannot be checked, that item fails.

## Citation Keys and the External `bibcheck` Boundary

`citation-check` parses common TeX citation commands (including lowercase `\parencite` / `\textcite` and each argument group in multicite commands such as `\cites{...}{...}`) and compares them with `.bib` entry keys, identifying keys cited in the body but absent from the bibliography. Citations in comments are ignored. This local check does not query DOI/arXiv, assess entry metadata, determine whether a citation supports a manuscript claim, or write to either input; metadata agreement does not establish scientific support.

`bibliography-check` verifies metadata through the supported `bibcheck.bibcheck.verify_bib_file` Python interface; it does not duplicate DOI/arXiv lookup or comparison logic. The environment must have an installed BibCheck package containing that read-only interface. A missing package or older version without the interface yields an explicit dependency error; the tool does not fall back to an older command that writes files and does not treat local key matching as metadata verification. The tool does not install dependencies or hard-code a developer-machine source path.

| Argument | Meaning |
|----------|---------|
| `--bib` | Required; path to an input `.bib` file, not BibTeX text. |
| `--key` | Optional; exact, case-sensitive citation key. If omitted, verify all entries and report them in input order; if provided, query and report only that entry. The entire file syntax is checked first; an empty, absent, or ambiguous key fails before lookup. |

The JSON report follows `pws.submission-report/1`; `verification` preserves BibCheck's original structured report, including each entry's status, query source, raw `{field, original, proposed}` differences, unavailable fields, reasons, and author-approval notice. Comparison uses BibCheck's default configuration; this tool does not introduce another configuration or reporting protocol.

| BibCheck `verification.outcome` | Tool `status` / exit code |
|----------------------------------|---------------------------|
| `clean` | `pass` / 0 |
| `differences` | `fail` / 1, suggestions preserved and not applied |
| `unverifiable` | `fail` / 1, preserving `missing_identifier`, `no_match`, `query_failure`, and other valid outcomes |
| `error` | `fail` / 1, preserving explicit input/selection errors |

Python integrators may call `submission.bibliography_check(bib_value, *, key=None)` when the tool module's directory is on the import path; it returns the same outer dictionary and does not print or write files. To use BibCheck's comparison configuration directly, use its own supported `verify_bib_file` interface rather than modifying or bypassing this check.

Checks do not rewrite the author's `.bib`, adjacent corrected/order-only files, or persistent cache. Missing identifiers, no reliable match, and query failure are not passes; known differences in a mixed report do not hide entries that could not be verified. The author must approve any suggested changes. Metadata consistency does not establish that a cited work supports the manuscript's scientific claim.
