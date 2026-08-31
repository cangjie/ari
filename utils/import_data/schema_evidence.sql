-- ============================================================================
-- Evidence Packet：对象级的证据聚合
-- 设计依据：docs/Metadata Enrichment Pipeline 提案.md
--          docs/Ariadne文化遗产Tier算法V3.0.txt 第十二节
--
-- 【与 artwork_meta 的分工】
-- Layer 1（事实）与 Layer 2（significance 证据）都是 key-value，装在 artwork_meta 里，
-- 加字段只是往 meta_key 插行，不动表结构。
-- 本表装的是**对象级聚合值** —— Completeness、Research Priority、逐维度可信度、
-- Missing Evidence —— 它们不是「某个键的取值」，而是对整包证据的评估，
-- 塞进 key-value 会让「一件对象的完备度是多少」变成一次聚合查询，得不偿失。
--
-- 【为什么逐维度记可信度】
-- V3.0 第十二节要求每个维度记录 Evidence Confidence，低可信度对象只能是
-- Preliminary Tier。artwork_tier_v3 只有一个总的 confidence，粒度不够 ——
-- 一件展品完全可能 HS 证据充分而 IU 一无所知，这两种情况该被区别对待。
--
-- 【键仍用 (museum_key, source_seq)】
-- 同 artwork_tier_v3 与 artwork_meta：import_artworks.py 会 DELETE FROM artwork
-- 并重置 AUTO_INCREMENT，artwork.id 不能做跨重灌的引用。故意不建到 artwork 的外键。
-- ============================================================================

DROP TABLE IF EXISTS artwork_evidence;

