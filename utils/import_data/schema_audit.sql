-- ============================================================================
-- Metadata Quality Audit：给 artwork_evidence 与 artwork_meta 补审计列
--
-- 设计依据：docs/Metadata Enrichment Pipeline 提案.md 第 2、3、4、6 节
--          docs/Ariadne文化遗产Tier算法V3.0.txt 第十二节
--
-- 【审计要回答什么】
-- 不是「这件东西该是几级」，而是「支撑它现在这一级的资料够不够」。所以本轮
-- 一列 tier 都不写：artwork.tier、artwork_tier_v3.tier / tier_override 全都不碰，
-- audit_load.py 里有写入前后的快照断言强制这一点。
--
-- 【为什么是 ALTER 而不是 DROP+CREATE】
-- schema_evidence.sql / schema_meta.sql 本来是 DROP+CREATE 的路子，因为表里的数据
-- 都能由仓库里的脚本重新生成。**2026-08-31 实测发现这个前提已经不成立**：
--   · artwork_meta 里有 source_key='pem_official' 61 条、'incollect' 4 条，
--     仓库里没有任何脚本会写它们（当初是在会话里逐件核实后直接入库的）
--   · artwork_evidence 里有 9 行 generated_by='rule' 却带 best_source_tier=1，
--     evidence_data_pem.py 复现不出来（它只有 11×4 / 1×3 / 1×1）
-- 重建这两张表会静默丢掉这批人工核实过的、来源等级最高的证据。故改用 ALTER。
-- 上面两个文件的 CREATE 也同步加了这些列，供从零建库时对齐。
--
-- 【只跑一次】
-- MySQL 8.4 没有 ADD COLUMN IF NOT EXISTS（那是 MariaDB）。重复执行会报
-- 1060 Duplicate column name，这是预期行为，不是出错 —— 说明已经加过了。
-- ============================================================================

-- ---------------------------------------------------------------- 对象级审计
ALTER TABLE artwork_evidence
  -- completeness 由两个写入者共用，必须能分辨当前这个数字是谁算的。
  -- rule  = evidence_score.py 的字段填充率（只看 key 在不在，不看取值质量，
  --         不认「不适用」）。PEM 实测中位 1.1/100 —— 它量的是填充率不是完备度。
  -- audit = audit_meta.py 的适用性感知判定（12 项逐项 full/partial/none/na，
  --         na 项从分母剔除后归一化）。已审计的行 evidence_score.py 不再覆盖。
  ADD COLUMN completeness_src ENUM('rule','audit') NOT NULL DEFAULT 'rule'
      COMMENT 'completeness 这个数字的口径与所有权：rule=字段填充率；audit=审计判定'
      AFTER completeness,

  -- 审计分数必须能被人复算，否则它只是另一个不可质疑的黑箱数字。
  ADD COLUMN completeness_detail TEXT NULL
      COMMENT '12 项逐项判定，一行一条：项目|full/partial/none/na|一句依据'
      AFTER completeness_src,

  -- 与 artwork_tier_v3.confidence 是两回事，别混：
  --   artwork_tier_v3.confidence = 打分那一刻，打分者对自己手上证据的可信度
  --   本列                        = 审计者对「当前这个 Tier 结论」的信心
  -- 后者可以在前者很高时仍然很低：证据本身自洽，但全部来自同一份弱资料。
  -- **low 不等于该降级。** 允许出现 Preliminary S — Low Confidence，
  -- 也允许 B — High Confidence。本列不参与任何自动升降级。
  ADD COLUMN tier_confidence ENUM('high','medium','low') NULL
      COMMENT '审计者对「当前 Tier 判断」的信心；low≠该降级，不触发任何自动改级'
      AFTER research_priority,

  -- Potential Tier Range 的下界。上界复用已有的 potential_ceiling。
  -- 上下界相同（如 A–A）表示现有资料已足以钉死这一级。
  ADD COLUMN potential_tier_low ENUM('S','A','B','C') NULL
      COMMENT '潜在 Tier 区间的下界；上界见 potential_ceiling。相同即表示资料已充分'
      AFTER tier_confidence,

  -- 提案第 3 节：第一轮先标出「该复核」，而不是直接改级。
  ADD COLUMN tier_review_flag BOOLEAN NOT NULL DEFAULT FALSE
      COMMENT '需人工复核：证据不足以支撑当前级 / 资料自相矛盾 / 可能被套话高估或被缺料低估',
  ADD COLUMN review_reason    VARCHAR(512) NULL COMMENT '复核原因（中文）；flag 为真时必填',
  ADD COLUMN review_reason_en VARCHAR(512) NULL COMMENT '复核原因（英文）',

  -- 现有 missing_evidence 是中文单语。审计文本一律成对存列，理由见文件末注释。
  ADD COLUMN missing_evidence_en TEXT NULL COMMENT 'missing_evidence 的英文版，一行一条',
  ADD COLUMN top_missing        VARCHAR(255) NULL COMMENT '最关键的那一条缺失证据（中文）',
  ADD COLUMN top_missing_en     VARCHAR(255) NULL COMMENT '最关键的那一条缺失证据（英文）',
  ADD COLUMN research_question    VARCHAR(512) NULL COMMENT '建议的研究问题（中文），要可直接执行',
  ADD COLUMN research_question_en VARCHAR(512) NULL COMMENT '建议的研究问题（英文）',

  -- 第五节第 6 问：把全部未经外部资料证实的推断删掉之后，它还站得住吗？
  -- 这一问是整轮审计里唯一能直接戳破「AI inference 被当作 fact」的检验。
  ADD COLUMN inference_only_survives BOOLEAN NULL
      COMMENT '删除全部未经验证的 inference 后，当前 Tier 是否仍成立；仅 S/A 深审填',
  ADD COLUMN audit_notes    TEXT NULL COMMENT 'S/A 深审六问的逐问作答（中文）',
  ADD COLUMN audit_notes_en TEXT NULL COMMENT 'S/A 深审六问的逐问作答（英文）',

  ADD COLUMN audited_by  VARCHAR(64) NULL COMMENT '审计者：模型型号 / human；与 scored_by 对照可看出是否同源',
  ADD COLUMN audit_round VARCHAR(16) NULL COMMENT '审计轮次标识，如 2026-08-31',
  ADD COLUMN audited_at  DATETIME(3) NULL,

  -- 区间方向不能反：low 不得优于 high。S<A<B<C 的序在 SQL 里没有内建语义，
  -- 只能显式枚举 —— 12 对合法组合，写死比留给应用层检查可靠。
  ADD CONSTRAINT ck_ev_tier_range CHECK (
      potential_tier_low IS NULL OR potential_ceiling IS NULL
      OR FIELD(potential_tier_low,'S','A','B','C')
         >= FIELD(potential_ceiling,'S','A','B','C')),
  -- flag 为真却说不出原因，等于没标。
  ADD CONSTRAINT ck_ev_review_reason CHECK (
      tier_review_flag = FALSE OR review_reason IS NOT NULL);

