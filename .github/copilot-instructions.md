# ari — AI 协作约定

> **本文件与 `.github/copilot-instructions.md` 是同一份内容的两个副本，逐字相同。**
> 事实源是 `AGENTS.md`；`.github/copilot-instructions.md` 由收工流程自动复制生成。
> 要修改规则，请改 `AGENTS.md`，**不要**改 `.github/copilot-instructions.md`。

本文件是本仓库所有 AI 编码工具的唯一事实源。Claude Code、GitHub Copilot、OpenAI Codex 共用这一套规则，行为必须一致。

---

## 项目

**ari** —— 产品定位尚未确定，见 `PROGRESS.md` 的未决项。

本仓库是 monorepo 根目录，将包含一个服务端子项目和多个客户端子项目。

- 仓库：`git@github.com:cangjie/ari.git`
- 主分支：`master`

### 子目录

- `web_api/` —— 服务端 Web 应用，FastAPI，静态页面与接口同进程提供。已上线，见 `docs/WEB_API.md`
- `utils/` —— 项目用到的临时工具。目前只有 `utils/import_data/`：把 Excel 数据源导入 `ari` 库的脚本与译名表，见 `utils/import_data/README.md`
- `docs/` —— 项目说明文档。服务器环境、web_api 部署、算法规格等都放这里。**例外：`AGENTS.md`、`CLAUDE.md`、`PROGRESS.md` 必须留在仓库根目录**，它们被 AI 工具与收工流程按固定路径读写，挪走会静默失效
- 客户端子目录尚未创建，待产品定位与客户端范围明确后再定

**子目录由用户创建，AI 不要擅自新建。** 用户创建后会明确告知，届时再往里写代码。

## 技术选型

服务端基础栈已确定：

- Python 3.14 + FastAPI，Uvicorn 作为 ASGI 服务
- MySQL 8.4
- Nginx 反向代理
- systemd 管理服务进程

客户端技术选型仍待产品定位与客户端范围确定后再决定。

### 服务器环境

- AWS 主机：`44.207.251.65`
- 系统：Ubuntu 26.04，ARM64（aarch64）
- SSH：`ubuntu@44.207.251.65`
- 域名：`ari.goldenma.xyz`，A 记录指向 `44.207.251.65`
- 公网入口：HTTPS `443`（web_api 正式入口）、HTTP `80`（301 跳转到 443）、MySQL `3306`、Nginx 环境验证 `8000`
- 本机入口：Uvicorn `127.0.0.1:8002`（web_api）、`127.0.0.1:8001`（smoke）、MySQL X Protocol `127.0.0.1:33060`
- 服务：`mysql`、`nginx`、`ari-web-api`、`ari-smoke` 均由 systemd 管理并开机启动
- 代码：仓库 clone 在 `/home/ubuntu/ari`，属主 `ubuntu`；服务以 `ari` 用户运行，对代码**只读**
- `/home/ubuntu` 权限为 `755`，否则 `ari` 用户穿不进去读不到代码
- 部署方式：`cd /home/ubuntu/ari && git pull --ff-only` + `sudo systemctl restart ari-web-api`
- Python 虚拟环境：`/opt/ari/.venv`（Python 3.14），web_api 与 smoke 共用
- TLS 证书：`/etc/ssl/ari/`，TrustAsia 手动签发，**2026-11-19 到期且无自动续期**
- 临时健康检查：`/opt/ari/smoke`，仍在 8000 上跑，作为环境自检对照；web_api 稳定后可退役
- MySQL 已按用户明确要求允许 `root@%` 公网登录，未强制 TLS；密码不进入仓库
- 业务库 `ari`（utf8mb4 / utf8mb4_0900_ai_ci），账号 `ari` 有 `ari`.* 全部权限，`localhost` 与 `%` 两个 host 都建了。密码不进仓库
- MySQL 8.4 用 `caching_sha2_password`。命令行客户端默认 `ssl-mode=PREFERRED` 可直连；JDBC 之类的客户端首次连接可能要加 `allowPublicKeyRetrieval=true`
- GitHub Deploy key：服务器 `ubuntu` 使用 `~/.ssh/id_ed25519`，指纹为 `SHA256:AJphJnfR+F7Id8JIonFKKchfVGeU6iWTssOZqJiJWD0`，已验证可访问 `cangjie/ari`
- 基础环境的设计、实施计划与部署记录见 `docs/SERVER_ENVIRONMENT.md`、`docs/SERVER_ENVIRONMENT_PLAN.md`、`docs/SERVER_ENVIRONMENT_REPORT.md`；web_api 的部署记录见 `docs/WEB_API.md`

### 数据库设计约定

`ari` 库现有 14 张表 + 5 个视图：两个源数据集（城市榜单、展品清单）之外，
另有 V3.0 评级、metadata、evidence、元数据质量审计四套派生数据，
以及 LLM 调用的缓存与计量（`llm_call` / `llm_call_item`）。
展品侧现有 **7 个 museum key、13348 件**（2026-09-04 新增 `mfa_boston_ext` 4464 件）。

**管线覆盖到哪儿了（2026-09-06 实测）—— 四个馆跑过，三个馆一件没碰：**

| 馆 | 展品 | V3 评分 | evidence | metadata | 审计口径 |
|---|---:|---:|---:|---:|---|
| `mfa_boston_ext` | 4464 | 4464 | 4464 | 14388 | **slim**（只 7 列） |
| `ham` | 204 | 204 | 204 | 437 | 完整 |
| `mfa_boston` | 203 | 203 | 203 | 393 | 完整 |
| `pem` | 196 | 196 | 196 | 612 | 完整 |
| `capital` / `palace` / `nmc` | 6159 / 1757 / 365 | **0** | **0** | **0** | 未跑 |

`mfa_boston_ext` 的 evidence 行虽然是 4464，但 `completeness` / `research_priority` /
`best_source_tier` 都还是占位值 —— **`evidence_score.py` 对这个馆从未跑过**，详见第 9 条
的 slim 说明。

