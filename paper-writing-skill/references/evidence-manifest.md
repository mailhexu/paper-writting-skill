# 阶段说明：证据检查 — 清单最小 schema 与三种 locator 取回约定

**实现状态（Story 005）**：本文件声明 `evidence-manifest.yaml` 最小 schema、校验
规则与三种 locator（`git` / `snapshot` / `retained`）的取回约定与失败语义；配套
确定性 helper 为 `tools/evidence_manifest.py`。已实现：schema 校验与取回
（Story 005）、采用时核验与快照（Story 006 `adopt`）、新鲜度检查与分诊报告
（Story 007 `check`）。**不属于本阶段**（后续 Story）：TeX 投影（008）、
清洁导出（009）。

## 原则（ADR-003）

手稿旁保留一份小清单 `evidence-manifest.yaml`，只登记**论文真正采用的依据**；
候选与暂不采用的材料留在工作台，不复制进清单。每条 artifact 必须同时有内容
哈希与可取回定位。**哈希永远不是一种取回方式**：只有 `sha256` 没有 locator 的
条目在校验时被明确拒绝。清单不是知识正文的第二份维护副本。

清单覆盖的是**选定固定（采用）的依据**，不是全部工作材料：写作用的散装输入
（从其他计算复制的数值结果、手工整理的表格、手绘示意图、手工推导）不需要
先具备哈希或元数据才能被使用。材料被采用进清单时，对当时字节计算哈希即可；
哈希证明采用字节一致，不保证上游计算可复现或科学有效性。上游来源确实未知
时如实登记未知，不虚构运行元数据；并非所有材料都必须进入清单。

## 清单 schema（evidence-manifest/1）

```yaml
edition: "2026-10-18-draft1"        # 本证据版本的版本/内容标识

artifacts:                          # 仅登记采用的依据；id 唯一
  - id: "tb2j-run-42"              # 短标识符（ASCII 字母/数字/连字符）
    sha256: "<64 位小写十六进制>"    # 采用字节的精确内容哈希
    locator:                        # 必填 — 下列三种之一
      kind: git                     # "git" | "snapshot" | "retained"
      repo: "/绝对/或/相对路径"      # git：记录的仓库
      commit: "<40 位完整 SHA>"      # git：采用时的完整不可变 commit（不接受分支/HEAD 引用）
      path: "runs/42/out.dat"       # git：该 commit 时的仓库相对路径
  - id: "uncommitted-note"
    sha256: "<64 位小写十六进制>"
    locator:
      kind: snapshot
      path: "snapshots/uncommitted-note.dat"   # 随记录提交的快照文件
  - id: "retained-pack"
    sha256: "<64 位小写十六进制>"
    locator:
      kind: retained
      path: "/kosmic/retained/pack/..."        # 既有留存 artifact 的实际可读取位置

claims:
  - id: "claim-magnon-lifetimes"
    statement: "一句话陈述，与手稿表述一致。"
    artifacts: ["tb2j-run-42"]      # 必须指向存在的 artifact id
    intent: "该证据在本篇论文论证中的作用（论文使用意图）。"
    judgment: support               # "support" | "refute" | "insufficient"
    reason: "对按此措辞的陈述为何成立该判断的理由。"
```

校验规则（每处违规输出一条指明字段的可读错误，见下节 CLI）：

- `edition` 必须为非空字符串。
- 每条 artifact 需非空 `id`、64 位小写十六进制 `sha256`、以及 `locator`；
  artifact `id` 重复即拒绝；**只有哈希没有 locator** 的条目被拒绝，报错明示
  "哈希是内容指纹，不是取回方式"。
- `locator.kind` 必须恰为 `git` / `snapshot` / `retained` 之一；`git` 条目缺
  `repo`、`commit` 或 `path` 各自报错；`commit` 必须是 40 位完整 SHA（采用时
  记录的精确 commit，不得用分支或 HEAD 冒充）；`snapshot`/`retained` 需 `path`。
- 每条 claim 需非空 `id`、`statement`、`intent`、`reason`；`artifacts` 为非空
  列表且引用的 artifact id 必须存在；`judgment` 必须是 `support` / `refute` /
  `insufficient` 之一——反驳与证据不足的结果按其本样登记即为合法依据。
- 未知额外字段本 Story 不校验、不拒绝；schema 演进属后续已批准 Story。

## 取回约定与失败语义

