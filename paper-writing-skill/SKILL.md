---
name: paper-writing-skill
description: >
  从已记录的物理与科学软件研究中准备期刊论文：从论文定位逐步细化主线、
  章节与图形、段落和面向读者的正文；按当前任务加载材料/计划、起草、证据、
  编辑评审、图形或提交说明，并承接已确认的决定。
  科学事实与证据一律来自既有研究记录，本技能不做科学计算、不改研究数据。
---

# 论文写作技能 — 入口路由

## 定位

本技能组织"从研究记录到期刊论文"的写作流程：按阶段给出说明与检查清单，
不镜像研究知识、不引入新的科学计算引擎、不替换论文已有构建系统
（LaTeX/图表构建命令继续负责宏、图、PDF）。知识正文始终留在其原始记录处
（Kosmic notes/artifacts）；本技能的 reference 只说明如何使用它们，不复制内容。

## 作者权限边界（任何阶段都适用）

1. **科学内容只由作者决定。** 改变科学意思、删除/合并/降级内容、替换关键
   证据：先给有理由的建议，作者逐项确认后才能执行；代理不联动改稿。
2. **不自动运行科学计算。** 缺证据或结果存疑时报告问题并提出研究请求
   （Research Handoff），不重算、不补数据、不为叙事择优。
3. **不虚构。** 不制造引用、数字、图或"待补"的占位内容；未实现的阶段如实
   说明尚未交付，不假装存在对应说明。
4. **知识单一来源。** 材料条目只加使用意图与采用/候选决定；不改写、不复制
   原始笔记，避免出现第二份知识正文。
5. **不安装、不全局发布。** 本技能包内的文件即全部能力；安装/发布另行审批。

## 阶段选择

先读该论文已有的 Plan、工作台与当前决定，定位第一个未解决且获授权的任务，
再**只加载当前所需**的 reference；已有进展不从头问起。完成后若获准继续，
再按需加载下一项，不预载整个流程。

| 阶段 | Reference | 状态 |
|------|-----------|------|
| 材料/计划 | [references/material-plan.md](references/material-plan.md) | 可用 |
| 起草（主线、章节/图形设计、段落、正文） | [references/drafting.md](references/drafting.md) | 可用：自上而下的规划顺序与确认出口、living skeleton、分节起草、FR-B4 语言完整性、FR-B5 整稿语言 pass 与 Vale 晋升门槛 |
| 证据检查（清单核验、取回验证） | [references/evidence-manifest.md](references/evidence-manifest.md) | 可用：manifest schema 校验与三种 locator 取回（Story 005）、采用时字节核验与快照（Story 006 `adopt`）、新鲜度检查与分诊报告（Story 007 `check`），入口均为 `tools/evidence_manifest.py`；TeX 投影见下行（Story 008）；清洁导出属 Story 009 |
| 起草证据边注（TeX 投影） | [references/evidence-projection.md](references/evidence-projection.md) | 可用（生成 `evidence-metadata.tex` 投影与 `\evidenceblock`/`\evidencemarginfalse` 开关，`tools/evidence_projection.py`） |
| 编辑评审（科学/编辑清单、prune、图形 gate） | [references/editorial-review.md](references/editorial-review.md) | 可用（类型化 finding 格式、科学/编辑独立清单、prune proposal 与拒绝留档、图形评审试点 gate，Story 012）。注意：结构修订后的整稿语言 pass（FR-B5）属起草阶段，由 [references/drafting.md](references/drafting.md) 覆盖；本阶段按 finding 格式收录其结果 |
| 图形（构造与核验） | [references/figure-style.md](references/figure-style.md) | 可用（全局缺省；逐篇约定可覆盖，reference 内显式 defer） |
| 提交（构建门、清洁导出、复现检查与合规） | [references/clean-export.md](references/clean-export.md)、[references/repro-check.md](references/repro-check.md)、[references/submission.md](references/submission.md) | 工具可调用：`build_gate.py`、`evidence_export.py`、`repro_check.py`；`submission.py` 提供 venue、可用性声明、AI 披露、cover letter、图文件、引文 key 与 BibCheck 整份/单 key 只读元数据检查。必要图形目检和实际投稿仍由作者执行 |

未实现阶段的处理：向用户如实说明该阶段能力尚未交付、需要先经相应 Story
批准实现；不要引用不存在的文件，不要用通用写作建议冒充本技能的该阶段。

仅当现有记录和用户要求仍不能判定下一步，且选择会改变工作时，才问一个具体
问题；不要为阶段标签或已有答案重复索取确认。

## 使用规则

- “next / 继续”承接已批准范围内下一项有依据的工作，不批准未见过的科学结论、
  新设计或计算。以当前进度、具体产出/变化和下一动作回应；实质未决处才提问。
- 产出与决定记录进项目既有的 Kosmic 记录/工作台文件，不在本技能包内堆积
  论文专属状态。
- 对作者既有约定（图形、风格、期刊习惯）保持缺省尊重（deference）；与其
  冲突时先提出，不擅自覆盖。
