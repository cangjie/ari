-- ============================================================================
-- Ariadne Tier 算法 V3.0 评分结果表
-- 算法原文：docs/Ariadne文化遗产Tier算法V3.0.txt
-- 生成脚本：utils/import_data/tier_v3.py
--
-- 【为什么不加在 artwork 表上】
-- import_artworks.py 第 355 行 `DELETE FROM artwork` 清全表，随后
-- `ALTER TABLE artwork AUTO_INCREMENT = 1`。所以：
--   1. 加在 artwork 上的任何列，下一次重灌就全部蒸发；
--   2. artwork.id 每次重新分配，不能作为跨重灌的稳定引用。
-- 而 V3 评分是逐件模型推理的产物，全库 8884 件的重算代价很高，
-- 绝不能设计成「跑一次导入器就没了」。故独立成表。
--
-- 【键的选择】
-- 用 (museum.key_name, artwork.source_seq) 而非 artwork.id：
--   - key_name 来自导入器的 MUSEUMS 配置，是写死的字符串，重灌不变；
--   - source_seq 取源表的 序号/Rank，AGENTS.md 已确认是「馆内唯一能成立的键」；
--   - 已实测六馆全局唯一（8884 行，各馆 source_seq 去重后行数不变）。
--
-- 【故意不建外键】
-- 同 museum.site_key 的处理：artwork 每次重灌都被清空，硬外键 RESTRICT 会让
-- 导入直接失败，CASCADE 会静默删光评分。查询时用
--   JOIN museum m ON m.key_name = v.museum_key
--   JOIN artwork a ON a.museum_id = m.id AND a.source_seq = v.source_seq
--
-- 【评分依据为什么是纯文本而不是内容ID】
-- AGENTS.md 约定「所有展示文本走内容表」。此处三个 *_reason / evidence 字段是
-- **审计轨迹**而非展示文本：它们记录「这个分为什么这么打」，供人工复核算法，
-- 不进任何面向游客的界面，因此不做双语、不进 content 表。
-- 若日后要把评级理由展示给游客，应另建 content 条目，不要直接暴露这几列。
-- ============================================================================

DROP TABLE IF EXISTS artwork_tier_v3;

