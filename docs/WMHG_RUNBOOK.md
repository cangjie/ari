# 伪满皇宫博物院（wmhg）：评分、审计、翻译与导出执行指引

执行者：Codex（或任何接手的 AI 工具）。写于 2026-09-25，前一棒是 claude。

本文件只讲 **wmhg 的第 7–8 阶段**：V3.0 评分 → 审计 → 翻译 → 导出 → 收工。
前面的抓取、入库、metadata 都已完成，**不要重做**。仓库通用规则见 `AGENTS.md`，
本文与它冲突时以 `AGENTS.md` 为准，并停下来问用户。

所有命令都在 `utils/import_data/` 下执行。macOS 用 `python3`，Windows 用 `python`。

---

## 0. 现状（截至 2026-09-24，已在线上库 `ari`）

| 项目 | 状态 |
|---|---|
| 源表 | `artworks/伪满皇宫_展品清单.xlsx`，由 `wmhg_build.py` 生成，61 行。**不要手改** |
| 构成 | 藏品 34 件（官网 30 + 御纹章展文章 4）+ 节点 27 个（官网常设 16 + 御纹章展 1 + 2023 年导览 10） |
| 序号 | `wmhg_seq_map.csv` 按身份键固定，1–61，重跑不改号 |
| 入库 | `artwork` 61 行：在展 22、未知 39；评级全空（等本轮评分） |
| metadata | `artwork_meta` 135 条（`meta_fill_official_wmhg.py`），全部 FACT / strong |
| 证据分 | `artwork_evidence` 61 行，`best_source_tier` 全 1，规则完备度 1.1–3.3 |
| 登记 | `import_artworks` / `tier_v3` / `museum_context` / `audit_meta.MUSEUM_NOTE` / `source_rules` 等七处都已登记 |

**两端必须不同源**：评分走 Codex 订阅（`gpt-5.6-luna`），审计走 Claude 订阅（`claude-sonnet-5`，medium 档）。
这与 PEM、MFA 扩充清单是同一把尺子（AGENTS.md 第 15 条）。**不要换型号，不要换档位**，换了要先问用户。

**节点第一次成批进评分**：V3.0 的 `object_type` 有 object / node / site 三种，node 另有 ER 维度。
此前库里只有零星几件判成 node（PEM 3 件，含荫余堂；MFA 扩充清单 4 件），wmhg 一次有 27 个，
而且全靠源表的「对象层级·类目」提示模型。冒烟时要专门验这一点（见 3.1）。

---

## 1. 硬规矩（违反任何一条就停下来问用户）

1. **失败先查原因，不找到原因不许重跑。** 看 `llm_call.error_text`、脚本输出和 CLI 自己的会话记录
   （AGENTS.md 第 9、10 条）。脚本自带的重试只对网络抖动有意义。
2. **长任务一律用 `llm_guard.py` 包住跑**（见第 5 节）。它发现本任务的第一条失败记录，就结束整棵进程树。
3. **写线上库的命令不要和「再跑一遍」串在同一条命令里**（`&&`、`| tail` 都不行）。
   先看第一次的结果，确认成功再做下一步。写库失败，先查 `information_schema.innodb_trx` 和 `processlist`
   有没有自己留下的残留事务。
4. **每一步都显式写 `--museum wmhg`。** `audit_bc_guard.py` 和 `audit_translate.py` 的默认值是
   `mfa_boston_ext`，漏写就会去动 MFA 的产物。
5. **不要删 `llm_call` 的行**，那是已付费的答案。
6. **口令只走 `~/.my.cnf`**，不进命令行、不进环境变量。
7. **不要改** `wmhg_site_data.py`、`wmhg_exhibition_data.py`、`wmhg_article_data.py`（抓取产物）、
   源 Excel（`wmhg_build.py` 生成）、`wmhg_seq_map.csv`。
8. 两个关卡必须停：**G3**（冒烟之后、放量之前）和 **G4**（评分写库之前），把结果交给用户确认。

---

## 2. 环境自检（开工先做）

