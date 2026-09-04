---
mode: agent
description: 接入新馆 —— 定源、体检、登记、入库、评级、metadata、审计、导出
---


按本清单逐步执行。**每一步都有通过判据，不通过就停下来问用户，不要往下跑。**

前置：先读 `AGENTS.md`（尤其「数据库设计约定」九条），再读本文件。

---

## 一条贯穿全程的纪律

**打分与审计必须不同源。** 当前配置：

| | 型号 | 入口 | effort |
|---|---|---|---|
| 打分 `tier_v3.py` | `claude-opus-5` | `claude` CLI headless（**订阅账号，无需 API key**） | 无此旋钮 |
| 审计 `audit_meta.py` | `gpt-5.6-sol` | OpenAI SDK（`~/.openai_key`） | 分阶段，见 `STAGE_EFFORT` |

审计要回答的是「支撑这一级的证据够不够」。审计者若与打分者同源，这个问题的答案
先天可疑。2026-09-02 至 09-05 两边都是 `gpt-5.6-sol`（本机无 Anthropic 凭据），
**交叉验证形同虚设**；09-05 改走 `claude` CLI 后恢复。
`scored_by` / `audited_by` 两列一对照即可看出是否同源 —— **改配置前先看这两列。**

**花钱之前先量。** 成本几乎全在 reasoning token 上（`xhigh` 下占输出的 68%）。
一个 200 件的馆约 190 次调用；4464 件按现结构约 2300–3600 次。
单件实测：打分 5579 token / 审计 11182 token，**审计的输出是打分的 4.7 倍**
（审计产出中英双语散文，打分只产出数字）。

**effort 只对 OpenAI 那条路有效**，且已按阶段分配（`STAGE_EFFORT`）：
评分一 high / 评分二 medium / 评分三 xhigh / 审计 medium。依据是实测降幅与
分数敏感度，见常量注释。`claude` CLI 不暴露 `reasoning_effort`，档位只能靠选型号。

⚠ **model 与 effort 都参与 `llm_cache` 的缓存键**：换任一个等于整批重跑，
而且新旧两批结果**不可直接比较** —— 跨轮比较时若混了型号或档位，
归因不到是「证据变了」还是「模型/推理强度变了」，务必在结论里标明。所以：

- 每一步先跑 `--dry-run` / `--limit` / `--only-seq`，确认链路通了再放量
- **`--limit N` 是「跑 N 件」不是「跑第 N 件」** —— 要单件复核用 `--only-seq`
- 所有调用自动进 `llm_call` 表（提示词哈希做键）：提示词没改必然命中缓存不花钱，
  改了必然重跑。所以**不要为了"干净"去删 llm_call 的行** —— 那是已付费的答案

---

## 步骤 1 · 定源

判定顺序，取第一个可用的：

1. **馆方开放 API**（哈佛有 `api.harvardartmuseums.org`，需申请 key）
2. **馆方开放数据集 / 藏品检索库**
3. **Wikidata**（`meta_scrape.py` 任意馆通用，WDQS 限流时自动切 QLever）
4. **人工 Excel**

**抓回来的原文必须落进仓库**，不能只落进库 —— 参照 `pem_official_data.py` 的成例。
只入库就等于把最硬的证据变成孤儿数据，下次连表都不敢重建。

key 文件权限 600，**不进命令行、不进仓库**（同 `~/.my.cnf`、`~/.openai_key`）。

## 步骤 2 · 源数据体检

**这一步决定后面值不值得花钱，不许跳过。**

| 查什么 | 为什么 |
|---|---|
| 总行数 / 有名称行数 / **填充率** | MFA 旧文件 1300 行只填了 204 行（15.7%） |
| 名称列中间有没有混入表头 | MFA Master 页混着一行 `'Tier'` |
| tier 有几列、两列不一致多少条 | 一律取原表评级列（`AGENTS.md` 第 5 条） |
| `source_seq` 唯一、且与导入器对齐 | 见步骤 4 的强制校验 |
| **名称是编目题名还是描述性转写** | PEM 91% 对不上号，是「身份不可核验」不是「资料薄」 |
| 简介长度中位数 | 六七十字符的一句话撑不起 12 项完备度判定 |
| 有没有 `official_url` / 藏品编号 | 决定证据能否升到 Tier 1 |

**通过判据**：填充率过低、或名称是描述性转写 → **停下来问用户**。
这两种情况下补资料的投入产出极差，得先解决对象身份问题。

## 步骤 3 · 登记（六处，缺一不可）

| 文件 | 登记什么 |
|---|---|
| `import_artworks.MUSEUMS` | 源文件、sheet、表头行、列号、`on_view` 映射 |
| `tier_v3.MUSEUMS` | 同一份源文件的列号（**与上一处必须一致**） |
| `museum_context.CONTEXTS` | 馆级语境，直接决定 IU 与 CR 的判断方向 |
| `audit_meta.MUSEUM_NOTE` | 本馆数据实情，**只陈述事实不给结论** |
| `meta_fill_rule.NAME_ARTIST_PREFIX` | 名称是不是「作者, 题名」格式 |
| `meta_scrape.MUSEUM_QID` | Wikidata 的馆 Q 号 |