完整说明见 `utils/import_data/README.md`，以下十一条是改代码前必须知道的，踩过就知道疼：

**1. 所有展示文本走内容表，主表只存内容ID。**
`content`（一段内容一个ID）+ `content_text`（`(content_id, lang)` 唯一，`lang` 用
BCP-47 标签 `zh-CN`/`en`）。加语种只是多插行，不动表结构。
去重是真去重：115 个国家名只占 115 行，7 条 `data_source` 只占 7 行。

**2. 主表同时保留 `*_key` 规范名与 `*_cid` 内容ID，两者缺一不可。**
内容ID只能保证「ID不重复」，保证不了「文本不重复」。`uk_city_name_country`、
`uk_site_name_city`、`uk_gallery_museum_name` 这类去重约束必须落在 `*_key` 上，
按国家筛选也走 `country_key` 索引而不必 join。`*_key` 取源数据原值，从不用于展示。

**3. `content` 表按 `kind` 划分所有权，ID 分段隔离。现在是三段。**

| 数据集 | 写入者 | kind | ID 段 |
|---|---|---|---|
| 城市/点位榜单 | `import_data.py` | `city_name`…`data_source` | 1 – 999,999 |
| 展品清单 | `import_artworks.py` | `museum_name`、`gallery_*`、`artwork_*` | 1,000,000 起 |
| 展品 metadata | `meta_seed.py` / `meta_lib.py` | `meta_key_name`、`meta_value_text` | 2,000,000 起 |

`content.kind` 是**固定 ENUM**，加 kind 要同时改三处：`schema.sql` 的 ENUM（从零建库）、
`schema_meta.sql` 的 ALTER（存量库补种）、以及对应写入者的 kind 常量。漏掉任何一处都不
报错 —— MySQL 报的是 `1265 Data truncated`，不是「未知取值」，第一次撞上很容易误判。
`content_text.source` 同样是固定 ENUM，只有 `原始/AI翻译/存疑/人工校对` 四个值。

**两个导入器都只删自己名下的 kind。** 早先的版本无条件 `DELETE FROM content`，
会把另一侧的文本一起删掉；而展品外键是 RESTRICT，真删起来是整个导入直接报错。
改动任一导入器的清空逻辑后，务必跑回归：导完展品再跑一次榜单导入，两侧行数都应不变。

**4. `museum.site_key` 是软链不是外键。**
`import_data.py` 每次重灌都 `DELETE FROM cultural_site`，硬外键 RESTRICT 会让榜单
导入失败、CASCADE 会静默删光展品；且七个 key 里 PEM／哈佛／首博三家根本不在
`cultural_site` 中。查询时 `LEFT JOIN cultural_site ON name_key = site_key`。

**5. 源文件有两列 tier 时，一律取原表评级列，不取后来重算的那列。**

| 文件 | 入库的列 | 丢弃的列 | 两列不一致 |
|---|---|---|---|
| PEM | `Tier`（第 0 列） | `tier_c`（第 1 列） | 36 条 |
| 哈佛 | `Tier`（第 3 列） | `tier_c`（第 4 列） | 86 条 |
| 故宫 | `原 Tier`（第 8 列） | `Tier（重评）`（第 7 列） | 828 条 |

MFA／国博／首博只有一列 tier，无从选择。重算列会把一批 S 降级（哈佛的莫高窟 320 窟
壁画残片就被降到 B），用户 2026-08-28 明确以原表评级为准。

故宫的两点已知代价，是代价不是 bug：① `原 Tier` 有 157 条「（原表未评）」，
由 `tier_of()` 归为 NULL，进「无评级」；② 第 9 列不可替代性得分与第 10 列评级理由
属于重评那一套，与 tier 不同源 —— 「评级理由」解释的是重评结论，未必解释得通原表
评级，导出表里这两列跟 tier 对不上是预期行为。

**改了 tier 取值列必须做非循环验证。** 拿库去比**自己选的那一列**永远是 0 不一致，
什么也没证明；要比的是源文件里你**没选**的那一列，或直接指定列号重跑比对。
2026-08-28 就是先犯了这个错才漏掉故宫。

**⚠ MFA 的源文件只填了 15.6%，那 1300 行是骨架不是数据。** `Master` 页 1300 行里
只有 203 行有名称与简介，其余只有 Rank 和 Tier：S 100 格填 30、A 300 格填 67、
B 899 格填 106。`Tier S` / `Tier A` / `Tier B` 三页是同一批数据的分页副本，填充率相同，
**这份文件里没有更全的版本**。哈佛（204/204）与 PEM（196/196）是填满的。

**⚠ 但 MFA 另有一份 4464 件的扩充清单，2026-09-04 已作为独立馆 `mfa_boston_ext` 导入。**
`MFA_展品清单_400_带Tier.xlsx`（名字叫 400，实为 4464 件）4464 行全有名称、简介与
官方页面链接，格式与三个中文馆同构。**它不是旧文件的超集**：北斋《神奈川冲浪里》、
Revere 自由之子碗均不在其中，全表日本相关条目仅 16 条（Wikidata 对 MFA 的覆盖偏欧美绘画），
而日本艺术恰是 MFA 的身份板块。所以是**两份互补，取并集合并**（用户 09-03 决定），
**不是新旧替换** —— 合并前必须先建新旧 `source_seq` 映射，否则现有 799 行派生数据会
原封不动贴到完全不同的展品上且不报错。合并尚未做。

**⚠ 这份扩充清单里混着两种出处，性质差别很大，必须分开对待：**
135 件 `official_url` 指向 `mfa.org`（馆方展厅/部门页，带馆藏号、断代、材质、
入藏基金与展厅位置，Tier 1）；4329 件指向 `wikidata.org`（带藏品编号可回官网核对，
但源文件自承「展厅与在展状态未经官网确认」，Tier 3）。已分成 `mfa_official` 与
`mfa_ext_wikidata` 两个 `source_key`。**`on_view` 也因此不能照抄中文馆的映射** ——
中文馆第 5 列叫「陈列状态」且全填「当前在展」，这份第 5 列叫「**来源**与陈列状态」，
4464 行全非空，照抄会把 4464 件全标成在展且不报错（同 PEM「不能拿 Has Image 推在展」）。
现按 `official_url` 域名映射：135 件在展 / 4329 件未知，已用未参与判断的列做非循环校验。

