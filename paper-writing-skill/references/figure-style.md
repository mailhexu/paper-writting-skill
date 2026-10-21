---
name: figure-style
description: Use when creating or revising matplotlib figures destined for physics or scientific-software journal papers (Physical Review, Computer Physics Communications, npj Computational Materials). Encodes publication-grade figure construction — no chart titles, print-size typography, colorblind-safe palettes, vector output — plus the pilot verification pass (built-in checklist + final print-size visual inspection). Defers to the author's per-paper conventions; this global reference is the fallback, not the override.
---

# 图形风格（全局缺省；逐篇约定可覆盖）

**Status: input-status statement.** This reference is the revised figure-style
draft adopted per Story 003 (ADR-006 conflicts corrected). It does **not**
claim the full FR-C2 architecture: the planning-mode router split and the
AI-imagery policy gate are **not implemented** (post-pilot items, PRD decision
6). The pilot graphic gate is exactly the built-in checklist plus the final
print-size visual inspection below; `figure-gate` is an *optional comparison*,
never a second mandatory gate.

## 约定层级与 deference（FR-C1 overlay）

1. **逐篇约定是缺省，不是建议。** 作者的 per-paper 约定（managed library 中
   的 per-paper 技能与笔记，以及记录在论文工作台 `paper/<paper-id>/` 的逐篇
   约定——overlay）优先于本 reference 的每一条全局规则。
2. **缺省回落。** 某篇论文没有相应 overlay 条目时，回落到本 reference 的全
   局缺省；不要为缺项发明规则。
3. **冲突先提出。** 本 reference 与某篇论文的 overlay 冲突时，按 overlay 执
   行；若疑似 overlay 有误，向作者提出，不擅自改稿或改 overlay。
4. 本 reference 不自我扩张：不新增规则库自动增长机制，不把观察到的失败自动
   晋升为永久 Vale 规则（规则晋升须作者批准，FR-B5/ADR-006）。

## Grounding

Rules encode the verified publisher specs for the three target venues — npj
Computational Materials submission guidelines (sans-serif lettering, optimum
8 pt at final size, ≥300 dpi, lines ≥1 pt after reduction, lowercase bold
panel labels, no truncated histogram axes, no red/green contrast, no rainbow
scale, legends described in words), Elsevier artwork sizing (7 pt finished
lettering, 30/90/140/190 mm widths), and REVTeX/APS figure handling plus
accessibility guidance (readable palettes, meaning not carried by color
alone). npj series journals do not redraw display items in production — the
author's figure ships as-is. Publisher specs are prose and can change:
re-verify the venue pages at submission time.

## Construction rules

1. **No titles, ever.** Do not set `ax.set_title`, `plt.title`,
   `fig.suptitle`, or a text annotation acting as a title. The LaTeX caption
   carries the message. If the reader needs a heading to know what a panel
   shows, the caption is deficient — fix the caption, not the figure.
2. **Build at final print size.** Create the figure at the physical column
   width it will occupy; never build large and shrink. Text must be legible
   *after* placement at that size. Venue widths:
   - Physical Review (REVTeX): 86 mm single column (`figure`), 172 mm double
     (`figure*`).
   - Elsevier / CPC: 90 / 140 / 190 mm (single / 1.5 / double).
   - npj Computational Materials: 89 mm standard, 183 mm full width.
