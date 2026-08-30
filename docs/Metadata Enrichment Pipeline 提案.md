# Metadata Enrichment Pipeline 提案

> 来源：ChatGPT 对话「完善评级介绍」，2026-08-30 由用户粘贴引入。
> 原分享链接 `https://chatgpt.com/s/t_6a91922c104c819181c78f482aa5d60a`
> 对非浏览器请求返回 403（Cloudflare + 客户端渲染），无法程序化抓取，故此处为用户手工转录。
>
> 本文是**设计输入**，与 `Ariadne文化遗产Tier算法V3.0.txt` 并列。
> 二者关系：V3.0 定义七维度与 Tier 门槛；本文提出这些维度的**证据从哪来**。
> 截至 2026-08-30 均未在代码或库中实现。

---

核心主张：不要靠人工把每条 description 越写越长来解决评级依据不足的问题。
覆盖几百家博物馆、几十万件对象时那样不可扩展。应当把它变成一条
Metadata Enrichment Pipeline。V3.0 已经给了很好的基础：每个维度要有评分依据
和来源、记录 Evidence Confidence、低可信度对象只能是 Preliminary Tier。

## 1. 先把 Description 和 Metadata 分开

最容易出现的问题是把所有信息都塞进一段 description。建议数据库分三层：

**Layer 1 — Basic Metadata（事实字段）**
Object Name / Maker / Culture / Date / Dynasty / Material / Dimensions /
Place of Origin / Provenance / Acquisition / Gallery / Object ID。
尽可能直接来自博物馆官方数据库，不让 AI「创作」。

**Layer 2 — Significance Metadata（最关键）**
这是算法真正缺的东西：
Historical Significance、Art Historical Significance、Rarity / Uniqueness、
Institutional Significance、Category Importance、Cultural Context、
Provenance Significance、Visual / Experiential Features、
Relationships to other objects/site。
这部分才是 Tier algorithm 真正需要「读」的资料。

**Layer 3 — Visitor Description**
最后才由 AI 根据前两层生成：150 字普通游客介绍、300 字深度介绍、儿童版、
中文版、audio guide。**Description 成为 output，而不是评分的主要 input。**

## 2. 建一个 Metadata Completeness Score

每个对象先自动检查：

| 信息 | 权重 |
|---|---|
| 基本身份/年代/作者 | 10% |
| Historical significance | 15% |
| Art/Cultural significance | 15% |
| Rarity | 15% |
| Provenance | 10% |
| Institutional significance | 15% |
| Category context | 10% |
| Visitor/visual significance | 10% |

于是每件得到 `Metadata Completeness = 82/100`，而不是简单判断「description 有/没有」。
若只有「Bowl, China, Qing Dynasty, porcelain.」可能只有 20/100。
算法看到 20/100 就知道：**不是它不重要，而是我不知道它是否重要。**

## 3. 最关键的一步：让 AI 主动寻找「缺什么」

例如：某尊辽代菩萨，Current Tier B，Metadata completeness 38%，
HS confidence Low，IU confidence Low。

AI 第一轮不要急着重新评级，而是生成 **Missing Evidence**：

- 是否属于本馆最重要的辽代雕塑？
- 是否有明确寺院/考古来源？
- 是否被重要学术出版物讨论？
- 是否属于罕见类型？
- 本馆是否将其列为 collection highlight？
- 同类作品在 Met / MFA / British Museum 等机构中的地位如何？

这就把「完善 description」变成了一个 research task。

## 4. 建立 Source Hierarchy

不是网上找到什么就用什么。资料来源分级：

- **Tier 1**：博物馆官方 object page / collection database；UNESCO；国家文物机构；官方 catalogue
- **Tier 2**：museum exhibition catalogue、学术论文、Oxford/Grove、大学数据库、权威考古报告
- **Tier 3**：重要拍卖行、专业艺术数据库、可靠文化机构
- **Tier 4**：Wikipedia 及普通网络资料 —— 用于发现线索，不应该单独支撑 S Tier

V3.0 规定 UNESCO 身份本身不直接产生 S、只作为 HS/IU/ER 的 evidence，这个原则很好。

## 5. 不需要平等研究所有展品

最能节省成本的地方。假设一馆有 10,000 件：

    10,000 → Candidate Screening（用现有 metadata 找 Potential S/A + Low Confidence）
       400 → Metadata Enrichment
       150 → 进入 S/A

资源集中在 **Tier boundary** 上。尤其优先调查
「Preliminary B，但可能因资料不足实际上是 A/S」的对象 —— 这种 research ROI 最大。

## 6. 增加 Research Priority Score

    Research Priority = Potential Importance × Missing Information × Probability of Tier Change

于是 `Current B / Potential S / Confidence Low → 9.5`，
而 `Current C / Potential C / Confidence High → 0.5`。
Ariadne 由此自动产生工作队列：今天最值得 research 的 100 件是什么。
从人工数据库维护变成半自动系统。

## 7. 建筑、遗址、景观需要另一套 metadata schema

颐和园不能用 Artist / Material / Dimensions 来描述。除 V3.0 已列出的
Spatial Relationship、Visual Corridor、Processional Sequence、
Human–Nature Integration、Integrity、Authenticity、Setting 之外，还应加：

Construction / Transformation History、Function、Symbolic Meaning、
Best Viewpoint、Best Sequence of Approach、Relationship to Parent Site。

这样佛香阁、昆明湖、十七孔桥、长廊才能与 museum objects 一同进入 Ariadne，
又不必硬套艺术品字段。

## 8. 每件对象应形成一个 Evidence Packet

以荫余堂为例，后台不是只有一段 description，而是：

    Basic Facts        年代、徽州来源、迁建 PEM 时间……
    Historical Significance    为什么重要
    Institutional Significance 为什么对 PEM 特别重要
    Uniqueness         为什么不可替代
    Visitor Experience  为什么现场体验突出
    Category Context    和 PEM 其他中国建筑/中国艺术相比
    Sources            PEM 官方资料 / catalogue / scholarly sources
    Confidence         HS: High / IU: Very High / VI: High / CE: High
    Missing Evidence   None / minor

然后由模型依据这个 Evidence Packet 打七维分数。这比让 AI 读一篇 500 字
description 然后「凭感觉打 8.7 分」可靠很多。

## 建议的下一步实验

先不改 PEM 的 description 文字。拿现有 196 项做实验：给每项增加约 10–15 个
结构化 metadata/evidence 字段 + Completeness + Confidence + Missing Evidence
+ Research Priority，然后看哪些从 B 变 A、哪些 A 变 S、哪些不变。

这样能很快知道：**到底是算法的问题，还是 metadata 的问题。**

实验成功后，这套 pipeline 才能规模化到故宫、国博、MFA、婆罗浮屠乃至以后
几千个目的地。