**⚠ 读源 Excel 生成 `source_seq` 时，必须按「过滤之后」的计数自增。**
`import_artworks.read_museum` 是这么做的，`tier_v3.load_items` 曾用 `enumerate` 的行号
—— 空占位行照样把计数推进，于是 MFA 每一件的分都会张冠李戴，**且不报错**。
PEM 与哈佛没有空行，两种算法碰巧一致，这个 bug 藏到 2026-09-02 才暴露。
新增馆时先查一遍：源表有没有空行、名称列中间有没有混入重复表头。

**6. tier / metadata / evidence / 审计四套数据都放独立表，不加到 `artwork` 上。**

`import_artworks.py` 第 355 行 `DELETE FROM artwork` 清全表并重置 AUTO_INCREMENT。
加在 `artwork` 上的列下次重灌就蒸发，且 `artwork.id` 每次重新分配，不能做跨重灌的引用。
这几张表一律用软键 `(museum.key_name, artwork.source_seq)`，**故意不建到 artwork 的外键**
（硬外键 RESTRICT 会让导入失败，CASCADE 会静默删光）。已实测该键在 13348 行全局唯一。

**⚠ `artwork.id` 与 `museum.id` 都是每次重灌重新分配的，任何地方都不要存。**
导入器对 `museum` / `gallery` / `artwork` 三表全部 `DELETE` 并 `ALTER AUTO_INCREMENT = 1`，
然后按 `MUSEUMS` 的**列表顺序**重新发号。2026-09-04 实测：把 `mfa_boston_ext` 插进
列表第 2 位，PEM 的 `museum.id` 就从 2 变成 3、首件 `artwork.id` 从 204 变成 4668 ——
PEM 自己一个字都没改。加在列表末尾这次能躲过，下次躲不过：只要前面任何一个馆的
源文件行数变了，后面所有馆的 id 就整体平移。

| 表 | 装什么 | 由谁写 |
|---|---|---|
| `artwork_tier_v3` | V3.0 七维分、Core、S-ness、评分依据 | `tier_v3_load.py` |
| `meta_key` / `artwork_meta` | metadata 键字典与取值（纯 key-value） | `meta_seed*.py` / `meta_fill_rule.py` / `meta_scrape.py` / `meta_fill_official_pem.py` |
| `artwork_evidence` | 完备度、研究优先级、逐维度可信度、缺失证据 | `evidence_score.py` + `evidence_fill.py` |
| `artwork_evidence` 的审计列 | Tier 可信度、潜在 Tier 区间、需复核、研究问题 | `audit_load.py` |
| `llm_call` / `llm_call_item` | 每次 LLM 调用的问答原文、token 用量、覆盖了哪些展品 | `llm_cache.py` |

**⚠ 每次跑完 `import_artworks.py`，必须接着跑两件事：**

```
python3 tier_v3_load.py --museum <mk> --apply-tier   # 否则 artwork.tier 退回源表评级
python3 llm_cache.py --refresh-ids                    # 否则 llm_call_item 的便利列指向错行
```

**第一条现在由导入器自己兜底**（`stale_tier_guard()`，收尾时比一遍
`artwork.tier` 与 `COALESCE(tier_override, tier)`，不一致就按馆报警并打印该跑的命令）。
加这个是因为规则写在文档里挡不住：`DELETE FROM artwork` 清的是**全表**，
而人只会想到自己刚动过的那个馆 —— 2026-09-04 加 `mfa_boston_ext` 时就只给新馆
跑了 `--apply-tier`，另外三馆 187 件（PEM 56 / MFA 76 / 哈佛 55）悄悄退回源表评级，
两天后从导出的 tier 分布里才偶然看出来。**第二条仍然靠人记，忘了不报错。**

`artwork_evidence` 现在有**三个**写入者分写不同列，职责必须互斥，`evidence_score.py`
必须用 UPSERT —— 早先它用先删后插，把 `evidence_fill.py` 刚写的可信度与缺失证据
一并冲成 NULL，且不报错。

**⚠ 所有权判断不能用「整个脚本退出」来实现。** 2026-08-31 为了让 `evidence_score.py`
不覆盖已审计行，加了「全馆都审过就 return」；而 `best_source_tier` 的重算在那个
return **之后**，于是一个馆审计完成后这一列就再也不更新了。2026-09-04 实测：
MFA 20 件、哈佛 12 件明明已抓到 Wikidata（Tier 3），`best_source_tier` 却全馆卡在 4
—— **而审计读的正是这一列**。只能跳过本脚本不该碰的那几列，不能跳过整个脚本。`completeness` 等四列由 `evidence_score.py` 与 `audit_load.py`
共写，靠 `completeness_src` 分辨所有权：写成 `audit` 的行 `evidence_score.py` 一律跳过。

**两个 completeness 不是一个东西**：`rule` 口径是「八个桶里 key 在不在 `artwork_meta`」
的纯填充率（PEM 中位 1.1/100，含义是「多数件只有 `object_form` 一个键」，
不是「这批东西没价值」）；`audit` 口径是 12 项逐项判 full/partial/none/na、
na 从分母剔除后归一化，量的是「资料够不够支撑判断」。

**7. `artwork_meta` 允许同一个键有多个来源的冲突取值，不消解。**

