# 阶段说明：提交准备与核验（Story 016）

配套工具：`tools/submission.py`；venue 参数：`configs/venue-profiles.json`。
本阶段只准备与核验 submission-prepared 包，不执行投稿，不替作者选择 venue、确认科学内容或改变 bibliography。

## 不变量与状态

- **包完整 ≠ 可投稿；实际投稿由作者执行并留痕。** 所有 JSON 报告都带有该边界声明；通过只代表本工具所检查项目通过，不代表编辑部合规、科学结论成立或作者已批准投稿。
- Venue 来源及其 `checked_on` 日期随每项检查输出。工具不联网更新政策；运行前作者必须逐篇核对现行要求，并在输入中明确记录核对日期与 `current_policy_rechecked: true`。配置中的文章类型/数量限制仅对有明确依据的字段做机械判断；未找到上限不等于已证明没有上限。
- 不得用通用默认规则替代未知 venue。配置中 CPC 可访问的文章类型细节来自历史指南，**不是已验证的现行投稿约定**；用前必须按当前指南复核。
- PDF 可以作语义/尺寸抽取检查；PNG 的文字、字体与调色板检查均为 `manual-required`。矢量/抽取规则不代替最终打印尺寸目检；Story 018/019 的试点目检仍须完成。
- 任何报告中的 `pass` 仅指被明确检查的机械/作者输入规则。来源元数据一致不代表 bibliography entry 真实、文献支持论断，或论断本身成立。

## 命令

从仓库根目录运行：

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

每条命令在 stdout 输出 JSON `pws.submission-report/1`。成功退出码为 `0`；检查失败、未知 venue 或仍需人工检查的退出码为 `1`；参数用法错误由 argparse 报告。输入错误也产生带边界声明的 JSON fail 报告。该工具只读手稿和 `.bib`，不提交、重写或建议自动应用 bibliography 修改。

## Venue checklist 输入

`venue-check` 的 `--submission` 接受 JSON 对象。字段名和枚举由参数文件中所列规则决定；检查结果逐项给 `pass`/`fail`/`manual-required`、详细理由及来源 URL、核对日期与 caveat。必需字段缺失、类型/取值非法或无法判定的文章类型均失败。当前参数档涵盖：

- `prb`：`article_type` (`regular_article` 或 `letter`)、`word_count`、`body_stands_alone_without_supplement`、`current_policy_checked_on`、`current_policy_rechecked`。Letter 采用配置的 4500 词上限；regular article 只记录篇幅，不从“未找到总上限”推断不存在其他要求。`ai_use` 为 `none`/`basic`/`substantive`；配置要求对 substantive use 记录 `ai_disclosure: true`。
- `cpc`：`article_type` (`computer_programs_in_physics` 或 `computational_physics`)、`current_policy_checked_on`、`current_policy_rechecked` 和必填 `ai_use` (`none`/`manuscript_preparation`/`research_process`)；两类生成式 AI 使用还需 `ai_disclosure: true`。Computer Programs in Physics 类型还需 `program_summary`。文章类型与摘要规则依据历史指南，必须在目标投稿日重新核验。
- `npj`：非负整数 `word_count`、非空字符串 `data_statement`、`central_custom_code`、`supplementary_methods`、`figure_legend_words` 和政策复核字段；当 `central_custom_code: true` 时需非空 `code_statement`，不得将 Methods 移至 Supplementary Methods，图注正文不超过配置的 350 词。`ai_use` 可为 `none`/`basic`/`manuscript_preparation`/`research_process`/`substantive`；非 `none` 时需 `ai_disclosure_location`。

AI 分类由各 venue profile 明确映射到“披露”或“无需披露”；未映射的 venue/category 组合失败，不把未知类别默认为豁免。AI 范围以作者对实际使用的记录为准，不能猜测“无使用”。细则与引用来源以 `venue-profiles.json` 为准；不应把本节解释复制成第二份可编辑政策表。

## 可用性声明（FR-D4 package metadata）