CREATE TABLE artwork_tier_v3 (
  museum_key       VARCHAR(32)  NOT NULL COMMENT '馆标识，对应 museum.key_name；软链不设外键',
  source_seq       INT UNSIGNED NOT NULL COMMENT '源表序号，对应 artwork.source_seq',

  -- 评级对象层级（V3.0 第二节）。决定用哪套权重，见第四节
  object_type      ENUM('object','node','site') NOT NULL
                   COMMENT 'object=单件展品(ER权重0) / node=建筑或空间节点 / site=遗产地整体',
  peer_group       VARCHAR(128) NOT NULL COMMENT '同类组，CR 的组内比较范围（V3.0 第五节）',

  -- 七个核心维度，0—10（V3.0 第三节）。分档锚点见 tier_v3.py 的 STAGE1_SYSTEM
  hs               DECIMAL(4,2) NOT NULL COMMENT '历史/艺术/遗产重要性',
  iu               DECIMAL(4,2) NOT NULL COMMENT '本馆身份与不可替代性；单件展品权重最高(25%)',
  vi               DECIMAL(4,2) NOT NULL COMMENT '视觉/空间冲击力',
  va               DECIMAL(4,2) NOT NULL COMMENT '游客体验吸引力',
  ce               DECIMAL(4,2) NOT NULL COMMENT '文化/教育/叙事价值',
  er               DECIMAL(4,2) NOT NULL DEFAULT 0
                   COMMENT '整体关系与景观价值；object 恒为 0（权重 0%），仅 node/site 有意义',

  -- CR 的三个分项（V3.0 第五节 CR = 0.5Q + 0.3D + 0.2G）
  q                DECIMAL(4,2) NOT NULL COMMENT '同类中的品质/历史地位/典范程度',
  d                DECIMAL(4,2) NOT NULL COMMENT '相对同类的独特性；必须组内横比，防评分膨胀',
  g                DECIMAL(4,2) NOT NULL COMMENT '对参观路线或文明叙事的补位价值',
  cr               DECIMAL(5,3) NOT NULL COMMENT '类别代表性，由 Q/D/G 算出',

  core             DECIMAL(5,3) NOT NULL
                   COMMENT '加权总分。门槛卡在 8.5/7.2/5.5，实测大量展品差值在千分位，故留三位小数',

  -- 定级结论（V3.0 第六、七节）
  tier             ENUM('S','A','B','C') NOT NULL COMMENT 'V3.0 算出的等级',
  tier_reason      VARCHAR(255) NOT NULL COMMENT '判定说明，含 Core 与降级原因',
  sness_q1         BOOLEAN NULL COMMENT '只有两小时是否仍应安排；仅 S 候选有值',
  sness_q2         BOOLEAN NULL COMMENT '未看到是否明显可惜',
  sness_q3         BOOLEAN NULL COMMENT '若消失本馆身份是否受损',

  -- 数据质量（V3.0 第十二节）
  confidence       ENUM('high','medium','low') NOT NULL
                   COMMENT '证据可信度；low 者不得直接定为正式 S',

  -- 人工修正（V3.0 第八节）。算法明确要求留痕可审，理由不得只写「很有名」
  tier_override    ENUM('S','A','B','C') NULL COMMENT '专家锁定的等级；非空则以此为准',
  override_reason  VARCHAR(512) NULL COMMENT '锁定理由，tier_override 非空时必填',

  -- 审计轨迹，不面向游客，故不进 content 表（见文件头说明）
  evidence         TEXT NULL COMMENT '五维评分依据',
  cr_reason        TEXT NULL COMMENT 'CR 的组内相对位置说明',
  sness_reason     TEXT NULL COMMENT 'S-ness Test 的作答理由',

  algo_version     VARCHAR(16)  NOT NULL DEFAULT 'V3.0' COMMENT '算法版本，便于日后并存多版',
  scored_by        VARCHAR(64)  NOT NULL COMMENT '评分来源，如 claude-opus-5 / human',
  scored_at        DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at       DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
                   ON UPDATE CURRENT_TIMESTAMP(3),

  PRIMARY KEY (museum_key, source_seq),
  KEY idx_v3_tier (museum_key, tier),
  KEY idx_v3_core (core),
  KEY idx_v3_peer (museum_key, peer_group),

  CONSTRAINT ck_v3_dim_range CHECK (
        hs BETWEEN 0 AND 10 AND iu BETWEEN 0 AND 10 AND vi BETWEEN 0 AND 10
    AND va BETWEEN 0 AND 10 AND ce BETWEEN 0 AND 10 AND er BETWEEN 0 AND 10
    AND q  BETWEEN 0 AND 10 AND d  BETWEEN 0 AND 10 AND g  BETWEEN 0 AND 10
    AND cr BETWEEN 0 AND 10 AND core BETWEEN 0 AND 10),
  -- 单件展品的 ER 权重为 0%，给它打分是无意义的，写库前就挡掉
  CONSTRAINT ck_v3_object_er_zero CHECK (object_type <> 'object' OR er = 0),
  -- V3.0 第八节：人工修正必须留痕，不能只锁等级不写理由
  CONSTRAINT ck_v3_override_has_reason CHECK (
    tier_override IS NULL OR (override_reason IS NOT NULL AND override_reason <> ''))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='Ariadne Tier V3.0 评分结果；独立于 artwork 以免被清空重灌抹掉';


-- ----------------------------------------------------------------------------
-- 便于查询的视图：把评分接回 artwork。
-- 注意 JOIN 走 (key_name, source_seq)，不走 artwork.id。
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_artwork_tier_v3 AS
SELECT
  a.id                AS artwork_id,
  m.key_name          AS museum_key,
  a.source_seq,
  a.name_key,
  a.tier              AS tier_in_artwork,
  v.tier              AS tier_v3,
  COALESCE(v.tier_override, v.tier) AS tier_effective,
  v.object_type, v.peer_group,
  v.hs, v.iu, v.vi, v.va, v.ce, v.er,
  v.q, v.d, v.g, v.cr, v.core,
  v.confidence, v.tier_reason, v.tier_override, v.override_reason,
  v.algo_version, v.scored_by, v.scored_at
FROM artwork_tier_v3 v
JOIN museum  m ON m.key_name   = v.museum_key
JOIN artwork a ON a.museum_id  = m.id AND a.source_seq = v.source_seq;