主键含 `source_key`：`(museum_key, source_seq, key_name, source_key, ord)`。
写入方只清空自己 `source_key` 的旧值。抓取数据彼此矛盾是常态 —— 实例：seq 15 费克肖像的
馆藏号，PEM 官方是 `100183`，Wikidata 是 `M11043`（`M` 前缀疑为老 Peabody Museum 编号，
纯数字疑为 Essex Institute 编号，两馆合并而来，未必是错）。谁对谁错交给读取方按
`source_key` + `confidence` 判断，写入方不挑赢家。若按覆盖写，这类矛盾会永远看不见。

**⚠ 中国分裂时期的朝代不能建成单值字段。** 辽/金/北宋在 12 世纪初是**并存政权**，
不是先后相承（山西北部属辽、南部属北宋，1125 后才全境入金）；南北朝、五代十国、
三国同理。同一件对象被不同来源标成「金代」与「宋代」**不是数据打架**，是不同的
政权归属表述。故拆成 `date_absolute`（绝对年代，各方无争议）+ `polity`（政权归属，
可多值并存）。这类归属之争在审计里一律判 `tier_sensitive=false` —— 学术上真实存在、
也可能永远定不下来，但它不改变游客该不该优先看这件东西。

**⚠ 从半结构化文本抽字段时，绝不能按位置猜。** 2026-09-04 实测：
`MFA_展品清单_400_带Tier.xlsx` 里两种来源的名称括号结构完全不同 ——
官网那 96 件是「（产地，年代；材质）」、Wikidata 那 3387 件是「（作者，ISO日期，材质）」，
而官网那批的第一段实测有 **76 种取值**（产地、年代、朝代、材质、题材描述、专辑标签混在一起）。
初版按位置把第一段一律当产地，**3370 条人名会被写成产地**（「威廉·莫里斯·亨特」「閻立本」）。
正确做法是**逐段按模式判别，认不出的一概不写**：
  · 朝代与产地**整段等值**匹配（「宋」是朝代，「宋徽宗」是人名）；
  · 材质必须靠子串匹配，而子串规则撞上音译人名就是灾难
    （约翰·辛格·沙「金」、欧仁·「布」丹、立「石」春美，实测误判 207 条）——
    所以在「这一段按格式应该是人名」的位置要关掉子串规则；
  · 解析的输入取 `artwork.name_key`（源数据原值），**不要取展示名** —— 展示名会被
    译名表覆盖，覆盖后括号里要抽的东西就没了。
取舍与 `meta_fill_rule.looks_like_person` 一致：宁可漏一条 metadata，也不能写错 ——
错的事实会被当证据喂进评分，漏掉的只是少一条。

**8. 数据库口令走 `~/.my.cnf`（权限 600），不进命令行。**

所有脚本用 `meta_lib.connect()` 或 `--defaults-file ~/.my.cnf`。**不要用 `--password`** ——
命令行里的口令会进 shell 历史，也会被权限系统写进 `.claude/settings.json` 的 allow 列表，
而该文件必须提交进仓库。

**9. 元数据质量审计只审证据，绝不改 tier。**

`audit_meta.py`（判定）→ `audit_load.py`（写库）。审的问题是「支撑当前 Tier 的证据
够不够」，不是「这件东西该是几级」。`audit_load.py` 写入前后各拍一次 `artwork.tier`
与 `artwork_tier_v3` 的快照，不一致就整体回滚，且**故意不提供** `--apply-tier`
之类的开关。发现证据不足时该做的是标 `tier_review_flag` 交给人看。

- `tier_confidence`（审计者对当前 Tier 结论的信心）与 `artwork_tier_v3.confidence`
  （打分那一刻打分者对手上证据的可信度）**是两回事**。**low 不等于该降级**：
  允许「S — Low Confidence」，也允许「B — High Confidence」，两者都不触发自动升降级。
- 潜在 Tier 区间写成「下界–上界」，差的那端在前：`B–S` 读作「最差 B，最好可能到 S」。
- `artwork_meta.evidence_type` / `source_quality` 逐条区分外部事实与 AI 推断。
  判 FACT 必须指得出真实来源，`audit_load.py` 有硬检查：来源若仍写着
  `Evidence Packet …` 直接报错退出 —— **Evidence Packet 是信息容器，不是信息来源**。
  非 `evidence` 来源按 `source_key` 确定性回填（`SOURCE_RULES`），遇到没登记过的
  `source_key` 报错退出，不猜。
- **型号不写死**（`--model` → `OPENAI_MODEL`），key 从 `~/.openai_key`（权限 600）读，
  **同 MySQL 口令一样绝不进命令行**。实际型号写进 `audited_by` / `scored_by`，
  两者对照即可看出审计者与打分者是否同源。

**⚠ 截至 2026-09-06，库里 5067 件一件都没享受到跨厂商交叉验证 —— 四个馆全是
OpenAI 打分、OpenAI 审计。** `mfa_boston_ext` 更是两边同一型号：

| 馆 | `scored_by` | `audited_by` |
|---|---|---|
| pem / ham / mfa_boston（603 件） | `gpt-5.6-sol xhigh` | `gpt-5.6-sol xhigh` |
| mfa_boston_ext（4464 件） | `gpt-5.6-luna high/medium/xhigh` | **`gpt-5.6-luna medium`** |

`claude_cli.py`（用本机 Claude Code 订阅账号跑 `claude-opus-5`，无需 API key）09-05 就
建好了，也确实在两件测试展品上跑通 —— **但 4464 件全量那轮为了赶时间两边都退回了 luna**，
`llm_call` 里只剩几次 `claude-opus-5` 的痕迹。曾经写在这里的「09-05 起跨厂商恢复」
是**没有兑现的计划，不是事实**，已就地改正。

**同源审计做出来的可信度，本质是打分者给自己打分。** 拿现存任何一个馆的审计结论当
独立验证之前，先看这两列。补救成本不高：审计改走 `claude_cli`，不花 OpenAI 的钱
（走订阅），代价是慢 —— 实测 `claude` CLI 每次调用 45–120 秒，OpenAI 是 4–47 秒。

