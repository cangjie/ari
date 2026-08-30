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

  -- 提案第 2 节：八个权重桶算出的 0–100 分
  completeness    DECIMAL(5,2) NOT NULL DEFAULT 0
                  COMMENT '证据完备度 0–100。低分的含义不是「它不重要」，而是「我不知道它是否重要」',

  -- 提案第 6 节。原式含 Probability of Tier Change 一项，取决于研究结果本身，
  -- 用它决定要不要研究是循环的；改为下面三项，均可从现有数据直接算出。
  potential_ceiling ENUM('S','A','B','C') NULL
                  COMMENT '现有证据支持的最高可能等级（不是「会变成」，是「最多能到」）',
  boundary_prox   DECIMAL(5,3) NULL
                  COMMENT '当前 Core 距最近 Tier 门槛的距离；越小越该优先研究',
  research_priority DECIMAL(5,2) NOT NULL DEFAULT 0
                  COMMENT 'Potential Ceiling × (1 − Completeness) × BoundaryProximity，0–10',

  -- V3.0 第十二节：逐维度的证据可信度
  conf_hs  ENUM('high','medium','low') NULL COMMENT '历史/艺术/遗产重要性 的证据可信度',
  conf_iu  ENUM('high','medium','low') NULL COMMENT '本馆身份与不可替代性',
  conf_vi  ENUM('high','medium','low') NULL COMMENT '视觉/空间冲击力',
  conf_va  ENUM('high','medium','low') NULL COMMENT '游客体验吸引力',
  conf_ce  ENUM('high','medium','low') NULL COMMENT '文化/教育/叙事价值',
  conf_cr  ENUM('high','medium','low') NULL COMMENT '类别代表性',
  conf_er  ENUM('high','medium','low') NULL COMMENT '整体关系与景观价值；单件展品不适用，留 NULL',

  -- 提案第 3 节：AI 第一轮先回答「缺什么」，而不是急着重新评级
  missing_evidence TEXT NULL COMMENT '还缺哪些证据，一行一条；这是 research task 的输入',

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
  CONSTRAINT ck_ev_completeness CHECK (completeness BETWEEN 0 AND 100),
  CONSTRAINT ck_ev_priority CHECK (research_priority BETWEEN 0 AND 10),
  CONSTRAINT ck_ev_source_tier CHECK (best_source_tier IS NULL OR best_source_tier BETWEEN 1 AND 4)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='Evidence Packet 的对象级聚合：完备度、研究优先级、逐维度可信度、缺失证据';