3. **Typography.** One sans-serif family and one size for the whole paper,
   every figure: 8 pt body at final size (floor 7 pt; absolute minimum 6 pt
   for sub/superscripts — Elsevier's floor). Tick labels may be 7 pt.
   Mathtext in the same family (`mathtext.fontset: dejavusans` with DejaVu
   Sans, or set both to Nimbus Sans/Helvetica if available). Never mix
   families across figures.
4. **Line work.** Data lines ≥1.0 linewidth (≈1 pt) at final size;
   axis/spine/tick lines may be 0.5–0.8. Distinguish series by linestyle and
   marker shape in addition to color, so every figure survives grayscale
   printing.
5. **Color.** Colorblind-safe palettes only: Okabe–Ito categorical set,
   viridis-family or Crameri (`cmcrameri`) continuous maps. Never red/green as
   the sole contrast; never jet/rainbow. Color is never the only encoding —
   pair it with linestyle, marker, or direct labeling.
6. **Axes.** Label every axis with quantity and unit, symbol first:
   `Exchange interaction $J_1$ (meV)`. SI units, thin space between number and
   unit. Do not truncate the value axis of bar charts or histograms to
   exaggerate differences (npj explicit). Break an axis only with an explicit
   caption note. Light grid at most, only when it aids reading against a
   light background.
7. **Panels.** One file per composite figure (never ship panels separately).
   Label panels with bold lowercase letters placed top-left inside each panel,
   same type size as tick labels; the caption describes each panel by letter.
   Exact rendering follows the manuscript's established convention and stays
   consistent within a paper — the author's existing papers use `(a)`, `(b)`
   top-left; npj's guideline shows bare bold `a`, `b`. Never mix conventions
   in one manuscript.
8. **Legend and caption contract.** Keep in-figure legends minimal (no box).
   Symbols must be described in words in the caption ("open red triangles",
   per npj). Error bars require a caption sentence stating what they represent
   (sd, se, range) and n. Every figure is cited in the text in order. Captions
   carry no implementation names — no script filenames, package names, or file
   formats; software provenance belongs in Methods (the author's standing
   convention).
9. **No annotation clutter.** No per-bar value callouts, no marker labels
   above bars, no background guide lines. Plain marks, axis labels, legend;
   everything explanatory lives in the caption (the author's standing
   convention). In-figure annotations are allowed only when they mark physical
   features the axis cannot express — and then the caption must introduce
   them.
10. **Data integrity.** No visual effect that alters perceived data: no 3-D
    bars, no shading gradients on data, no decorative color, white background,
    no excessive framing boxes.
11. **Export.** Vector PDF for line/scatter plots (fonts embedded:
    `pdf.fonttype: 42`); PNG at ≥500 dpi only when raster is required
    (heatmaps, large scatter); one figure per file, named after the manuscript
    figure number. Never post-edit exported files by hand — change the script
    and regenerate.
12. **Provenance.** Every computed figure is produced by a versioned script
    reading the pinned evidence edition (the same rule as manuscript numbers).
    No interactive-window exports.

### 来源安全：示意图与外部图（真实来源，不虚构）

- 静态示意图（schematics）与外部获得的图必须记录**真实来源**：由哪个工具/
  哪个版本绘制、或转载自哪篇文献/哪个 URL、许可条件；记录进该论文的图形
  说明（Methods 或 caption，按期刊惯例与逐篇 overlay），caption/Metadata 中
  不写不真实的"脚本生成"来源。
- 不得为满足本 reference 而编造来源、把外部图当作本仓库脚本产物、或把手工
  图说成脚本生成。来源不明就如实标注来源不明并交作者处理。
- **AI 生成图像没有 policy gate**：是否允许 AI 生成图形/图形摘要是 post-
  pilot 决定（PRD 决定 6，Out of Scope）。在作者明确决定前，不引入 AI 生成
  图形，也不为此设计强制门禁。

## Base profile

Save as `paper.mplstyle` in the paper repo and apply with
`plt.style.use('paper')`; per-venue, override only the figure width. (Where a
per-paper overlay defines its own style, the overlay wins per the 约定层级
section.)

```ini
figure.dpi        : 150
savefig.dpi       : 600
savefig.bbox      : tight
savefig.facecolor : white
pdf.fonttype      : 42
font.family       : sans-serif
font.sans-serif   : DejaVu Sans, Nimbus Sans, Helvetica, Arial
mathtext.fontset  : dejavusans
font.size         : 8
axes.labelsize    : 8
axes.titlesize    : 8
xtick.labelsize   : 7
ytick.labelsize   : 7
legend.fontsize   : 7
legend.frameon    : False
lines.linewidth   : 1.2
lines.markersize  : 4
axes.linewidth    : 0.6
xtick.major.width : 0.6
ytick.major.width : 0.6
grid.linewidth    : 0.4
grid.alpha        : 0.3
axes.prop_cycle   : cycler('color', ['0072B2', 'D55E00', '009E73', 'CC79A7', 'E69F00', '56B4E9', '000000'])
```

(The cycle is Okabe–Ito minus gray; grayscale separation comes from rule 4's
linestyle/marker pairing.)

Single-column creation sizes: `figsize=(3.35, 2.1)` (86 mm), `figsize=(3.5,
2.2)` (90 mm), `figsize=(3.5, 2.4)` (89 mm npj). Double-column: `(6.7, …)`,
`(7.5, …)`, `(7.2, …)`. Height is free; keep panels square-ish only when
comparing on equal footing.

## Verification pass（试点图形 gate = 内置清单 + 最终视觉检查）

Run after producing or changing any figure, before it enters the manuscript.
Mechanical, fail-and-fix — do not waive a failed check for convenience. When
a check conflicts with the paper's overlay, the overlay wins and the check is
evaluated against the overlay's convention; escalate to the author only when
the overlay itself looks wrong or a rule conflicts with the science — never
silently deviate.

1. **Titles absent**: `assert not fig._suptitle` and `all(not
   ax.get_title() for ax in fig.axes)` (or equivalent inspection).
2. **Print-size type**: figure was created at the venue column width, so the
   smallest rendered text ≥7 pt; check any `fontsize=` overrides.
3. **Panel labels**: composite figures have bold lowercase panel letters on
   every panel, top-left, consistent placement and format (`(a)` vs `a` per
   the manuscript's convention).
4. **Axes complete**: every axis has quantity+unit labels; value axis of any
   bar/histogram starts at a non-truncating baseline or the truncation is
   captioned.
5. **Color safety**: series distinguishable in grayscale (linestyle/marker
   differ); no red/green-only pairing; continuous maps from viridis/Crameri
   only.
6. **Line weight**: data lines ≥1.0; nothing meaningful below ~0.5 after
   scaling.
7. **Clipping**: no data points or labels clipped at axes edges or figure
   bounds; tight bbox used.
8. **Caption draft exists** and names each panel by letter, describes symbols
   in words, and explains error bars if present.
9. **Output**: line/scatter figures — vector PDF present, fonts embedded
   (`pdffonts` shows embedded subsets), filename matches the manuscript figure
   number. Raster-required figures (heatmaps, large scatter) — PNG at ≥500 dpi
   present, matching the figure number; no vector/raster duplication of the
   same figure.
10. **Provenance**: computed figures regenerated cleanly from their script;
    schematics/external figures carry their true recorded source (来源安全
    section); `git status` shows no hand-modified exported file.
11. **Render and inspect**: rasterize the exported PDF (`pdftoppm -png -r
    150`) — or, for permitted raster-only figures, inspect the exported PNG
    directly — and look at the result at approximately final print size — the
    checks above catch named defects; only inspection catches layout ugliness
    (overlapping labels, dead space, unbalanced panels). This final visual
    inspection is part of the pilot gate, not an optional extra.

### figure-gate：仅可选对照

If `figure-gate` (PyPI) happens to be installed, you MAY run it as an
**optional comparison** and report interesting agreements/disagreements to the
author. Its FAIL/WARN items are **never** blocking by themselves, this skill
does not adopt its JSON/severity protocol, and **no duplicate JSON checker is
built or shipped**. Not installed → say so and move on; installing it just to
gate figures is out of scope. Any promotion of figure-gate to a mandatory gate
is a post-pilot decision requiring owner approval.

### 评审边界：不是语言缺陷

常规图注标题（"Fig. 1"、"(a)"）、数学简写（$J_1$、$E_F$）与坐标/面板标签
**不是破碎语言**，评审与机械检查不得把它们当作语言失败上报（ADR-006）。本
reference 不产生任何永久语言规则，也不设规则库自动增长路径。

## Venue deltas

| Venue | Width (mm) | Body type | Notes |
|---|---|---|---|
| PRB / REVTeX | 86 / 172 | 8 pt | Figures near first reference; `\label` inside `\caption`; `figure*` for double column |
| CPC / elsarticle | 90 / 140 / 190 | 8 pt (≥7 finished) | 300/500/1000 dpi for halftone/combination/line art; vector preferred |
| npj Comput. Mater. | 89 / 183 | 8 pt | No copyediting/redrawing in production; same typeface+size across all figures; no rainbow, no red/green |

Per-paper overrides (branch flow, data files, symmetry ordering, panel
conventions) live in the paper's overlay and win over this table's "Notes"
where they conflict.

## Where this sits among existing skills

- **Author's per-paper convention skills** (`tmtmfeo3-paper-figures`,
  `tmfeo3/spinphon-manuscript-conventions` in the managed library) and per-
  paper overlays recorded in the workbench: authoritative for their papers;
  this reference defers to them (see 约定层级).
- **Public figure skills** (checked 2026-10-16 via skills.sh):
  `k-dense-ai/scientific-agent-skills/matplotlib` (2.1K installs) is generic
  matplotlib API guidance; `nature-figure` (yuan1z0825/nature-skills, 17.9K
  installs) is a broad Nature-flavored figure-making router including AI
  graphical-abstract policy workflows. Neither encodes the target venues'
  print specs (column widths, type floors, REVTeX/npj handling) or this
  author's conventions. Partial inspection only — skills.sh truncates SKILL.md
  content.
- **figure-gate** ([PyPI](https://pypi.org/project/figure-gate/) /
  [repo](https://github.com/narenp12/figure-gate), MIT, ships as a Claude Code
  plugin): the verification layer, not a style layer — it checks a built
  figure (21 named defects) but "does not draw, restyle, or judge whether a
  figure is good". Treated here strictly as an optional comparison (see
  above), not as a gate.