**⚠ `--slim` 只产出 7 列，跑完导出的「元数据审计汇总」会大半是空的 —— 不是导出算错。**
slim 是为省钱设的精简口径：只问「缺哪些证据、有没有事实错误」，**不判 12 项完备度、
不出 `tier_confidence`、不出潜在区间、不跑阶段二**。2026-09-06 `mfa_boston_ext`
4464 件全量用 slim 跑完，汇总表除了「对象总数」和 metadata 三行之外全是 0。

三处连锁，每一处单看都不像 bug：

1. **slim 写的列**：`tier_review_flag`、`review_reason(_en)`、`missing_evidence(_en)`、
   `top_missing(_en)`、`audited_by`、`audit_round`、`audited_at`。**没有** `tier_confidence`、
   `potential_tier_low`、`completeness_detail`、`research_question`、`inference_only_survives`。
2. **`export_excel.py` 拿 `tier_confidence` 非空当「这件审过没有」的探针**
   （`audited = [r for r in rows if r[5] is not None]`）。slim 不写这一列，于是 `audited`
   是空表，后面每一项都从它派生 —— 连**已经跑出来的** 4464 件已审、4460 件需复核、
   Top 20 研究优先级清单也一起被挡在外面。拿一列代理另一件事，同「不能拿 Has Image
   推在展」。
3. **slim 的 INSERT 只列 10 个列名，其余全吃表默认值**，于是
   `completeness NOT NULL DEFAULT 0` → 平均完备度 `0.00`、
   `research_priority NOT NULL DEFAULT 0` → 优先级全 0、
   `completeness_src NOT NULL DEFAULT 'rule'` → **这一行在撒谎**：它声称是
   `evidence_score.py` 的填充率口径，而那个脚本对这个馆压根没跑过
   （`generated_by` 全是表默认的 `manual`，`best_source_tier` 全 NULL）。
   **`0.00` + `src='rule'` 比 NULL 危险得多** —— NULL 一眼看得出「没有」，
   这个看着像一个测出来的结果。

教训：**「没跑」和「跑出来是 0」必须在库里长得不一样。** NOT NULL DEFAULT 0 用在
「测量结果」列上就是在制造这种混淆；新增此类列一律可空，让缺席保持可见。

**⚠ 提示词就是判据，写错一句就等于伪造结论。** 本轮三次踩到，代价都是整轮重跑：

1. **不要把结论写进提示词。** `COMMON_RULES` 里曾有一句「看到一件只有名称和一句套话
   简介的东西，就该判低完备度、低可信度」——这是我为了防模型编内容加的，结果它成了
   唯一的锚点：三馆 603 件跑出 `low` 占 95% 以上。**指定答案的提示词得到的不是审计
   结论，是提示词自己的回声。** 更糟的是我据此下过「两个馆独立复现同一形态，说明是
   判据问题不是数据问题」的判断 —— 三个馆读的是同一段提示词，那是共因不是独立验证。
2. **馆专属的事实不要放进通用规则。** 那段 PEM 实情（官方门户停服）被三个阶段、
   所有馆共用，而 MFA 与哈佛的官网都正常。现改为 `MUSEUM_NOTE` 按馆陈述事实、不给结论；
   缺某馆的条目直接报错退出，不许靠猜。
3. **一列一个判据，判据只放在一个地方。** `tier_confidence` / 潜在区间 / `tier_review_flag`
   曾同时由阶段一和阶段二输出，而 `audit_load.py` 让阶段二覆盖阶段一。改判据时只改了
   阶段一，阶段二仍用旧问法 —— 于是三馆 248 件 S/A 的可信度被整片冲成 `low`，
   B/C 段却是新判据。现在阶段二只输出它独有的东西（六问作答、`inference_only_survives`、
   `found_factual_error`），三列一律取阶段一。

**判据本身也有锚点要求，与 `tier_v3.py` 的 0–10 分档同理。** `tier_confidence` 三档必须
写死含义，且**明确禁止由完备度推出**：完备度问「我们知道多少」，可信度问「不知道的那部分
会不会推翻结论」。两条实测有效的补充：① 馆方与学界的既成共识本身就是证据，缺 provenance
或 catalogue raisonné 不构成降信心的理由；② 「还能继续考证」不是理由 —— 任何文物都永远
有可研究的问题，以此为准这一列会对每件都输出 low，从而不携带任何信息。

**Research Needed ≠ 还有东西可以研究，= 缺的那条事实一旦有答案，Tier 可能改变。**
每条缺失证据带 `tier_sensitive`，`tier_review_flag` 由它导出而非独立判断。
**这一条目前只修好了上半段**：S 段需复核率降到 53–83%，但 B/C 段仍是 96–100% ——
判据问「会不会改变 Tier」，而对身份不明的无名小件答案永远是「会」。
缺的是第三条规则：潜在区间整个落在 B/C 内时不进队列（不管查出什么都不改变
「不是本次参观重点」）。**未实现。** 2026-09-06 在 4464 件上再次证实：
**4460/4464 = 99.9% 被标需复核**，一个 100% 饱和的队列不携带任何优先级信息，
等于没有队列。
- 审计自由文本成对存 `xx` / `xx_en` 两列**不走 `content` 表**（审计轨迹逐轮重写，
  灌进内容表既删不掉又要新增 kind）。代价是导出的「零回落」检查照不到它们，
  故 `audit_load.py` 里有中英成对齐全的校验，缺一边拒绝写入。
- 馆级语境（喂给模型、直接决定 IU 与 CR 的判断方向）在 `museum_context.py`，
  `tier_v3.py` 与 `audit_meta.py` 共用。两边各存一份必然分叉，且不报错。

**⚠ PEM 这 196 件里，179 件（91%）无法与 PEM 官方发布的藏品对应上。**
2026-08-31 抓全 18 个栏目页共 219 条官方编目记录后实测：95 件与官方记录**一个显著词
都不重合**，84 件只重合 1 个词（screen/badge 这类巧合），最终只关联上 15 件。
原因在源数据本身 —— 这 196 件的名称是**描述性转写**而非 PEM 编目题名
（「Chinese Export Mandarin Punch Bowl」「Maori War Treasure Jade Mere」），
指不到藏品库里任何一件具体的东西。