在有 `~/.my.cnf` 的机器上执行（macOS 那台或 Windows 那台都行，`host=44.207.251.65`）：

```
python -c "import pymysql, openpyxl; print('py ok')"
python -c "import codex_cli; print(codex_cli.available(), codex_cli.version())"
claude --version
python -c "import meta_lib as M; c=M.connect().cursor(); c.execute(\"SELECT COUNT(*) FROM artwork a JOIN museum m ON m.id=a.museum_id WHERE m.key_name='wmhg'\"); print(c.fetchone())"
```

最后一行应输出 `(61,)`。任何一项不对就停。

- **Windows**：`codex` 与 `claude` 都不在 PATH 上。设 `CODEX_BIN` 指向
  `%LOCALAPPDATA%\OpenAI\Codex\bin\<哈希>\codex.exe`，并把 VS Code 扩展里 `claude.exe` 所在目录加进 PATH。
  中文输出设 `PYTHONIOENCODING=utf-8`（AGENTS.md 第 15 条「在 Windows 上跑管线」）。
- **网络**：这些脚本要连 MySQL（44.207.251.65:3306），还会派生 `codex exec`（连 OpenAI）和
  `claude -p`（连 Anthropic）子进程。如果你所在的沙箱禁网，这几步要申请放开网络权限再跑。
- **额度**：Codex 订阅 09-22 用尽，09-25 17:35 才恢复。一旦报 `usage limit`，**停下告诉用户**，
  不要退避重试（AGENTS.md 第 15 条）。

---

## 3. 第 7 阶段：V3.0 评分

产物目录：正式跑用 `./run12/tier_wmhg`，冒烟用 `./run12/tier_wmhg_smoke`，**两者分开**。
一律带 `--evidence`：把 `artwork_meta` 里的已核实事实喂给打分者。

### 3.1 冒烟：1 件藏品 + 1 个节点

seq 13 是「日本黄釉凤纹七宝烧瓶」（藏品，metadata 最全），seq 36 是「同德殿」（宫廷原状陈列）。

```
python llm_guard.py --provider openai_codex --stage "tier_stage%" --museum wmhg -- \
  python tier_v3.py --museum wmhg --provider codex_cli --model gpt-5.6-luna --evidence \
    --only-seq 13 --only-seq 36 --out-dir ./run12/tier_wmhg_smoke
```

跑完逐项核对，**任何一项不符就停**：

1. `run12/tier_wmhg_smoke/wmhg_stage1.jsonl`：seq 36 的 `object_type` 是 `node`，且 `ER` 大于 0；
   seq 13 是 `object`，`ER` 为 0。
2. 启动时打印的「证据模式：x/2 件带已核实事实」里，x 应为 2。
3. `run12/tier_wmhg_smoke/wmhg.model` 内容形如 `gpt-5.6-luna effort=high/medium/xhigh (codex-cli)`。
4. 查本次每次调用的 token 用量：

```
python -c "import meta_lib as M; c=M.connect().cursor(); c.execute(\"SELECT stage, COUNT(*), AVG(completion_tokens), AVG(prompt_tokens) FROM llm_call WHERE museum_key='wmhg' AND provider='openai_codex' GROUP BY stage\"); print(c.fetchall())"
```

### 3.2 关卡 G3：交给用户确认后才放量

向用户报告：两件的 `object_type`、ER、Core、tier，每次调用的 token 用量，以及全量的调用次数估计：

- 阶段一：`ceil(61 / 12) = 6` 次（`--batch` 默认 12）
- 阶段二：**按 peer_group 逐组发**，次数 = 阶段一跑完后的组数（估 30–50 组）。
  **单件组不合批**，AGENTS.md 第 15 条结论二已实测合批会系统性压低 CR。
- 阶段三：只对 S 候选跑（Core ≥ 8.5 且有一维 ≥ 9），通常 0–5 次

### 3.3 全量：分阶段跑

先只跑阶段一，数一下组数再跑阶段二和三。每一步都用守护包住：