`retrieve` 取回被固定的字节，并**先核验 `sha256` 再判定成功**；哈希失配是消费
者可见的失败，绝不把取回字节当作已采用版本输出。

- **git** — 用 `git cat-file` 在记录的仓库按记录的 commit 取历史字节；先确认该
  commit 对象在该仓库存在。**不读当前工作树文件**：路径在该 commit 不存在则
  取回失败并明确报告，不以当前文件字节顶替。仓库缺失、commit 不存在、路径
  缺失分别报错并指明 locator 字段。
- **snapshot** — 读取随记录提交的快照文件；路径不可读或哈希失配即失败并报告。
- **retained** — 读取留存存储的实际位置；失败语义相同。
- 相对路径解析：`repo` 与 `path` 若为相对路径，相对**清单文件所在目录**解析；
  绝对路径原样使用。仓库缺失（`repo` 不可用）与 commit 不存在分别报错并指明
  对应字段。

取不回字节的 pin 与任何缺失 artifact 同等失败（Research Handoff，FR-K3）：
本技能从不宣称内容取不回的版本"可复现"，也从不重算或顶替。

## CLI

```sh
python tools/evidence_manifest.py validate  evidence-manifest.yaml   # 退出码 0；逐条回显每个 artifact 的取回路径
python tools/evidence_manifest.py retrieve  evidence-manifest.yaml tb2j-run-42 --output out.dat
```

任何校验或取回失败：退出码 2，单行可读错误（指明字段）。依赖：Python 3.11+
与 PyYAML；`git` locator 需 PATH 上的 `git`。

## 采用（Story 006：`adopt`）

```sh
python tools/evidence_manifest.py adopt <current-file> \
    --repo REPO --commit <40 位完整 SHA> --git-path PATH \
    [--snapshot-dir evidence-snapshots] [--artifact-id ID] \
    [--output-manifest-fragment FILE]
```

`adopt` 只执行**已经由作者做出的采用决定**：它核验字节并产出与 Story 005 schema
兼容的 YAML fragment（`id` / `sha256` / `locator`），不做任何采用判断。

- **一致**：当前文件字节与记录 commit 的 git blob 完全一致 → 通过，登记 `git`
  locator（repo/commit/path），`sha256` 取自实际字节。
- **不一致**（典型：未提交/未推送内容）：**绝不以 HEAD 字节顶替**。先区分两种
  不一致：若当前字节与 HEAD 在同一路径的 blob **一致**（即差异已被提交），则
  明确失败（退出码 2），报错同时给出记录 commit 与 HEAD commit——两个版本都不
  得被静默登记，也不生成快照；只有当前字节**同时**不同于记录 commit 的 blob 与
  HEAD 的 blob（或路径在两者中均不存在，真正的未提交内容）才快照。快照：当前
  字节被复制进 `--snapshot-dir`（仅此时才创建该目录；文件名由 `--artifact-id`
  或内容哈希派生，安全 ASCII），登记 `snapshot` locator 与当前字节的 sha256，
  并显著打印快照路径——**快照必须与记录一起提交**。快照路径已存在且字节不同 →
  拒绝（幂等；换一个 `--artifact-id`），同字节则幂等通过。
- **记录的 commit 不可取回**（垃圾 SHA / 已修剪）：消费者可见失败并说明原因；
  绝不"用当前文件补写旧快照"，清单保持不变。
- 当前文件不存在 → 失败并指明 `current-file`。

不变式：`adopt` 从不把当前字节冒充为记录 commit 的内容；失败一律退出码 2、
单行可读错误、指明字段。

## 新鲜度检查与分诊（Story 007：`check`）

```sh
python tools/evidence_manifest.py check evidence-manifest.yaml \
    [--report FILE]   # 缺省打印到 stdout
    [--records-dir DIR]
```

`check` 是**只读命令**：运行前后断言清单字节不变；它从不写清单、不自动替换、
不为故事择优。替换任何采用版本必须经作者明确批准（审批动作属作者拥有的记录）。

确定性层（ADR-004 第 1 层），逐 artifact 取回比对：

- `unchanged` — 记录 commit 的 blob 与 pin 一致，且仓库 HEAD 同路径及当前工作区
  文件（若存在）仍与 pin 一致。