**所以这批的低完备度不全是「资料薄」，有很大一部分是「对象身份本身不可核验」。**
这两件事后果完全不同：前者补资料就能解决，后者得先把对象认出来。
往后再看 PEM 的完备度分数、或考虑把管线推广到其余五馆时，先想清楚源数据的名称
到底是不是能指向真实藏品的标识符。

**⚠ 文本列的宽度按中文估的，一上英文就爆。** 两处踩过，都是 4464 件那轮暴露的：
`content_text.text` 原为 `varchar(512)`，英译普遍比中文长，写到第 120 条就
`1406 Data too long`；审计的 `top_missing_en` 等 6 列原为 `varchar(255)`，同因。
两处都已 ALTER 成 `TEXT`（记在 `schema_meta.sql` / `schema_audit.sql`）。
**当时的应急做法是在写入前 `[:512]` 截断 —— 那是错的**，它把「存不下」变成
「静默存了一半」，已删掉。宁可报错。

**⚠ 这两张表不能 DROP 重建，改结构一律走 `schema_audit.sql` 那样的 ALTER。**
2026-08-31 发现 `artwork_meta` 与 `artwork_evidence` 里有仓库脚本复现不出来的数据：
`source_key='pem_official'` 61 条、`'incollect'` 4 条，以及 9 行 `generated_by='rule'`
却带 `best_source_tier=1` —— 都是当初在会话里逐件核实后直接入库的。

`pem_official` 那批**已经补救**：18 个栏目页的抓取原文逐字存进 `pem_official_data.py`，
由 `meta_fill_official_pem.py` 重放，现覆盖 15 件 82 条。`incollect` 那 4 条仍无脚本可复现。
`best_source_tier` 也已改由 `evidence_score.py` 按库里实际存在的来源重算（`LEAST` 只升不降）。

**教训是通用的：抓回来的东西要落进仓库，不能只落进库。** 光入库就等于把最硬的证据
变成孤儿数据，下次连表都不敢重建。同理 `audit_out/` 的 JSONL 与审阅 CSV 要提交
（只忽略日志），因为审计结果重跑一次要 2.5 小时 API。

**10. 每次 LLM 调用都进 `llm_call`，缓存键含提示词全文。**

2026-09-03 复盘：两天约 100 美元，从 JSONL 反推约 1052 次调用，其中约 500 次（≈48%）
是判据改动后作废重跑的。而当时 `ask()` 拿到响应只取 `content`，`resp.usage` 直接丢弃
—— **精确账目事后根本查不出来**。原有的 JSONL 断点续跑挡不住两种花钱方式：
键只有 `seq`，换 `--out-dir` 就全额重付；键里不含提示词，改了判据沿用旧 JSONL 会
**静默返回旧答案**，为安全只能整轮删掉重跑。

现在键是 `sha256(provider|model|effort|system|user|schema)`，一个哈希买到两个性质：
**提示词一字未改必然命中（不花钱），改了必然不命中（拿不到旧判据的答案）。**

- **`model` 与 `effort` 都在键里。** 换型号或换档位 = 对应阶段整批重跑，且新旧两批
  **不可直接比较** —— 跨轮比较时若混了型号或档位，归因不到是「证据变了」还是
  「模型/推理强度变了」。结论里必须标明。
- **失败也留痕**（`status='error'`），但**失败行的 `cache_key` 恒为 NULL** ——
  否则下次同样的提示词会命中一条错误记录，把一次偶发失败永久固化成「答案」。
- **不要为了「把表弄干净」去删 `llm_call` 的行** —— 那是已付费的答案，删掉等于
  把钱扔了。（2026-09-03 清理冒烟数据时就这么丢过一次结果。）
- **本项目只记 token，不折算金额**（`cost_usd` 恒为 NULL，`PRICES` 留空）。
  token 是客观事实，单价会变、会有折扣、会随账户不同；混在一列里日后分不清
  某个数字是真实支出还是某次估算的残留。要临时看金额就填 `PRICES`，可随时回算。
- **`llm_call_item` 用软键 `(museum_key, source_seq)` 关联展品**，多对多。
  `artwork_id` / `museum_id` 是可空的**便利列**，重灌即失效，须跑 `--refresh-ids`；
  视图 `v_artwork_llm_call` 的 `ids_stale` 列直接给出新鲜度判断。
- **校验必须发生在写缓存之前**（`call(validate=...)`）。曾经模型漏返一个 `seq`，
  那条坏答案照样进了缓存 —— 于是重启后**每次都命中同一条坏答案，崩在同一个地方**，
  看起来像「代码没改对」。现在 `validate` 不过就抛 `Invalid` 并重试（默认 2 次），
  连缓存里的旧答案也会重新校验、不过就删掉。三个评分阶段与 slim 审计都传了 `validate`。
- **瞬时错误退避重试**（`_transient()`：连接/超时/限流/5xx，退避 5s、10s）。
  一次 `APIConnectionError` 曾直接打死跑了几小时的审计进程。
- **`claude_cli` 的 token 计量目前是坏的**：库里那几行 `claude-opus-5` 调用
  `prompt_tokens` 记成 4/8/12，显然没接上 CLI 的用量字段。不影响结果，但走
  `claude_cli` 的那部分账目缺一块。**未修。**

**⚠ 分批只是调度，绝不能进入算法。** 把批大小从 500 改成 100 或 1000，
评分结果必须逐字节一致。初版让 `peer_group` 在每批 500 件内各自形成 —— 等于把批大小
混进了判据，CR 的防评分膨胀机制（组内比较）会随分批方式变化，用户 09-05 当场否掉。
现在的分法是：