CREATE TABLE artwork_evidence (
  museum_key      VARCHAR(32)  NOT NULL COMMENT '对应 museum.key_name；软链不设外键',
  source_seq      INT UNSIGNED NOT NULL COMMENT '对应 artwork.source_seq',

  -- 提案第 2 节：0–100 分。两个写入者共用这一列，靠 completeness_src 分辨口径。
  completeness    DECIMAL(5,2) NOT NULL DEFAULT 0
                  COMMENT '证据完备度 0–100。低分的含义不是「它不重要」，而是「我不知道它是否重要」',
  completeness_src ENUM('rule','audit') NOT NULL DEFAULT 'rule'
                  COMMENT 'completeness 的口径与所有权：rule=evidence_score.py 的字段填充率（只看 key 在不在）；audit=audit_meta.py 的适用性感知判定。已审计的行 evidence_score.py 不覆盖',
  completeness_detail TEXT NULL
                  COMMENT '12 项逐项判定，一行一条：项目|full/partial/none/na|一句依据。审计分数必须能被人复算',

  -- 提案第 6 节。原式含 Probability of Tier Change 一项，取决于研究结果本身，
  -- 用它决定要不要研究是循环的；改为下面三项，均可从现有数据直接算出。
  potential_ceiling ENUM('S','A','B','C') NULL
                  COMMENT '现有证据支持的最高可能等级（不是「会变成」，是「最多能到」）',
  boundary_prox   DECIMAL(5,3) NULL
                  COMMENT '当前 Core 距最近 Tier 门槛的距离；越小越该优先研究',
  research_priority DECIMAL(5,2) NOT NULL DEFAULT 0
                  COMMENT 'Potential Ceiling × (1 − Completeness) × ChangeFactor，0–10',

  -- 与上面 artwork_tier_v3.confidence 不是一回事，别混：
  --   那一列 = 打分那一刻，打分者对自己手上证据的可信度
  --   本  列 = 审计者对「当前这个 Tier 结论」的信心
  -- 后者可以在前者很高时仍然很低：证据自洽，但全部来自同一份弱资料。
  -- **low 不等于该降级**，不参与任何自动升降级。
  tier_confidence ENUM('high','medium','low') NULL
                  COMMENT '审计者对「当前 Tier 判断」的信心；low≠该降级，不触发任何自动改级',
  potential_tier_low ENUM('S','A','B','C') NULL
                  COMMENT '潜在 Tier 区间的下界；上界见 potential_ceiling。上下界相同即表示资料已足以钉死这一级',

  tier_review_flag BOOLEAN NOT NULL DEFAULT FALSE
                  COMMENT '需人工复核：证据不足以支撑当前级 / 资料自相矛盾 / 可能被套话高估或被缺料低估',
  review_reason    VARCHAR(512) NULL COMMENT '复核原因（中文）；flag 为真时必填',
  review_reason_en VARCHAR(512) NULL COMMENT '复核原因（英文）',

  -- V3.0 第十二节：逐维度的证据可信度
  conf_hs  ENUM('high','medium','low') NULL COMMENT '历史/艺术/遗产重要性 的证据可信度',
  conf_iu  ENUM('high','medium','low') NULL COMMENT '本馆身份与不可替代性',
  conf_vi  ENUM('high','medium','low') NULL COMMENT '视觉/空间冲击力',
  conf_va  ENUM('high','medium','low') NULL COMMENT '游客体验吸引力',
  conf_ce  ENUM('high','medium','low') NULL COMMENT '文化/教育/叙事价值',
  conf_cr  ENUM('high','medium','low') NULL COMMENT '类别代表性',
  conf_er  ENUM('high','medium','low') NULL COMMENT '整体关系与景观价值；单件展品不适用，留 NULL',

  -- 提案第 3 节：AI 第一轮先回答「缺什么」，而不是急着重新评级。
  -- 「需要更多资料」这种写法等于没写；要具体到「缺该作品在艺术家创作生涯中的位置」。
  missing_evidence    TEXT NULL COMMENT '还缺哪些证据，一行一条；这是 research task 的输入',
  missing_evidence_en TEXT NULL COMMENT 'missing_evidence 的英文版，一行一条',
  top_missing         VARCHAR(255) NULL COMMENT '最关键的那一条缺失证据（中文）',
  top_missing_en      VARCHAR(255) NULL COMMENT '最关键的那一条缺失证据（英文）',
  research_question    VARCHAR(512) NULL COMMENT '建议的研究问题（中文），要可直接执行',
  research_question_en VARCHAR(512) NULL COMMENT '建议的研究问题（英文）',

  -- 审计第五节第 6 问：把全部未经外部资料证实的推断删掉之后，它还站得住吗？
  -- 这是整轮审计里唯一能直接戳破「AI inference 被当作 fact」的检验。
  inference_only_survives BOOLEAN NULL
                  COMMENT '删除全部未经验证的 inference 后，当前 Tier 是否仍成立；仅 S/A 深审填',
  audit_notes     TEXT NULL COMMENT 'S/A 深审六问的逐问作答（中文）',
  audit_notes_en  TEXT NULL COMMENT 'S/A 深审六问的逐问作答（英文）',
  audited_by      VARCHAR(64) NULL COMMENT '审计者：模型型号 / human；与 artwork_tier_v3.scored_by 对照可看出是否同源',
  audit_round     VARCHAR(16) NULL COMMENT '审计轮次标识，如 2026-08-31',
  audited_at      DATETIME(3) NULL,

  -- 提案第 4 节：来源分级。记录本包证据里最高等级的来源。
  -- MySQL 不做相邻字符串字面量的隐式拼接（那是 C/Python 的习惯），COMMENT 必须是单个字符串
  best_source_tier TINYINT UNSIGNED NULL
                  COMMENT '来源分级：1=官方藏品库/UNESCO/国家文物机构；2=展览图录/学术论文/权威考古报告；3=拍卖行/专业艺术数据库；4=Wikipedia及一般网络资料。Tier 4 不足以单独支撑 S',

  is_preliminary  BOOLEAN NOT NULL DEFAULT TRUE
                  COMMENT 'V3.0 第十二节：低可信度对象只能是 Preliminary Tier，不得直接成为正式 S',

  generated_by    VARCHAR(64)  NOT NULL DEFAULT 'manual' COMMENT 'manual / rule / 模型名',
  generated_at    DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at      DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),

  PRIMARY KEY (museum_key, source_seq),
  KEY idx_ev_priority (research_priority DESC),
  KEY idx_ev_completeness (completeness),
  KEY idx_ev_ceiling (museum_key, potential_ceiling),
  KEY idx_ev_review (museum_key, tier_review_flag),
  KEY idx_ev_tierconf (museum_key, tier_confidence),
  CONSTRAINT ck_ev_completeness CHECK (completeness BETWEEN 0 AND 100),
  CONSTRAINT ck_ev_priority CHECK (research_priority BETWEEN 0 AND 10),
  CONSTRAINT ck_ev_source_tier CHECK (best_source_tier IS NULL OR best_source_tier BETWEEN 1 AND 4),
  -- 区间方向不能反：low 不得优于 high。S<A<B<C 的序在 SQL 里没有内建语义，
  -- 用 FIELD 显式钉死比留给应用层检查可靠。
  CONSTRAINT ck_ev_tier_range CHECK (
      potential_tier_low IS NULL OR potential_ceiling IS NULL
      OR FIELD(potential_tier_low,'S','A','B','C')
         >= FIELD(potential_ceiling,'S','A','B','C')),
  -- flag 为真却说不出原因，等于没标
  CONSTRAINT ck_ev_review_reason CHECK (
      tier_review_flag = FALSE OR review_reason IS NOT NULL)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='Evidence Packet 的对象级聚合：完备度、研究优先级、逐维度可信度、缺失证据';
