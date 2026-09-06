-- ============================================================================
-- 展品 metadata：纯 key-value，键与值都多语种
--
-- 【为什么没有模版 / 分类】
-- 曾按「陶瓷/书画/青铜器」建过一套模版，实测对不上账：波士顿三馆 602 件里
-- 456 件（76%）无处可归 —— Oil Painting 就有 149 件，油画要的是画派、签名、
-- 原框，跟「书画编目」的装裱、题跋是两回事。更要命的是中文三馆 8281 件
-- （全库 93%）连门类字段都没有，模版根本挂不上去。故取消模版层：
-- 每件展品收集若干 key-value，用到什么记什么，不预设它属于哪一类。
--
-- 【键和值都进 content / content_text】
-- AGENTS.md 数据库约定第 1 条。键「年代」和值「清」各是一段内容，各占一个
-- content 行、两条 content_text（zh-CN / en）。加语种只是多插行，不动表结构。
-- 去重是真去重：「清」被几百件展品共用，也只占一行。
--
-- 【键为什么还要 key_name，不能只有 key_cid】
-- AGENTS.md 第 2 条：内容ID只能保证「ID不重复」，保证不了「文本不重复」。
-- 没有 key_name 的话，「年代」很容易被写成两个 content 行，程序按键取值时
-- 就会漏。meta_key 这张小字典表把「一个规范键名 <-> 一段多语种显示名」钉死，
-- 唯一约束落在 key_name 上。
-- **它不是模版**：不规定哪些展品该有哪些键，不校验，不分组。
--
-- 【键用 (museum_key, source_seq)，不用 artwork.id】
-- import_artworks.py 会 `DELETE FROM artwork` 清全表并重置 AUTO_INCREMENT，
-- artwork.id 每次重灌都重新分配。同理故意不建到 artwork 的外键 ——
-- 硬外键 RESTRICT 会让导入失败，CASCADE 会静默删光 metadata。
--
-- 【content 的 ID 分段】（AGENTS.md 第 3 条）
--   import_data.py      city_name…data_source   ID 0 段（1–999,999）
--   import_artworks.py  museum_name…artwork_*   ID 1,000,000 段
--   本数据集             meta_key_name / meta_value_text   ID 2,000,000 段
-- 两个既有导入器的 CONTENT_KINDS 都不含 meta_*，重灌不会碰这里。
-- ============================================================================

-- content.kind 是固定 ENUM，新 kind 必须先加进去，否则插入被静默截断
-- （MySQL 报 1265 Data truncated，不是「未知取值」，第一次撞上很容易误判）。
-- 从零建库时 schema.sql 的 ENUM 已含这两种，本 ALTER 只为给已建好的库补种。
ALTER TABLE content MODIFY COLUMN kind
  ENUM('city_name','country_name','site_name','tier_reason',
       'change_reason','collection_type','data_source',
       'museum_name','gallery_name','gallery_theme',
       'artwork_name','artwork_description','artwork_medium','artwork_tier_reason',
       'meta_key_name','meta_value_text')
  NOT NULL COMMENT '内容归类：既便于按类清点未译项，也界定各导入器各自的清空范围';

DROP TABLE IF EXISTS artwork_meta;
DROP TABLE IF EXISTS meta_key;