| 阶段 | 依赖 | 能不能分批 |
|---|---|---|
| 阶段一 HS/IU/VI/VA/CE | 逐件独立 | 可任意分批，随时中断续跑 |
| 阶段二 CR | **须看到同组全部对象** | 必须等阶段一全跑完，按**全馆**分组 |
| 阶段三 S-ness | S 候选 | 同上 |

代价是要等全部跑完才看得到 tier，换来的是结果可复现。`tier_v3.py` 为此加了
`--stage 1|2|3|all` 与 `--seq-from/--seq-to`（后者**只在 `--stage 1` 下允许**，
在阶段二三用会静默破坏分组）。逐阶段推理强度写死在 `STAGE_EFFORT`：
阶段一 `high`、阶段二 `medium`、阶段三 `xhigh`。

**11. `--limit N` 是「跑 N 件」，不是「跑第 N 件」。** 单件复核用 `--only-seq`
（`tier_v3.py` / `audit_meta.py` / `meta_fill_official_mfa.py` 都支持，可重复给）。
2026-09-04 因为写成 `--limit 130` 而多审了 48 件没人要求碰的展品。

---

**译名必须留在 `utils/import_data/translations_*.csv`，不能只改数据库。**
两个导入器都是清空重灌，写在库里的译文重跑一次就没了。

**中文源的馆导出英文版之前必须先跑 `translate_artwork.py`。** 导入器的规矩是
「原文永远保底写入，即使译名表缺这一条」—— 所以**缺译不报错**，只在英文版 Excel 里
整片露出中文。2026-09-06 首次导出 `mfa_boston_ext` 英文版报出 **14893 处** CJK 回落，
两个原因都不在 artwork 表上：

1. **漏了 `gallery.name_cid`** —— 81 个展厅名一段没译，而每件展品都带展厅列，
   一个漏译名称乘以几千行就是上万处。补译要覆盖的不止 artwork。
2. **只查 `e.text IS NULL` 不够** —— 「原文保底写入」会在 `en` 行里塞中文原文，
   看着有英文其实没有。判据必须是 `e.text IS NULL OR e.text REGEXP '[一-鿿]'`，
   这一条又捞出 67 个展品名。

修完重跑，中英两版都是零回落。译文同时写 `content_text` 与译名表两处，缺一不可。

**导出用 `utils/import_data/export_excel.py`**，中英各一套，落在
`utils/import_data/exports/`（已 gitignore，属派生文件）。整跑约 12 分钟，瓶颈是跨公网
读 MySQL（预载 `content_text` 两万余行就占 2.5 分钟），不是计算 —— 看着像卡住其实在等网络。
`--museum pem --artworks-only` 只导一个馆，但预载开销照付，不会按比例变快。
改完导入器务必重跑导出，否则 Excel 里还是旧评级。

展品文件现含 metadata：主表按键加列，另有「metadata明细」sheet 逐条列出取值与来源。
注意 `artwork_meta.source` 是纯 VARCHAR 不走内容表，**「零回落」检查照不到它** ——
英文版曾因此漏出中文，靠 `VALUE_MAPS["meta_source"]` 映射与语种中立的来源串解决。

---

## 工作流程

两个流程。三个工具的行为必须完全一致。

### 开工流程（start-work）

调用：Claude Code `/start-work`，Copilot `/start-work`，Codex `$start-work`，或直接说「开工」。

1. `git pull --ff-only`。失败就**停下来报告**，不要自动 merge 或 rebase —— 拉不动说明有未推送的本地提交或远端分歧，需要人看一眼。
2. 读 `AGENTS.md` 全文（若尚未在上下文中）。
3. 读 `PROGRESS.md` 顶部最近 3 条。
4. 跑 `git log --oneline -10` 和 `git status`，与 PROGRESS 的记载对照，看有没有未被记录的改动。
5. 校验 `.github/copilot-instructions.md` 与 `AGENTS.md` 是否逐字一致（`cmp -s AGENTS.md .github/copilot-instructions.md`）。不一致就报告 —— 说明上次收工没走完。
6. 向用户汇报三句话：项目现状 → 上次做到哪、是哪个工具做的 → 建议的下一步。**然后等用户决定做什么，不要自行开工。**

### 收工流程（end-work）

调用：Claude Code `/end-work`，Copilot `/end-work`，Codex `$end-work`，或直接说「收工」。

> **归档目标不随执行者变化。** 无论由哪个工具执行，写入目标恒定为下列四项。
> 唯一允许的差异在**输入**侧：若当前环境提供持久 memory 目录（目前只有 Claude Code 有），额外把其中的长期事实并入 `AGENTS.md`；没有就只从本次会话提取。**输出恒定不变。**

1. 从本次会话提取：做了什么、下一步、未决问题。
2. 若当前环境有持久 memory 目录，读取其中的 memory 文件，把属于长期事实的内容并入 `AGENTS.md`。没有则跳过。
3. 更新 `AGENTS.md` —— **就地修订，不是追加**。长期事实会被推翻（选型换了、决策改了），必须改写原处，不要越堆越多。
4. 在 `PROGRESS.md` **顶部**插入本次条目，格式见下。
5. 把 `AGENTS.md` 逐字复制到 `.github/copilot-instructions.md`：`cp AGENTS.md .github/copilot-instructions.md`。
6. `git add -A`，按下方格式提交，`git push`。
7. 汇报提交了什么。

若本次会话没有任何实质改动，只汇报，不产生空提交。

### PROGRESS.md 条目格式

新条目插在**文件顶部**（倒序）。这样开工只需读文件头部固定几条，攒到几百条也不会拖慢。

```markdown
## YYYY-MM-DD HH:MM · <工具名>
**做了什么** — …
**下一步** — …
**未决** — …
```

`<工具名>` 取 `claude` / `copilot` / `codex`。

这一栏在接力时能解释痕迹：比如上一棒是 `copilot`，它没有 memory 目录，那么某些判断只会落在 `PROGRESS.md` 里而不在 `AGENTS.md` 里 —— 知道执行者是谁，就知道该去哪找。

### 提交信息格式

