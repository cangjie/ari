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

`ari` 库现有 12 张表 + 4 个视图：两个源数据集（城市榜单、六馆展品）之外，
另有 V3.0 评级、metadata、evidence、元数据质量审计四套派生数据。
完整说明见 `utils/import_data/README.md`，以下九条是改代码前必须知道的，踩过就知道疼：

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
| 六馆展品 | `import_artworks.py` | `museum_name`、`gallery_*`、`artwork_*` | 1,000,000 起 |
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
导入失败、CASCADE 会静默删光展品；且六个馆里 PEM／哈佛／首博三家根本不在
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
**没有别处藏着更全的版本**。哈佛（204/204）与 PEM（196/196）是填满的。
所以「MFA 用来测世界级名作密度」这件事，在源数据补全前做不了 —— 缺的不是算法。

**⚠ 读源 Excel 生成 `source_seq` 时，必须按「过滤之后」的计数自增。**
`import_artworks.read_museum` 是这么做的，`tier_v3.load_items` 曾用 `enumerate` 的行号
—— 空占位行照样把计数推进，于是 MFA 每一件的分都会张冠李戴，**且不报错**。
PEM 与哈佛没有空行，两种算法碰巧一致，这个 bug 藏到 2026-09-02 才暴露。
新增馆时先查一遍：源表有没有空行、名称列中间有没有混入重复表头。

**6. tier / metadata / evidence / 审计四套数据都放独立表，不加到 `artwork` 上。**

`import_artworks.py` 第 355 行 `DELETE FROM artwork` 清全表并重置 AUTO_INCREMENT。
加在 `artwork` 上的列下次重灌就蒸发，且 `artwork.id` 每次重新分配，不能做跨重灌的引用。
这几张表一律用软键 `(museum.key_name, artwork.source_seq)`，**故意不建到 artwork 的外键**
（硬外键 RESTRICT 会让导入失败，CASCADE 会静默删光）。已实测该键在六馆 8884 行全局唯一。

| 表 | 装什么 | 由谁写 |
|---|---|---|
| `artwork_tier_v3` | V3.0 七维分、Core、S-ness、评分依据 | `tier_v3_load.py` |
| `meta_key` / `artwork_meta` | metadata 键字典与取值（纯 key-value） | `meta_seed*.py` / `meta_fill_rule.py` / `meta_scrape.py` / `meta_fill_official_pem.py` |
| `artwork_evidence` | 完备度、研究优先级、逐维度可信度、缺失证据 | `evidence_score.py` + `evidence_fill.py` |
| `artwork_evidence` 的审计列 | Tier 可信度、潜在 Tier 区间、需复核、研究问题 | `audit_load.py` |

**⚠ 每次跑完 `import_artworks.py`，必须重跑 `tier_v3_load.py --apply-tier`**，
否则 `artwork.tier` 会退回源文件的原表评级。**不报错，只是数据悄悄变回去。**

`artwork_evidence` 现在有**三个**写入者分写不同列，职责必须互斥，`evidence_score.py`
必须用 UPSERT —— 早先它用先删后插，把 `evidence_fill.py` 刚写的可信度与缺失证据
一并冲成 NULL，且不报错。`completeness` 等四列由 `evidence_score.py` 与 `audit_load.py`
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
  两者对照即可看出审计者与打分者是否同源。2026-09-02 起两边都是 `gpt-5.6-sol`
  （本机没有 Anthropic 凭据），**同源偏差这一层保护已经没有了**，结论里要如实标注。

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
「不是本次参观重点」）。**未实现。**
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

---

**译名必须留在 `utils/import_data/translations_*.csv`，不能只改数据库。**
两个导入器都是清空重灌，写在库里的译文重跑一次就没了。

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
| `web_api/README.md` | web_api 的开发说明：本地怎么跑、路由约定 |
| `.claude/skills/*/SKILL.md` | Claude Code 的两个命令入口 |
| `.agents/skills/*/SKILL.md` | Codex 的两个命令入口 |
| `.github/prompts/*.prompt.md` | Copilot 的两个命令入口 |