`availability` 消费 Story 015 的 `pws.repro-record/1` JSON 与相应 evidence manifest。记录必须 `result: pass`、edition 与清单一致，且至少有一个 pinned input。每个输入须为 `verified`，并将记录的 `sha256`、locator 与 supplied manifest 对应 artifact 的 hash/定位核对一致：记录 locator 按记录中绝对的原始 `manifest` 路径目录解析，supplied manifest locator 按该清单目录解析；若记录没有可用的绝对原始 manifest 路径，不能证明相对 locator 的基址，必须报告 gap。字段报告给出记录 JSON Pointer、该次验证的 hash/locator 和清单 locator。每个输入 artifact 还必须在 `package_metadata.artifacts` 中有非空、非占位的 `license` 和 `dataset_id`。缺字段、`unknown`、占位符、清单缺项、未验证输入、hash/locator 不一致都会成为逐项 `gaps`，不生成占位文本。结果是对已记录元数据的溯源陈述，不证明 URL 可访问、许可判断正确或数据/代码已公开。

## AI 披露

`disclosure` 输入 JSON 必须显式给 `use`。各 profile 显式列出无需披露类别与必须披露类别；仅明确列出的豁免类别返回无文本结果，未映射类别失败，不得静默豁免。需要披露时，作者还需填写 `tools`（`[{"name":"...","model":"..."}]`）、`purpose`、`human_review`、`responsibility_statement` 与 `placement`；工具把这些事实代入 venue 对应模板。缺事实时失败，不代作者杜撰。未知 venue 明确返回核对现行政策标记，不套用任何模板。

## Cover letter

命令要求传入 `pws.paper-plan/1` JSON adapter，至少包含下列字段；格式最小形状如下：

```json
{
  "schema": "pws.paper-plan/1",
  "status": "approved",
  "source": "<author-approved Paper Plan record locator>",
  "contributions": ["<approved contribution item>"]
}
```

`source` 必须指向作者批准的权威 Paper Plan 记录，`contributions` 必须逐项原样转录其获批贡献。工具拒绝缺少计划、schema 不匹配、状态非 `approved`、来源或贡献缺失；生成的草稿按贡献逐条列项，并返回 adapter 路径及来源定位。**该 JSON 是传递已批准记录内容的消费 adapter，不是 Kosmic 记录类型或审批机制；工具只检查 adapter 字段，不验证其来源记录、审批人或批准真实性。不得把手工编造/未经批准的 adapter 当成已批准计划。** 当前技能材料阶段没有已交付的 machine-readable Paper Plan exporter；作者/集成人须先从真实批准记录构造该 adapter。这个来源真实性边界必须保留，绝不宣称工具认证了作者审批。

## 图文件检查

`figure-check` 和 `venue-check --figure-manifest` 接受相对路径 JSON manifest，示例：

```json
{"figures":[{"path":"figures/fig1.pdf","column":"single","panels":["a"],"panel_regions":{"a":[0,0,1,1]}}]}
```

路径不得为绝对路径、含 `..` 或解析到 manifest 目录外。每个文件需声明 `column`，并显式列出预期 `panels`（没有 panel 时传 `[]`）；可选 `panel_style` 为 `parenthesized`（默认，`(a)`）或 `bare`。为自动核对 panel 相对位置，`panel_regions` 可按 panel 字母给归一化 `[x0,y0,x1,y1]` 矩形，坐标原点为页面左上；标签须落在相应面板内部的左上象限。缺少某 panel 的 bounds 时，位置报告 `manual-required`，不以整页高度判定下排标签。CPC 含栅格内容时需 `artwork_type` (`halftone`/`combination`/`line_art`) 以选择分辨率门槛。