```
end-work(<工具名>): <一句话概括本次工作>
```

让工具接力在 `git log` 里直接可见。

---

## 硬性约定

- **`.claude/`、`.agents/`、`.github/` 必须提交进仓库，绝不能加进 `.gitignore`。** 这三个目录装着两个流程在各工具下的入口。一旦被忽略，换台电脑 clone 下来命令就消失了，而且**不会报错**，只是静默地不存在。
- **不要手工编辑 `.github/copilot-instructions.md`。** 改 `AGENTS.md`，由收工流程同步过去。
- **memory 是单向的**：memory 目录 → 仓库。开工流程**不**反向写 memory 目录。仓库是权威源，memory 只是本地缓存；双向同步只会制造重复和冲突。
- **上下文必须随仓库走。** 任何项目上下文都不要只留在会话里，也不要写到仓库外的位置。
- **证书、私钥、密码绝不进仓库。** `.gitignore` 已挡掉 `*.key` `*.pem` `*.crt` `*.zip` 等后缀，但提交前仍要查一遍暂存区。私钥传服务器用管道直写并原子设权限，不在 `/tmp` 留副本。
  **特别注意 `.claude/settings.json`：** 权限系统会把批准过的命令原文写进 allow 列表，命令行里带的密码会跟着落盘，而这个文件按上一条规矩是必须提交的。收工前用 `grep -rl '<密码>' --exclude-dir=.git .` 扫一遍，发现就把那几条 allow 规则删掉。2026-08-26 收工时就是这么处理的。
  **根治办法是不要把密码写进命令行**：服务器上配 `~/.my.cnf`（权限 600），或用 `MYSQL_PASSWORD` 环境变量，命令里就不会出现密码。
- **浏览器的定位、剪贴板等 API 只在安全上下文可用**（HTTPS 或 `localhost`）。公网入口必须是 HTTPS，裸 IP 的 HTTP 一律拿不到定位。

---

## 文件地图

| 文件 | 作用 |
|---|---|
| `AGENTS.md` | 事实源。Codex、Claude Code、VS Code Copilot 自动读取 |
| `.github/copilot-instructions.md` | 上者的逐字副本。**全部** Copilot 界面都自动读取（JetBrains / Visual Studio / Xcode 不读 `AGENTS.md`） |
| `CLAUDE.md` | 一行 import，指向 `AGENTS.md` |
| `PROGRESS.md` | 进展时间线，倒序追加 |
| `docs/SERVER_ENVIRONMENT.md` | 服务器基础环境设计与验收标准 |
| `docs/SERVER_ENVIRONMENT_PLAN.md` | 已执行的服务器环境实施计划 |
| `docs/SERVER_ENVIRONMENT_REPORT.md` | 服务器实际版本、配置、安装过程与验收记录 |
| `docs/WEB_API.md` | web_api 的部署记录：服务、Nginx、证书与验收证据 |
| `docs/Ariadne文化遗产Tier算法V3.0.txt` | Tier 评级算法规格 V3.0：五层评级对象、七维度加权、S-ness Test、VisitScore 与路线生成。七维与 Tier 门槛已在 `tier_v3.py` 实现；第九、十节的 VisitScore 与路线生成**尚未实现**（所需 metadata 全为空） |
| `docs/Metadata Enrichment Pipeline 提案.md` | 证据管道设计：三层 metadata、Completeness、Missing Evidence、来源分级、Research Priority、Evidence Packet。与 V3.0 是「维度定义」与「证据从哪来」的关系，不是替代 |
| `utils/import_data/README.md` | `ari` 库的建表、导入、多语种机制与已知数据问题 |
| `utils/import_data/museum_context.py` | 馆级语境，`tier_v3.py` 与 `audit_meta.py` 共用 |
| `utils/import_data/source_rules.py` | 每个 `source_key` 的来源等级与 FACT/INFERENCE 性质，`evidence_score.py` 与 `audit_load.py` 共用 |
| `utils/import_data/pem_official_data.py` | PEM 官网 18 个栏目页的抓取原文（219 条）+ 14 条人工核实映射 |
| `utils/import_data/meta_fill_rule.py` | 从名称/简介确定性提取 metadata，任意馆通用（原 `meta_fill_pem.py`）。`NAME_ARTIST_PREFIX` 记着各馆名称是不是「作者, 题名」格式 |
| `utils/import_data/meta_scrape.py` | Wikidata 抓取，任意馆通用（原 `meta_scrape_pem.py`）。WDQS 限流时自动改用 QLever 端点 |
| `utils/import_data/meta_fill_official_mfa.py` | 从 `mfa_boston_ext` 的半结构化名称/简介确定性抽 8 个字段，**零 API**。逐段按模式判别，认不出就不写 |
| `utils/import_data/translate_artwork.py` | 给展品名称、**展厅名**与简介补英译，同时写 `content_text` 与译名表。中文源的馆导出英文版前必跑 |
| `utils/import_data/llm_cache.py` | LLM 调用的缓存与计量：`call()` 包住每次请求，`--refresh-ids` 刷新便利列，`python3 llm_cache.py` 出 token 账 |
| `utils/import_data/claude_cli.py` | 通过 `claude` CLI 的 headless 模式调 Anthropic 模型，走订阅账号不需 API key。**不要加 `--bare`**，那样读不到 OAuth |
| `utils/import_data/schema_llm_cache.sql` | `llm_call` / `llm_call_item` / `v_artwork_llm_call` 的建表与 ALTER |
| `.claude/skills/onboard-museum/SKILL.md` 等三份 | 接入新馆的八步清单，含每步的通过判据与踩过的坑 |
| `web_api/README.md` | web_api 的开发说明：本地怎么跑、路由约定 |
| `.claude/skills/*/SKILL.md` | Claude Code 的两个命令入口 |
| `.agents/skills/*/SKILL.md` | Codex 的两个命令入口 |
| `.github/prompts/*.prompt.md` | Copilot 的两个命令入口 |
