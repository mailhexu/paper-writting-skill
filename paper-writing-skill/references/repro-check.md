# 阶段说明：一次性提交前清洁环境复现检查与包元数据记录（Story 015，FR-D4 / FR-E1）

配套确定性 helper：`tools/repro_check.py`；固定输入取回复用 `tools/evidence_manifest.py`
（Story 005/006），忽略表比对在 `repro_check.py` 内实现。本检查**仅提交包阶段执行一次**，
不随每轮草稿迭代运行（Epic 004 Out of Scope）。

## 清洁环境定义

全新目录（`<record 目录>/clean`，已存在即拒绝——每次检查都是新鲜重建树）：除按记录
locator 取回并核验 sha256 的 pinned 输入外，**不携带任何工作树状态**。步骤进程使用受限
环境（仅 PATH，可另加计划显式声明的 `source_date_epoch`）；工作目录即清洁目录。环境变量
不继承、工作区文件不可见——ambient 输入未被 pin 时步骤在清洁目录内自然失败，这正是
检查要暴露的缺口，而不是要绕过的障碍。

## 计划 schema（pws.repro-plan/1）

```yaml
schema: pws.repro-plan/1
edition: "2026-10-21-submission1"
source_date_epoch: 1767225600        # 可选；仅显式声明的值会进入步骤环境
inputs:                              # 每个 pinned 输入 = 清单 artifact id + 清洁目录内目标路径
  - artifact: result-data
    path: data/result.csv
  - artifact: macro-script
    path: make_macros.py
  - artifact: figure-script
    path: make_fig1.py
  - artifact: main-tex
    path: main.tex
steps:                               # 三类各至少一步：重提宏 + 重绘图 + 重编译
  - {id: macros, kind: macro, command: ["python", "make_macros.py"]}
  - {id: fig1,   kind: plot,  command: ["python", "make_fig1.py"]}
  - {id: pass1,  kind: tex,   command: ["pdflatex", "-interaction=nonstopmode", "main.tex"]}
  - {id: pass2,  kind: tex,   command: ["pdflatex", "-interaction=nonstopmode", "main.tex"]}
intermediates:                       # 声明的编译中间产物；清洁树不允许出现任何未声明文件
  - macros.tex
  - main.aux
  - main.log
declared_outputs:                    # 声明输出集（PDF + 关键图）+ 显式忽略表
  - path: main.pdf
    reference: references/main.pdf          # 参照副本（提交包构建的产物）
    reference_sha256: "<忽略表归一化后的 sha256>"
    ignore:                                  # 逐条命名的非确定性字节，绝不整体忽略 PDF 差异
      - 'CreationDate \(D:[^)]*\)'
      - 'ModDate \(D:[^)]*\)'
      - '(?s)/ID \[<[0-9A-Fa-f]*> ?<[0-9A-Fa-f]*>\]'
  - path: fig1.pdf
    reference: references/fig1.pdf
    reference_sha256: "<…>"
    ignore: ['CreationDate \(D:[^)]*\)']
package_metadata:                    # FR-E1：同一记录内逐 artifact 写入许可与数据集 ID
  artifacts:
    - {artifact: result-data, license: "CC BY 4.0", dataset_id: "10.5281/zenodo.xxxxxxx"}
    - {artifact: macro-script, license: "MIT", dataset_id: "not-applicable-private"}
    - {artifact: figure-script, license: "MIT", dataset_id: "not-applicable-private"}
    - {artifact: main-tex, license: "unknown", dataset_id: "unknown"}
```

校验规则：schema/edition/steps/inputs/declared_outputs/intermediates/package_metadata 各字段缺失即失败；步骤 `kind` 只能是 `macro`/`plot`/`tex` 且**三类各至少一步**，且顺序必须为宏提取/绘图在前、TeX 编译在后（编译必须消费重提取的宏与重绘的图）；必须存在 tex 步骤编译 pinned 手稿源，且其 stem 对应一个声明的 `.pdf` 输出。`tex` 步骤只允许裸名 `pdflatex`/`bibtex` 加**有界白名单旗标**（nonstopmode/batchmode/errorstopmode/scrollmode、halt-on-error、file-line-error）——output 重定向、shell-escape、引擎/格式切换一律拒绝；`.tex`/`.bib` 参数必须是已声明的 pinned input；`macro`/`plot` 步骤只允许**裸名**解释器运行已声明的 pinned 脚本路径（拒绝 `-c` 等选项与带路径的解释器）。输入/输出/intermediates/`reference` 路径必须相对、不含 `..`、归一化后互不冲突；计划 `edition` 必须与清单 `edition` 一致。每个 pinned input 必须有 package metadata 条目，`license`/`dataset_id` 非空且非占位（`todo`/`tbd`/`<…>` 等），**真实未知时如实写 `unknown`**，不虚构合规信息。