```
python llm_guard.py --provider openai_codex --stage "tier_stage%" --museum wmhg -- \
  python tier_v3.py --museum wmhg --provider codex_cli --model gpt-5.6-luna --evidence \
    --stage 1 --out-dir ./run12/tier_wmhg

python -c "import json; g={json.loads(l)['peer_group'] for l in open('run12/tier_wmhg/wmhg_stage1.jsonl',encoding='utf-8')}; print(len(g), sorted(g))"

python llm_guard.py --provider openai_codex --stage "tier_stage%" --museum wmhg -- \
  python tier_v3.py --museum wmhg --provider codex_cli --model gpt-5.6-luna --evidence \
    --stage 2 --out-dir ./run12/tier_wmhg

python llm_guard.py --provider openai_codex --stage "tier_stage%" --museum wmhg -- \
  python tier_v3.py --museum wmhg --provider codex_cli --model gpt-5.6-luna --evidence \
    --stage 3 --out-dir ./run12/tier_wmhg
```

- 组数与 G3 时的估计差得多（比如翻倍），先停下问用户。
- 中途额度耗尽：每组是原子的，已完成的在缓存里。**等额度恢复后原命令续跑**，不要反复重试。
- `--seq-from/--seq-to` 只能配 `--stage 1` 用；61 件用不着分批。

### 3.4 关卡 G4：审阅后才写库

产物 `run12/tier_wmhg/wmhg_review.csv`。向用户报告：

- tier 分布，**藏品与节点分开列**（节点是 seq 35–61）；
- 所有 S 与 S 候选，附 S-ness 结论；
- 节点里 `object_type` 不是 `node` 的（应该没有）；
- 只有 2023 年导览一两句话的 10 个节点（seq 52–61）如果拿到 A/S，单独列出，这类要重点看；
- peer_group 的分组是否合理（比如同一类纪念章是否在同一组）。

**用户确认后**才写库，先试跑，看完输出再正式执行（**不要串在一条命令里**）：

```
python tier_v3_load.py --museum wmhg --out-dir ./run12/tier_wmhg --apply-tier --dry-run
python tier_v3_load.py --museum wmhg --out-dir ./run12/tier_wmhg --apply-tier
python evidence_score.py --museum wmhg
```

这里用 `--apply-tier` 是对的：wmhg 刚评完，评分表要从 JSONL 写入。
另一个开关 `--apply-only` **只用于重灌展品之后**，只把 `artwork.tier` 刷回评分表的结论，不在这里用。

---

## 4. 第 8 阶段：审计、翻译、导出

### 4.1 审计四步（顺序不能乱，AGENTS.md 第 9 条）

产物目录 `./run12/audit_wmhg`。61 件、batch 48，所以阶段一是 2 批，每批约 5 分钟。

```
python llm_guard.py --provider anthropic_cli --stage "audit_%" --museum wmhg -- \
  python audit_meta.py --museum wmhg --provider claude_cli --model claude-sonnet-5 \
    --slim --batch 48 --out-dir ./run12/audit_wmhg

python audit_bc_guard.py --museum wmhg --out-dir ./run12/audit_wmhg

python llm_guard.py --provider openai_codex --stage audit_trans -- \
  python audit_translate.py --museum wmhg --out-dir ./run12/audit_wmhg \
    --provider codex_cli --model gpt-5.6-luna

python audit_load.py --museum wmhg --out-dir ./run12/audit_wmhg --dry-run
python audit_load.py --museum wmhg --out-dir ./run12/audit_wmhg
```

- `audit_meta.py` 走 `claude_cli` 时档位固定为 medium，写进 `audited_by` 的字样形如
  `claude-sonnet-5 effort=medium (claude-cli)`。不是这个样子就停。
- `audit_translate.py` 的退路顺序：Codex → Gemini 免费层 → claude haiku（`--provider claude_cli
  --model claude-haiku-4-5 --size 100`）。换退路前先确认上一条为什么失败（AGENTS.md 第 15 条）。
  换了 provider，守护的 `--provider` 也要跟着换（`google` / `anthropic_cli`）。
- `audit_load.py` 写库前后会给 `artwork.tier` 拍快照，**不一致会整体回滚**。审计只审证据，不改评级。