- 仅检查配置允许格式的单页 PDF/PNG；核对页面物理宽度、抽取文字中的标题候选、panel 是否存在/粗体、sans-serif 家族、字号和配置色板。没有标题候选并不能证明没有左对齐、短标题或下方面板标题：这时 `embedded-title` 为 `manual-required`，候选标题则失败。Panel 位置按已声明的面板 bounds 检查；bounds 缺失时要求人工检查。PDF 字号仅对可抽取文字做筛查：明确识别的 superscript 低于 6 pt 或无 superscript 标志的文字低于 6 pt 时 `fail`；无 superscript 标志的 6–7 pt 跨度可能是 subscript，因此只能 `manual-required`，`flags` 不用于推断 subscript 语义；缺少配置的 8 pt body text 也会 `fail`。其余未检测到缺陷的字号检查仍为 `manual-required`，因为不能证明 PDF 文本抽取完整或视觉字号合适。PNG 文本/字号始终需人工检查。
- PDF 字体嵌入由 `pdffonts` 核对；矢量/文本中出现 categorical palette 之外的非中性色彩时，色彩检查为 `manual-required` 而非失败，以允许 viridis/Crameri 连续色图同时避免将未知颜色误判为安全。PDF 的 raster DPI 与人工色彩检查使用 PyMuPDF `get_image_info(xrefs=True)` 枚举显示图像，也包含 inline images；DPI 门槛允许 0.01 dpi 的浮点/分辨率元数据舍入误差。
- PNG 检查 PNG 实际格式、嵌入 DPI 与计算出的物理宽度；文本、字体、panel、打印字号和色彩都标为 `manual-required`，总状态不会错误地报告 `pass`。
- 当前参数档的单栏宽度为 PRB 86 mm、CPC 90 mm、npj 89 mm；CPC 另支持 140/190 mm，npj 183 mm，PRB 172 mm。字体/色板/分辨率配置和出处见 venue profiles 与 `figure-style.md`。不可将机械结果解释为已经完成打印尺寸视觉审查。

最终尺寸目检还须检查坐标轴标签等内容是否被页面边缘裁切；抽取到完整文字或机械项没有失败都不能替代这一步。

可安装 PDF/PNG 检查依赖：

```sh
python -m pip install -r paper-writing-skill/requirements-submission.txt
```

PDF 检查还要求系统 PATH 有 Poppler `pdffonts`；工具不会自动安装它。不能核验字体时该项失败。

## 引文 key 与外部 bibcheck 边界

`citation-check` 解析常用 TeX citation command（含小写 `\parencite`/`\textcite` 与 `\cites{...}{...}` 等 multicite 的每个参数组）并比对 `.bib` entry key，点出正文引用但 bibliography 不存在的 key；注释中的引用不计入。该本地检查不查询 DOI/arXiv、不判断条目元数据、不检查引文是否支持正文论点、不写入两份输入；metadata agreement does not establish scientific support。

`bibliography-check` 通过受支持的 `bibcheck.bibcheck.verify_bib_file` Python 接口核验元数据，不复制 DOI/arXiv 查询或比较逻辑。运行环境须安装包含该只读接口的已交付 BibCheck 包；缺包或旧版缺少该接口时返回显式依赖错误，不退回旧的会写文件的校正命令，也不把本地 key 对应检查当成元数据核验。本工具不自动安装依赖或硬编码开发机源码路径。

| 参数 | 含义 |
|------|------|
| `--bib` | 必填；输入 `.bib` 文件路径，不是 BibTeX 文本。 |
| `--key` | 可选；精确、区分大小写的 citation key。省略时核验全部 entry，按输入顺序返回；指定时只查询和报告该 entry。整文件语法仍先检查，空/不存在/歧义 key 在查询前失败。 |

JSON 报告沿用 `pws.submission-report/1`；`verification` 保留 BibCheck 原始结构化报告，包括每条 entry 的状态、查询来源、原始 `{field, original, proposed}` 差异、不可用字段、原因和作者审批 notice。比较采用 BibCheck 默认配置；本工具不另造配置或报告协议。

| BibCheck `verification.outcome` | 本工具 `status` / 退出码 |
|------------------------------|-------------------------|
| `clean` | `pass` / 0 |
| `differences` | `fail` / 1，保留建议，不应用修改 |
| `unverifiable` | `fail` / 1，保留 `missing_identifier`、`no_match`、`query_failure` 及其他有效结果 |
| `error` | `fail` / 1，保留 input/selection 等显式错误 |

Python 集成人可在工具模块目录位于 import path 时调用 `submission.bibliography_check(bib_value, *, key=None)`；返回同一外层字典，不打印、不写文件。需要直接使用 BibCheck 的比较配置时，使用其自身受支持的 `verify_bib_file` 接口，而不是修改或绕过本检查。

检查不改写作者 `.bib`、相邻 corrected/order-only 文件或持久缓存。缺标识符、无可靠匹配与查询失败都不是通过；混合报告中存在已知差异也不会掩盖未能核验的 entry。所有建议修改都须作者确认，元数据一致不代表文献支持正文科学论断。