- `content-changed`（modified-in-place）— locator 处字节与 pin 哈希不同；或
  记录 commit 验证通过但 HEAD 在同一路径的字节已不同（pending 文本给出 HEAD
  commit 与两侧哈希）；或 HEAD 与记录 commit 均匹配 pin，但当前工作区文件字节
  不同（pending 明确标出 working-tree 与哈希）；或路径在 HEAD 已不存在且 pin
  内容未在 HEAD 树中找到。工作区路径缺失本身不表示来源失效（记录 commit
  仍可取回）。
- `path-moved` — 两种触发：(a) 记录 locator 在其 commit 取不回时，扫描**记录
  commit 树**；(b) 记录验证通过但 HEAD 已不含该路径时，扫描 **HEAD 树**（当前
  状态）。树扫描为一次 `git ls-tree -z -r`（NUL 分隔，转义路径按真实路径报告）
  加一次 `git cat-file --batch` 批量读 blob——复杂度以树大小为界，绝无逐 blob
  进程。报告 旧 locator 路径 → 新路径。
- `source-lost` — 来源彻底取不回（含垃圾 commit、快照/留存文件缺失）；失败原因
  写入报告；**绝不回退到任何当前文件**。受影响的 claim 在报告中标记，从不删除
  或建议删除。
- `scientific-invalidation` — **只**来自显式记录标记（frontmatter
  `scientific_invalidation: true` + 目标 + reason）；本工具从不自行推导该类别。

生命周期通道（可选字段，向后兼容；缺省清单照常通过校验）：

- 清单内嵌：`superseded_by`（id 或文本，字符串/列表）、`deprecated`（布尔，
  `true` 时必须给 `deprecated_reason`）、`counter_evidence`（文本/列表），
  可出现在 artifact 或 claim 上。
- `--records-dir DIR`（或显式 `--no-records-dir` 跳过；两者都不给则退出码 2，
  因为 vault 记录检查是 FR-D6 新鲜度工作流的一部分）：试点性的**确定性记录
  检查层**——只扫描 `*.md` 的 YAML frontmatter（无全文语义），识别
  `superseded_by` / `deprecated`（**严格布尔**，字符串值静默跳过；目标按
  `artifact:` / `claim:` / `id:` 解析，显式 `artifact:` / `claim:` 优先于
  record `id`；可带 `reason` / `deprecated_reason`）/
  `contrary_evidence`（可带 `artifact:` / `claim:` / `id:` 子键）/
  `scientific_invalidation: true`（仅显式标记）/ `status: superseded|deprecated`。
  记录通道的 `contrary_evidence` 与清单内嵌 `counter_evidence` 同样经
  `classify_counter_evidence` 标注候选标签。命中记录进入分诊报告；无
  frontmatter 或格式不合法的文件被静默跳过——它们不是关于手稿的证据。

反证候选标签（FR-A3 / SPEC-004）：`classify_counter_evidence(text)` 是**纯描述
性的确定性候选标签**，不是科学判定——文本同时含失效表述与范围限定时返回
`candidate-admissible (scoped-failure wording; requires claim-wording comparison
by reviewer)`，否则 `candidate-review-required`。**本层从不产出"有效/无效"
裁定**：可采性只能由代理/作者把该证据与具体手稿 claim 的措辞和范围逐条比对
后决定（报告在每条 counter-evidence 下显式声明这一点）。从不要求 "SUPPORT"
字样。

分诊报告格式（固定布局）：每条发现给出类别（path-moved / content-changed /
source-lost / superseded / deprecated / counter-evidence /
scientific-invalidation）并**并列**展示 `CURRENT ADOPTED`（id、sha256、locator）
与 `PENDING CHANGE`；content-changed / path-moved / superseded / deprecated /
counter-evidence / scientific-invalidation 各附固定字段的
`COMPARABILITY TRIAGE` 块（research question / structure / parameters /
approximation / processing conditions / scope——全部开放待代理/作者填写，仅
adopted-vs-pending 的确定性 basis 预填）；针对 artifact 的生命周期/反证发现会
解析到清单条目并列出受影响 claim（标记、从不删除；review status: paused
pending author review；未匹配目标保持记录级归属）；来源失效类发现附 FR-K3
风格的 `REQUEST (draft)` 恢复请求草案（纯文本，无审批自动化）。报告结尾固定
声明替换政策：替换需作者明确批准，`check` 从不写清单字节（`--report` 目标若解析
为清单文件本身或指向同一 inode 的硬链接则拒绝），且 FR-D6 要求在宣布"无变化"前
记录（代理第 2 层判断）。科学可比性是代理判断，不是规则引擎。