`intermediates`（可选）声明编译中间产物（`main.aux`、`main.log` 等）；重建结束后对清洁树做足迹核验：出现的每个文件必须是声明的 input、declared output 或 declared intermediate 的**常规文件**——未声明文件与符号链接（如指向工作树参照副本的软链）一律失败。TeX 步骤的每个非旗标操作数（含无后缀/绝对路径）都必须是已声明的 pinned input。忽略表逐条正则、长度保持掩码；能匹配任意长度跨度的模式在校验时拒绝，按**匹配字节覆盖率**核验——覆盖超过输出一半（无论模式形状）的比对失败，文档中原生的 `~` 字节不计入覆盖——**没有"忽略全部 PDF 差异"的开关**。

## 步骤与比对

1. **固定输入核验**（复用 Story 005/006）：每个输入按记录 locator 取回实际字节并核对
   sha256——哈希不是取回方式，缺失或失配都不以当前文件顶替（ADR-003）；相对 locator 相对
   **清单文件所在目录**解析，计划 edition 必须与清单 edition 一致。
2. **参照副本核验**：每个声明输出的 reference 副本按忽略表归一化后与记录的
   `reference_sha256` 比对，基线不完整即失败。
3. **记录命令**：按序在清洁目录执行；非零退出/超时即失败并点名步骤。复现 ≠ 重跑科学——
   宏提取、绘图（只运行 pinned 脚本于 pinned 数据）、TeX 编译是 FR-D1 允许的派生操作；
   任何需要重算才能出图/出数的情形一律失败并开 FR-K3 交接，不静默降级。
4. **声明输出比对**：忽略表为**逐条正则、长度保持掩码**（掩码后字节偏移不变，PDF 可比）；
   归一化 sha256 不一致即失败，点名文件与期望/实际哈希。已知 TeX 元数据噪声（CreationDate、
   ModDate、/ID）必须显式逐条列入忽略表——**没有"忽略全部 PDF 差异"的开关**。
5. **清洁树足迹核验**：重建结束后，清洁树内的每个文件必须是声明的 input、declared output
   或 declared intermediate；出现任何未声明文件即失败并点名（构建中间产物必须在计划中登记，
   不被静默容忍）。
6. **包元数据记录**（FR-E1）：package_metadata 原样写入检查记录（`pws.repro-record/1` JSON），
   供 Story 016 可用性声明消费；工具不校验其科学真实性，只拒绝占位符与缺失。

## 失败语义（FR-K3）

pinned 输入缺失（含 artifact 未登记于清单、locator 不可取回）或哈希失配：检查失败，点名
artifact 与期望/实际哈希，在 record 目录产出
`repro-frk3-draft-<artifact>.md` 交接草稿（纯文本请求，owner 批准后才执行；无审批自动化）；
**绝不重跑科学计算、绝不用当前文件字节顶替缺失旧版本、绝不伪造缺失数据使管线"完整"**，
失配输入不被声明为"已复现"。全部失败：退出码 2、stderr 单行可读错误、检查记录仍写盘
（`result: fail` 与失败细节）。

## 不变量

- 只读 pinned 输入（按 locator），只写清洁目录内的声明产物与 record 目录内的检查记录/交接草稿；无仓库级扫描，无其他副作用。
- 忽略表只作用于声明输出、只掩码显式列出的模式；比对基线（reference + 归一化哈希）先核验后使用。
- 复现 ≠ 正确性：绿灯只证明提交包可从固定输入按记录命令重建，不证明科学正确性、不证明
  claim–evidence 一致（FR-A3 在其上）、不证明 venue 合规（Story 016）。