**⚠ `on_view` 必须逐馆写映射，绝不能照抄。** 中文馆是「第 5 列非空即在展」，
因为它们第 5 列叫「陈列状态」且全填「当前在展」；MFA 扩充清单第 5 列叫
「**来源**与陈列状态」，4464 行全非空但 4329 行写着「未经官网确认」——
照抄会把 4464 件全标成在展，且不报错。同 PEM「不能拿 Has Image 推在展」。

**⚠ 一个文件里若混着两种出处，必须分成两个 `source_key` 登记**
（`source_rules.py`）。MFA 扩充清单里 135 条来自 mfa.org（Tier 1）、
4329 条来自 Wikidata（Tier 3），混为一谈就是把后者伪装成馆方权威发布。

## 步骤 4 · 入库

```
python3 import_artworks.py --host <host> --user ari --database ari
```
口令走 `MYSQL_PASSWORD` 环境变量或 `~/.my.cnf`，**不用 `--password`**。

**强制校验（`AGENTS.md` 要求）：`source_seq` 逐条对齐。**
`tier_v3.load_items` 与 `import_artworks.read_museum` 各自生成 seq，两边算法
必须一致（都按**过滤之后**的计数自增）。校验方法：逐条比对名称，
拿 `artwork.name_key`（源数据原值，不经翻译）比，并把不换行空格归一化。
不一致就停 —— 2026-09-02 那个张冠李戴 bug 就是这里漏掉的。

**跑完必须接着跑两件事，忘了不报错：**
```
python3 tier_v3_load.py --museum <mk> --apply-tier    # 否则 tier 退回源表评级
python3 llm_cache.py --refresh-ids                     # 否则 artwork_id 指向错行
```

**回归**：导完展品再跑一次 `import_data.py`（城市榜单），两侧行数都应不变。

## 步骤 5 · 评分（花钱）

```
# 先冒烟（--provider 默认就是 claude_cli，走订阅账号的 claude-opus-5）
python3 tier_v3.py --museum <mk> --only-seq <某件> --evidence --out-dir ./run/<mk>
# 确认无误再放量
python3 tier_v3.py --museum <mk> --evidence --out-dir ./run/<mk>
python3 tier_v3_load.py --museum <mk> --out-dir ./run/<mk> --apply-tier
```

**`claude_cli` 这条路的三个代价，放量前必须掂量**（2026-09-05 单件实测）：

1. **慢**。单件三阶段 **1 分 56 秒**（OpenAI 路径约 20 秒）。4464 件 × 3 阶段
   按这个速率是**以天计**的，不是以小时计。
2. **每次附带约 4–5.5k token 的 Claude Code 脚手架**（系统提示词、工具定义），
   走 prompt cache 但仍计入订阅用量。我们自己的提示词只占 `input_tokens: 4`。
3. **订阅账号有用量限额**，这条路径每次调用有固定开销，全馆规模消耗很快。

所以放量前**先在几十件上量实际速率与用量**，再决定是全量走 Claude，
还是只让 S/A 候选走 Claude、B/C 走 OpenAI。

**换模型会改变结论，不只是改变成本。** 同一件《历代帝王像》：
`gpt-5.6-sol` 给 Core 9.318，`claude-opus-5` 给 8.605 —— 分歧集中在
VI（8.6 vs 6.5）与 VA（8.4 vs 6.5），Claude 的理由是「绢本手卷色调晦暗、
需轮展且尺度不具压倒性」。两者都定 S，但 8.605 离门槛 8.5 只有 0.105。
**门槛附近的评级对模型选择高度敏感**，跨模型的结果不要混在一张表里比。

- **`--evidence` 只喂事实，不喂审计结论**。完备度、可信度、缺失证据一律不进 ——
  把「证据不足」交给打分者，几乎必然被读成「该压分」，那就把「不知道」和
  「不重要」混成了一件事
- **分档锚点必须写死在提示词里**。实测：全维度统一 +0.75，
  「132/196 件要改」就变成「24/196 件要改」—— 结论测的是标尺位置，不是算法
- **阶段二占全部调用的 65–68%，其中六成是单件组**（组内独特性无从比较）。
  单件组应合批处理，不是逐组发请求
- 产物 `<mk>_review.csv` 是给人审的，**确认无误前不要写库**

## 步骤 6 · metadata（0 API）

```
python3 meta_seed.py                          # 建键字典
python3 meta_fill_rule.py --museum <mk>       # 从名称/简介确定性提取
python3 meta_scrape.py --museum <mk>          # Wikidata
```

**半结构化的源文本优先用正则抽，不要用模型。** MFA 扩充清单的名称是
`（产地，朝代，年代；材质）`（覆盖 96%）、简介带藏品编号（89%），
`meta_fill_official_mfa.py` 用正则抽了 8 个字段，一次 API 都没调，
而且结果可复算、可复核。