CREATE INDEX idx_ev_review    ON artwork_evidence (museum_key, tier_review_flag);
CREATE INDEX idx_ev_tierconf  ON artwork_evidence (museum_key, tier_confidence);

-- ---------------------------------------------------------------- 逐条 claim
-- 提案第 3、4 节：每一条 metadata 取值都要说清「这是外部事实，还是我们的推断」。
--
-- 现状是两者混在一起：source_key='evidence' 的 117 条 sig_* 全是模型依据描述
-- 作出的判断，却和源文件里的 Category 值共用同一套 confidence 语义。导出到
-- Excel 之后，读表的人无从分辨哪句有外部资料撑着、哪句只是 Ariadne 自己的看法。
-- 这正是「inference 伪装成 fact」的结构性入口，加这两列就是为了堵死它。
ALTER TABLE artwork_meta
  ADD COLUMN evidence_type ENUM('FACT','INFERENCE') NULL
      COMMENT 'FACT=有外部资料直接支撑；INFERENCE=Ariadne/AI 依据事实作出的判断。推断可用于定级，但不得冒充馆方或学术来源'
      AFTER confidence,
  ADD COLUMN source_quality ENUM('strong','moderate','weak') NULL
      COMMENT '提案第 4 节来源分级：strong=Tier1-2 馆方官方/UNESCO/学术出版；moderate=Tier3 专业数据库/拍卖行；weak=Tier4 一般网络资料，或仅有原 description 与 AI 推断支撑'
      AFTER evidence_type;

CREATE INDEX idx_am_etype ON artwork_meta (museum_key, evidence_type, source_quality);

-- ============================================================================
-- 【审计文本为什么成对存列，不走 content / content_text】
--
-- AGENTS.md 第 1 条要求所有展示文本走内容表。这批文本是**审计轨迹不是展示文本**：
--   · 每轮审计整体重写，走内容表就得每轮往 content 里灌几百段一次性内容，
--     且删不掉（content 被外键 RESTRICT 挡着）
--   · 它们不属于任何一个既有 kind，新增 kind 又要同时改三处（schema.sql 的 ENUM、
--     补种 ALTER、写入者常量），代价远大于收益
-- 代价是 export_excel.py 的「零回落」检查照不到这些列 —— 与 artwork_meta.source
-- 同类问题，英文版曾因此漏出中文。故审计脚本必须中英同时产出，
-- audit_load.py 里有成对齐全的校验，缺一边直接拒绝写入。
-- ============================================================================