审计应能查出的已知疑点（**查出来是对的，不是审计出错**）：

- seq 18 伪满建国功劳章：官网原文写「直径30厘米」，同段还有「章绶宽为35厘米」，疑为单位写错。
  metadata 照录了原文。
- seq 29 景仁宫御用地毯：简介里的长宽是剪开之前的原始尺寸，metadata 故意没录。
- 节点 seq 52–61 只有 2023 年导览的一两句话，现状未核实。

### 4.2 翻译

中文源的馆导出英文版之前必须先补英译（AGENTS.md「中文源的馆导出英文版」一节）。
先看缺多少：

```
python translate_artwork.py --museum wmhg --dump
```

再补（中译英，然后给只有英文的九谷盘 seq 30 补中文名）：

```
python llm_guard.py --provider openai_codex --stage "trans_artwork%" -- \
  python translate_artwork.py --museum wmhg --provider codex_cli --model gpt-5.6-luna

python llm_guard.py --provider openai_codex --stage "trans_artwork%" -- \
  python translate_artwork.py --museum wmhg --provider codex_cli --model gpt-5.6-luna --direction en2zh
```

- 翻译调用的 `museum_key` 可能是空的，所以守护这里**不给 `--museum`**。
- 译文会同时写进 `content_text` 和 `translations_artwork_*.csv`，**这几个 CSV 必须提交**。
  导入器每次清空重灌，只写在库里的译文重跑一次就没了。
- 22 件藏品的英文名和英文简介是馆方原文（机翻，记为「原始」），用户 09-24 定照录。
  脚本只补缺的，不会覆盖它们。**不要**为了改善质量去改写。

### 4.3 导出

```
python export_excel.py --defaults-file ~/.my.cnf --museum wmhg --artworks-only
```

约 12 分钟，慢在跨公网读库，不是卡住了。产物落在 `exports/`（已 gitignore）。

英文版的 CJK 扫描**预期会报**下面这些 metadata 取值（英文侧照中文写的），不是漏译：
作者（大山雅堂、冈本大更、松村景文、渡边华山、喜多川龟麿）、官方展厅「怀远楼二楼清宴堂」。
除此之外的 CJK 回落都要查。

---

## 5. 守护工具 `llm_guard.py`

```
python llm_guard.py --provider <llm_call.provider> --stage "<LIKE 模式>" [--museum wmhg] -- <命令…>
```

- 启动时记下 `llm_call` 的 `MAX(id)`，**只看之后新增的**、`status='error'`、provider / stage / museum
  都对得上的记录。一旦发现，就结束整棵进程树（Windows `taskkill /T`，其他系统按进程组），退出码 3。
- 各流水线的名字：评分 `openai_codex` + `tier_stage%`；审计 `anthropic_cli` + `audit_%`；
  审计补英译 `audit_trans`（provider 随退路变）；展品翻译 `openai_codex` + `trans_artwork%`。
- 退出码 3 就是发现了失败：**先查原因**（打印出来的 `error_text`、CLI 会话记录），不要重跑。

---

## 6. 提交与收工

1. 提交产物（`run11/` 的同类产物也入库，只有日志被 gitignore）：
   - `run12/tier_wmhg/`、`run12/tier_wmhg_smoke/`：`*.jsonl`、`wmhg_review.csv`、`wmhg.model`
   - `run12/audit_wmhg/`：`*.jsonl`、`wmhg.model`（精简口径不出审阅 CSV，PEM 那次也是这样）
   - `translations_artwork_*.csv`
2. 走收工流程（`$end-work`），在 `AGENTS.md` 里**就地修订**：
   - 「数据库设计约定」开头那张管线覆盖表：`wmhg` 一行，写上展品数、V3 评分、evidence、metadata、审计口径；
   - wmhg 的评分与审计结论：tier 分布（藏品和节点分开）、节点判成 node 的情况、审计查出的事实错误；
   - 第一次给节点评分的观察：ER 是否起作用，节点和藏品放在同一把尺子上是否合适。
3. PROGRESS 条目的工具名写 `codex`。