**写入时就填 `evidence_type` / `source_quality`**（按 `source_rules.SOURCE_RULES`），
不要留给审计阶段回填 —— `tier_v3 --evidence` 会把这两列拼进提示词，
NULL 会渲染成 `[?/? · xxx]`，而提示词里教模型怎么读 FACT/strong 的那四行就作废了。

**冲突取值不消解**：同一个键允许多来源并存，靠 `source_key` + `confidence` 区分，
**写入方不挑赢家**（`AGENTS.md` 第 7 条）。

**⚠ 中国分裂时期的朝代不能建成单值字段。** 辽/金/北宋在 12 世纪初并存
（山西北部属辽、南部属北宋，1125 后入金），南北朝、五代十国、三国同理。
拆成 `date_absolute`（绝对年代，各方无争议）+ `polity`（政权归属，可多值并存）。

**批量写入**：逐条 INSERT 跨公网太慢（4464 件 × 8 字段跑 10 分钟没跑完）。
数据量大时必须批量提交。

## 步骤 7 · 证据分与审计

```
python3 evidence_score.py --museum <mk>        # 0 API，规则口径完备度 + best_source_tier
python3 audit_meta.py --museum <mk> --slim --model <model> --out-dir ./run/<mk>
python3 audit_load.py --museum <mk> --out-dir ./run/<mk>
```

**用 `--slim`。** 实测三馆 603 件：12 项里 9 项一次 `full` 都没出现过（占 90 分权重）、
`cultural_educational` 203/203 全 partial、`tier_review_flag` 92–97% 全 true、
`potential_tier_low` 74–92% 全 C、阶段二六问里三问 100% 单一答案。
那些列在真实输入下不携带信息。精简版只留**缺失证据**（MFA 202/203 条不重复）
与 **`found_factual_error`**，完备度改由 `evidence_score.py` 的规则口径给。

**判据的四条硬规矩**（每违反一次代价都是整轮重跑）：

1. **不要把结论写进提示词。** 曾写「就该判低完备度、低可信度」，
   三馆 603 件跑出 95% 以上 `low` —— 指定答案的提示词得到的是提示词自己的回声
2. **馆专属事实只进 `MUSEUM_NOTE`**，不进通用规则
3. **一列一个判据，判据只放在一个地方。** 曾让阶段二覆盖阶段一，
   改判据只改了阶段一，248 件 S/A 的可信度被整片冲成 `low`
4. **`tier_sensitive` 问的是「这条事实有了答案 Tier 会不会变」**，不是「还能不能研究」。
   并存政权的归属之争一律 `false`；既成共识不是缺口

**审计只审证据，绝不改 tier。** `audit_load.py` 写入前后各拍快照，不一致整体回滚。

## 步骤 8 · 导出与验收

```
python3 export_excel.py --defaults-file ~/.my.cnf --museum <mk> --artworks-only
```

- 整跑约 12 分钟，瓶颈是跨公网读 MySQL，不是计算
- 零回落检查 + **英文成品 CJK 扫描**
- **译文必须落进 `translations_*.csv`**，不能只改库 —— 导入器清空重灌，
  写在库里的译文重跑一次就没了
- **中文源的新馆先补译再导**，否则英文版整片漏中文

**验收清单**：
- [ ] 存量各馆行数一个不变
- [ ] `artwork_tier_v3` / `artwork_evidence` / `artwork_meta` 行数与预期一致
- [ ] 新馆 `source_seq` 无缺号、无重复
- [ ] tier 分布与源文件逐格吻合
- [ ] `on_view` 分布可用**没参与判断的列**（如 `official_url` 域名）非循环校验
- [ ] `llm_call` 出一张本轮 token 表，分阶段可查

---

## 两件必须如实记录的事

**① 跨厂商已恢复，但历史数据是同源的。** 2026-09-05 起打分走 `claude-opus-5`
（订阅账号）、审计走 `gpt-5.6-sol`，两端不同源。**但库里现存三馆 603 件的评分与
审计是 09-02 至 09-05 之间跑的，两边都是 `gpt-5.6-sol`** —— 那批的交叉验证无效。
`scored_by` / `audited_by` 一对照即可分辨，这个事实要出现在导出的成品里。
重跑那 603 件之前，不要拿它们的审计结论当独立验证。

**② 目前没有 ground truth。** 所有形式检查（12 项齐不齐、区间方向、q6 一致性、
零回落、CJK 扫描）验的都是**形式**，没有一条比过外部事实。一个自洽但错误的
答案能全部通过 —— 水月观音那份就通过了全部七条检查，而它的 `tier_confidence`
违反了判据自己写的「既成共识本身就是证据」。

**在建立人工核验金标之前，不要声称结果是对的。** 只能说「形式自洽，且忠实
反映了库里资料的贫乏程度」。金标做法：挑 20–30 件逐件对照馆方官方记录人工
判定，存成仓库 CSV，每轮跑完比对出准确率。**选样必须覆盖名作与无名小件两端** ——
只挑名作会重演「用结论倒推判据」。