-- ---------------------------------------------------------------- 键字典
CREATE TABLE meta_key (
  key_name    VARCHAR(64)  NOT NULL COMMENT '规范键名，程序用，从不展示；如 period / artist',
  name_cid    INT UNSIGNED NOT NULL COMMENT '键的多语种显示名 -> content.id (kind=meta_key_name)',
  note        VARCHAR(255) NULL COMMENT '给录入者看的说明，如取值口径、单位；纯备注不做约束',
  sort_order  SMALLINT     NOT NULL DEFAULT 0 COMMENT '展示顺序',
  created_at  DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (key_name),
  UNIQUE KEY uk_meta_key_cid (name_cid),
  CONSTRAINT fk_meta_key_name FOREIGN KEY (name_cid) REFERENCES content (id)
    ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='metadata 键字典：规范键名 <-> 多语种显示名。不是模版，不规定谁该有哪些键';

-- ---------------------------------------------------------------- 取值
CREATE TABLE artwork_meta (
  museum_key  VARCHAR(32)  NOT NULL COMMENT '对应 museum.key_name；软链不设外键，见文件头',
  source_seq  INT UNSIGNED NOT NULL COMMENT '对应 artwork.source_seq',
  key_name    VARCHAR(64)  NOT NULL COMMENT '对应 meta_key.key_name',
  -- 来源进主键，是为了让同一个键的多个来源共存。抓取来的数据彼此矛盾是常态：
  -- 源文件说「pre-contact」而 Wikidata 标 1825 年，这种冲突本身就是有用信息，
  -- 不该由写入方挑一个赢家。谁对谁错留给读取方按 source_key + confidence 判断。
  source_key  VARCHAR(32)  NOT NULL COMMENT
              '来源标识：source_file / rule / wikidata / pem_customprints / wikipedia / manual',
  ord         SMALLINT UNSIGNED NOT NULL DEFAULT 0
              COMMENT '同一来源下、同一个键的第几个值。材质可能是「木」「漆」「金」三条，各占一行',

  value_cid   INT UNSIGNED NOT NULL COMMENT '值的多语种文本 -> content.id (kind=meta_value_text)',
  -- 值以 content_text 为准；这一列只是「值本身就是数字」时的可计算冗余。
  -- 加它是因为 V3.0 第九、十节的 VisitScore 与 RouteUtility 要拿观看时长、
  -- 门槛 G、修正量 Ma/Mc/Mr 直接参与运算，从多语种文本里反解数字既慢又脆。
  -- 非数字的键留 NULL。两者不一致时以 content_text 为准，本列可随时重算。
  value_num   DECIMAL(12,3) NULL COMMENT '数值型取值的冗余副本，仅供计算与排序',

  -- V3.0 第十二节：每条都要能追到来源，并记录证据可信度
  source      VARCHAR(255) NULL COMMENT '来源：官网URL / 名称解析 / 源文件字段 / 人工录入',
  confidence  ENUM('high','medium','low') NOT NULL DEFAULT 'medium',
  -- 提案第 3、4 节：每条取值都要说清「这是外部事实还是我们的推断」，以及来源有多硬。
  -- confidence 回答不了这个问题 —— 一条 AI 推断可以「很有信心」，那与「有馆方
  -- 官网背书」是两码事。混在一起，导出表里就分不出哪句有外部资料撑着。
  -- 存量库补种见 schema_audit.sql。
  evidence_type  ENUM('FACT','INFERENCE') NULL COMMENT
              'FACT=有外部资料直接支撑；INFERENCE=Ariadne/AI 依据事实作出的判断。推断可用于定级，但不得冒充馆方或学术来源',
  source_quality ENUM('strong','moderate','weak') NULL COMMENT
              '提案第 4 节来源分级：strong=Tier1-2 馆方官方/UNESCO/学术出版；moderate=Tier3 专业数据库/拍卖行；weak=Tier4 一般网络资料，或仅有原 description 与 AI 推断支撑',
  filled_by   VARCHAR(64)  NOT NULL DEFAULT 'manual' COMMENT 'manual / rule / 模型名',
  created_at  DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at  DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),

  PRIMARY KEY (museum_key, source_seq, key_name, source_key, ord),
  KEY idx_am_key (key_name),
  KEY idx_am_source (source_key, key_name),
  KEY idx_am_value (value_cid),
  KEY idx_am_num (key_name, value_num),
  KEY idx_am_etype (museum_key, evidence_type, source_quality),
  CONSTRAINT fk_am_key FOREIGN KEY (key_name) REFERENCES meta_key (key_name)
    ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_am_value FOREIGN KEY (value_cid) REFERENCES content (id)
    ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='展品 metadata 取值；键与值均为多语种内容ID';

-- ----------------------------------------------------------------------------
-- 便于查询的视图：展品 / 键 / 值，按语种摊平。
-- JOIN artwork 走 (key_name, source_seq)，不走 artwork.id。
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_artwork_meta AS
SELECT
  a.id            AS artwork_id,
  am.museum_key,
  am.source_seq,
  am.key_name,
  am.ord,
  kt.lang,
  kt.text         AS key_label,
  vt.text         AS value_text,
  am.value_num,
  am.source, am.confidence, am.evidence_type, am.source_quality,
  am.filled_by, am.updated_at
FROM artwork_meta am
JOIN meta_key  mk ON mk.key_name  = am.key_name
JOIN content_text kt ON kt.content_id = mk.name_cid
JOIN content_text vt ON vt.content_id = am.value_cid AND vt.lang = kt.lang
JOIN museum  m ON m.key_name  = am.museum_key
JOIN artwork a ON a.museum_id = m.id AND a.source_seq = am.source_seq;

-- ============================================================================
-- 2026-09-06：content_text.text 由 VARCHAR(512) 改为 TEXT
--
-- 原列宽是按中文实测定的（注释写着「实测最长 116 字符」）。中文信息密度高，
-- 512 字符绰绰有余；但**英译同样内容通常是 2–3 倍字符数**，
-- mfa_boston_ext 的展品简介译成英文后直接撑爆：
--   DataError (1406): Data too long for column 'text' at row 1
-- 而这一撞让补译进程整个退出，名称译完了、简介只译了 4 批。
--
-- 中文塞得进 512 是信息密度带来的巧合，不是这一列的固有上限 ——
-- 只要加英译（或任何拉丁语系语种），这个上限迟早会撞上。故改 TEXT。
--
-- 索引不用动：idx_ct_lang_text 本来就是 (lang, text(64)) 前缀索引。
-- ============================================================================

ALTER TABLE content_text
  MODIFY COLUMN text TEXT NOT NULL
  COMMENT '该语种下的文本。中文多在百字内，但英译通常是中文的 2–3 倍字符数，故用 TEXT 不用 VARCHAR';
