# 阶段说明：严格构建门与清洁源码导出（Story 014 FR-D3 / Story 009 FR-D5 / STD-005）

配套确定性 helper：`tools/evidence_export.py`（导出）、`tools/build_gate.py`（构建门）。
开关（`\evidencemarginfalse`）只控制 PDF 显示；**提交用的真正剥离靠本导出**。

## 严格构建门（Story 014, FR-D3）

干净构建把提交 SHA 与证据版本（edition）ID 嵌入 PDF，文献在起草前冻结到带日期
版本，引用错误或固定输入哈希失配时构建直接失败（Manubot 默认容忍引用是点名反模式）。

```sh
# 起草前：把参考文献冻结为带日期版本（快照字节 + sha256 + 日期 → bib-freeze.yaml）
python tools/build_gate.py freeze refs.bib --record bib-freeze.yaml

# 干净构建：前置核验 + 宏嵌入 + 真实 pdflatex/bibtex 编译
python tools/build_gate.py build --tex main.tex --manifest evidence-manifest.yaml \
    --bib refs.bib --freeze-record bib-freeze.yaml --commit <40-hex-SHA> [--output-dir build]
```

构建前置检查复用 Story 005/006 的 `tools/evidence_manifest.py`：清单中每个 pinned
输入按记录的 locator 取回实际字节并核对 sha256——哈希不是取回方式，也不用 HEAD
代替未提交内容。失配即失败，点名 artifact 与期望/实际哈希；缺文件、locator 不可
解析同样失败。

提交 SHA 与 edition ID 经生成的宏文件 `build-info.tex`（`templates/` 约定同 008，
FR-D1：宏文件而非内联字符串）进入正文（`\buildcommit`、`\buildedition`），随 PDF
渲染，可从 pdftotext 取回。宏文件由工具生成，不手改。

**文献冻结语义**：`freeze` 把 bib 字节钉为带日期版本；其后的构建核对当前 bib 的
sha256。冻结后被修改的 bib **绝不静默采用**——默认失败并显式报告差异（冻结日期、
冻结/当前哈希）；`--use-frozen` 显式选择用冻结版本构建，同样打印差异报告。改用新
文献版本的唯一路径是重新 `freeze` 一个新的带日期版本。

**失败语义（不产出被声称为成功的 PDF）**：pdflatex/bibtex 非零退出、日志中的
`Citation '…' undefined` / 未定义引用、bibtex 缺条目——构建失败并点名引用键；
任何失败路径都会删除输出目录内全部 PDF。消费者可见错误（退出码 2，stderr 一行）。
绿灯还需两点实际核验：渲染 PDF（pdftotext）确实含有 commit SHA 与 edition ID
（手稿必须 `\input{build-info.tex}` 并使用 `\buildcommit`/`\buildedition`，否则
不亮绿灯）；首轮 `.aux` 的 `\bibdata` 请求的正是冻结的 `--bib` 文件——bibtex 的
BIBINPUTS 只指向构建目录里的冻结副本，请求其他 bib 即失败，冻结外无解析路径。

**边界（绿灯 ≠ 正确性）**：绿灯构建只证明 plumbing——不证明科学正确性、不证明
claim–evidence 一致、不证明语言/图形质量；构建门从不运行科学计算；claim–evidence
map（FR-A3）在构建门之上。复现检查（FR-D4 清洁环境重建）属 Story 015，不在本门
范围；本门不自动采用任何新材料、不重算、不抓取外部引用。

## 使用

```sh
# 生成干净副本（工作稿永不修改）；默认在工作副本上独立 pdflatex 编译一次（--no-compile 跳过）
python tools/evidence_export.py export main.tex --output-dir clean-export \
    [--copy refs.bib --copy figures/fig1.pdf] [--strip-metadata evidence-metadata.tex] \
    [--private-marker /private/path/substring]...

# 对导出树做泄漏检查（消费者可见 pass/fail，失败附 文件:行号）
python tools/evidence_export.py leak-check clean-export [--private-marker STRING]...
```

导出复制入口 .tex 及其 `\input`/`\include` 引用的本地文件（限制在稿件目录内解析，
越界拒绝），加上 `--copy` 指定的附加文件（.bib、图等）。

## 剥离边界（只认专用证据元数据模式，不做通用 TeX 变换）

剥离且仅剥离：

1. 每个 `\evidenceblock{ID}` 调用（整行只有该调用时保留换行）；
2. 生成的 `evidence-metadata.tex` 文件本身（不进入导出；`--copy` 指到它即拒绝）；
3. 引入它的 `\input`/`\include` 命令——专用于 metadata 的引入与其他 TeX 同行时
   只删命令本身，行的其余部分原样保留。

文件以**二进制读写**处理：不发生任何换行符规范化，CRLF/CR/LF 手稿逐字节保留。
`\input`/`\include` 解析到稿件目录之外且确实存在时，loudly 拒绝（不静默省略）。

公开内容逐字节保留：正文、公开 citation、数据/代码可用性语句、图表、`--copy` 文件。
`verbatim` 类环境中出现 `\evidenceblock` 不做改写—— loudly 失败并指出位置
（证据块是草稿边注宏，不是 verbatim 内容）。

## 泄漏检查

扫描导出树（跳过二进制图片/PDF）中的固定标记：`evidenceblock`、
`evidence-metadata`、`evidence-manifest`、`evidence-snapshots`，以及调用方经
`--private-marker`（可重复）显式传入的私有路径子串——调用方负责把自己的私有根
传入；命中任一即失败（退出码 2），逐条给出 `文件:行号` 与命中模式；无残留则
pass。`export` 自身在编译成功后运行同一检查（含同样的 `--private-marker`），
泄漏即整体失败（导出目录保留供检查）。

## 不变量

- 构建门（014）：输出目录已存在即拒绝（每次构建都是新鲜构建树）；pinned 输入按 locator 取回的字节核验，失败不编译；宏文件只由工具生成。
- 工作稿字节不变（导出只读工作副本、只写新目录；`--output-dir` 已存在即拒绝）。
- 导出源在其自身目录独立编译成功。
- 无证据构造的普通稿件导出与输入正文等价，泄漏检查通过。
