-- ============================================================================
-- LLM 调用缓存与计量表
-- 写入者：llm_cache.py（被 tier_v3.py 与 audit_meta.py 的 ask() 包住）
--
-- 【为什么要有这张表】
-- 2026-09-03 复盘：两天烧掉约 100 美元，从留下的 JSONL 反推约 1052 次调用，
-- 其中约 500 次（≈48%）是判据改动后作废重跑的。而 ask() 拿到响应只取
-- message.content，resp.usage 直接丢弃 —— 全仓库 grep usage 零命中，
-- **精确账目事后根本查不出来**，只能靠数 JSONL 行数倒推。
--
-- 原有的 JSONL 断点续跑挡不住这两种花钱方式：
--   1. 缓存键只有 seq，换 --out-dir 就等于全额重新付费
--      （tier_v3_out → tier_v3_out_ev → run2/tier_*，每换一次全付一遍）；
--   2. 键里不含提示词，所以改了判据后沿用旧 JSONL 会**静默返回旧答案**
--      （「改了阶段一没改阶段二」正是这个形态），为安全只能整轮删掉重跑。
--
-- 本表把键改成 sha256(provider|model|effort|system|user|schema)：
--   · 改评分阶段二的提示词 → 阶段一的 key 未变 → 只有阶段二重跑；
--   · 换 out-dir / 换机器 → 无影响，照样命中；
--   · 旧提示词的答案**不可能**被静默复用，因为 key 必然不同；
--   · 每一轮花在哪个阶段的钱可以直接 SQL 查出来。
--
-- 【为什么不进 content 表】
-- 同 artwork_tier_v3 的 evidence/cr_reason：这是**审计轨迹**不是展示文本，
-- 不做双语、不面向游客。而且它逐轮追加、体量远大于内容表能承受的规模。
--
-- 【为什么不建外键】
-- museum_key 同 artwork_tier_v3 的处理：import_artworks.py 每次重灌都清空
-- artwork，硬外键 RESTRICT 会让导入失败、CASCADE 会静默删光缓存 ——
-- 而缓存被删掉就意味着下次重跑要重新付钱，正是本表要避免的事。
--
-- 【这张表不能 DROP 重建】
-- 同 artwork_meta / artwork_evidence 的教训（AGENTS.md）：表里装的是真金白银
-- 换来的答案，重建一次就等于把已付费的结果扔掉。改结构一律走 ALTER。
-- ============================================================================

CREATE TABLE IF NOT EXISTS llm_call (
  id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,

  -- 缓存键：sha256(provider|model|effort|system|user|schema_json)。
  -- **允许 NULL** —— MySQL 的 UNIQUE 容忍多个 NULL，回填的历史记录走这条路：
  -- 它们没有留下 prompt 原文，重建出来的未必是当初那一段，假命中比不命中危险，
  -- 所以给 NULL，永不参与命中，只作账目与答案的归档。
  cache_key      CHAR(64)     NULL COMMENT 'sha256(provider|model|effort|system|user|schema)；NULL=历史回填，不参与命中',

  provider       VARCHAR(16)  NOT NULL COMMENT 'openai / anthropic',
  model          VARCHAR(64)  NOT NULL COMMENT '型号原文，如 gpt-5.6-sol',
  effort         VARCHAR(16)  NULL     COMMENT 'reasoning_effort；未显式指定时为 NULL',

  -- 归属：用来分组算账，也用来在改判据后精确定位要作废哪一批
  stage          VARCHAR(32)  NOT NULL COMMENT 'tier_stage1/2/3、audit_stage1/2/3、official_zh 等',
  museum_key     VARCHAR(32)  NULL     COMMENT '馆标识；与馆无关的调用（如翻译）为 NULL',
  scope          VARCHAR(255) NULL     COMMENT '本次调用覆盖的范围，如 "seq 1-12" 或 peer group 名',
  prompt_version VARCHAR(32)  NULL     COMMENT '判据版本号，人工标注；便于日后按版本作废',

  -- 问与答的原文。**存全文而不是哈希** —— 事后要复核「当时到底问了什么」，
  -- 只存哈希就等于又回到了「答案是孤儿数据」的老路。
  system_text    MEDIUMTEXT   NOT NULL COMMENT 'system 提示词原文',
  user_text      MEDIUMTEXT   NOT NULL COMMENT 'user 提示词原文',
  schema_sha     CHAR(64)     NOT NULL COMMENT '结构化输出 schema 的 sha256',
  response_json  MEDIUMTEXT   NOT NULL COMMENT '模型返回的 JSON 原文',

  -- 计量。**型号不在 llm_cache.PRICES 里时 cost_usd 写 NULL，绝不猜价** ——
  -- 猜出来的价会被当成账目读，比没有更糟。
  prompt_tokens     INT UNSIGNED NULL COMMENT '输入 token',
  cached_tokens     INT UNSIGNED NULL COMMENT '其中命中服务端 prompt cache 的部分',
  completion_tokens INT UNSIGNED NULL COMMENT '输出 token（含 reasoning）',
  reasoning_tokens  INT UNSIGNED NULL COMMENT '其中的推理 token；xhigh 下这是账单主体',
  cost_usd          DECIMAL(10,6) NULL COMMENT '按 PRICES 估算；型号未登记时为 NULL',
  latency_ms        INT UNSIGNED NULL,

  is_legacy      BOOLEAN      NOT NULL DEFAULT FALSE COMMENT '由历史 JSONL 回填，无 prompt 原文与用量',
  created_at     DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),

  PRIMARY KEY (id),
  UNIQUE KEY uk_llm_cache_key (cache_key),
  KEY idx_llm_stage (museum_key, stage, created_at),
  KEY idx_llm_model (model, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='LLM 调用缓存与计量。键含提示词全文的哈希，故改判据必然不命中、不改判据必然命中；cache_key 为 NULL 的是历史回填记录，只作归档不参与命中';

-- ============================================================================
-- llm_call ←→ 展品 的关联（多对多）
--
-- 【为什么不是 artwork_id 外键】
-- import_artworks.py:382-391 对 museum / gallery / artwork 三表全部 DELETE 并
-- ALTER AUTO_INCREMENT = 1，所以 **artwork.id 与 museum.id 都是每次重灌重新分配的**。
-- 实测：2026-09-03 把 mfa_boston_ext 插进 MUSEUMS 第 2 位，PEM 的 museum.id
-- 就从 2 变成 3、第一件展品的 artwork.id 从 204 变成 4668 —— 只因为加了一个
-- 不相干的馆。按 id 建关联会在下一次导入时整体错位，**且不报任何错**。
-- 故沿用其余派生表的软键 (museum_key, source_seq)，见 schema_tier_v3.sql 的说明。
--
-- 【为什么是多对多】
-- 一次调用覆盖一批展品（阶段一 12 件、阶段二一整个 peer group）；
-- 一件展品又会被多次调用碰到（评分一/二/三 + 审计一/二，S 段共 5 次）。
-- 一对多的设计两头都装不下。
--
-- call_id 的外键是安全的：llm_call 是本模块自己的表，从不被导入器清空，
-- CASCADE 也正是想要的语义（删掉一次调用记录，它的关联一并消失）。
-- ============================================================================

CREATE TABLE IF NOT EXISTS llm_call_item (
  call_id     BIGINT UNSIGNED NOT NULL COMMENT 'llm_call.id',
  museum_key  VARCHAR(32)     NOT NULL COMMENT '馆标识，对应 museum.key_name',
  source_seq  INT UNSIGNED    NOT NULL COMMENT '源表序号，对应 artwork.source_seq',

  PRIMARY KEY (call_id, museum_key, source_seq),
  KEY idx_lci_item (museum_key, source_seq),

  CONSTRAINT fk_lci_call FOREIGN KEY (call_id) REFERENCES llm_call (id)
    ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='哪次 LLM 调用覆盖了哪些展品。软键 (museum_key, source_seq)，不用 artwork.id —— 它每次重灌都重新分配';

-- 便利视图：把调用记录接回 artwork，省得每次手写三段 JOIN。
-- 注意 JOIN 条件走 museum.key_name 而非 id，理由同上。
CREATE OR REPLACE VIEW v_artwork_llm_call AS
SELECT m.key_name       AS museum_key,
       a.source_seq,
       a.id             AS artwork_id,      -- 仅供当次查询使用，**不要存下来**
       tn.text          AS artwork_name_zh,
       a.tier,
       c.id             AS call_id,
       c.stage, c.model, c.effort, c.scope,
       c.prompt_tokens, c.cached_tokens, c.completion_tokens,
       c.reasoning_tokens, c.cost_usd, c.is_legacy, c.created_at
FROM llm_call_item i
JOIN llm_call c ON c.id = i.call_id
JOIN museum   m ON m.key_name = i.museum_key
JOIN artwork  a ON a.museum_id = m.id AND a.source_seq = i.source_seq
LEFT JOIN content_text tn ON tn.content_id = a.name_cid AND tn.lang = 'zh-CN';

-- ============================================================================
-- 2026-09-03 增补：artwork_id / museum_id 便利列（用户要求）
--
-- **权威键仍然是软键 (museum_key, source_seq)。** 这两列是为了方便直接 JOIN
-- 而冗余出来的**缓存**，不是关联依据，所以都可空。
--
-- 【它们会失效，这是设计内的】
-- import_artworks.py 清空 museum/gallery/artwork 三表并重置 AUTO_INCREMENT，
-- 所以每跑一次导入，这两列就全部指向错误的行。实测：2026-09-03 加入
-- mfa_boston_ext 后，PEM 的 museum.id 由 2 变 3、首件 artwork.id 由 204 变 4668。
--
-- 【所以必须在每次导入后刷新】
--     python3 llm_cache.py --refresh-ids
-- 它按 (museum_key, source_seq) 重新解析这两列，解析不到的置 NULL。
-- **导入器不会自动调它** —— 同 tier_v3_load.py --apply-tier 的处境：
-- 忘了跑不会报错，只是数据悄悄错位。要判断新鲜度看 ids_synced_at。
--
-- 用 ALTER 而非重建：本表装的是已付费的答案，重建等于把钱扔掉（见文件头）。
-- ============================================================================

ALTER TABLE llm_call_item
  ADD COLUMN artwork_id     INT UNSIGNED NULL COMMENT '便利列，= artwork.id；重灌即失效，须 llm_cache.py --refresh-ids 刷新',
  ADD COLUMN museum_id      INT UNSIGNED NULL COMMENT '便利列，= museum.id；同上',
  ADD COLUMN ids_synced_at  DATETIME(3)  NULL COMMENT '这两列最后一次刷新的时间；早于最近一次导入即为过期',
  ADD KEY idx_lci_artwork (artwork_id);

ALTER TABLE llm_call
  ADD COLUMN museum_id      INT UNSIGNED NULL COMMENT '便利列，= museum.id；重灌即失效，须 --refresh-ids 刷新',
  ADD COLUMN ids_synced_at  DATETIME(3)  NULL COMMENT '同上';

-- 视图补上便利列，并直接给出新鲜度判断，省得每次自己比时间。
-- stale = 这一行的 artwork_id 是在最近一次导入之前解析的，已经不可信。
CREATE OR REPLACE VIEW v_artwork_llm_call AS
SELECT m.key_name       AS museum_key,
       a.source_seq,
       a.id             AS artwork_id,        -- 实时 JOIN 出来的，永远正确
       i.artwork_id     AS artwork_id_cached, -- 存下来的便利列，可能已过期
       i.museum_id      AS museum_id_cached,
       i.ids_synced_at,
       (i.artwork_id IS NULL OR i.artwork_id <> a.id) AS ids_stale,
       tn.text          AS artwork_name_zh,
       a.tier,
       c.id             AS call_id,
       c.stage, c.model, c.effort, c.scope,
       c.prompt_tokens, c.cached_tokens, c.completion_tokens,
       c.reasoning_tokens, c.cost_usd, c.is_legacy, c.created_at
FROM llm_call_item i
JOIN llm_call c ON c.id = i.call_id
JOIN museum   m ON m.key_name = i.museum_key
JOIN artwork  a ON a.museum_id = m.id AND a.source_seq = i.source_seq
LEFT JOIN content_text tn ON tn.content_id = a.name_cid AND tn.lang = 'zh-CN';

-- ============================================================================
-- 2026-09-03 增补：把失败的调用也记下来
--
-- 原先 fn() 一抛异常就什么都不写，于是「API 报错 / 模型拒答 / 返回的 JSON 解析
-- 不了」这几类调用在表里查不到 —— 而它们照样可能已经消耗了 token，也照样是
-- 判断「这一轮到底发生了什么」的关键线索（例如整批 429 限流）。
--
-- **失败行的 cache_key 必须为 NULL。** 否则下次同样的提示词会命中一条错误记录，
-- 把一次失败永久固化成"答案"。NULL 让它只作日志，永不参与命中。
-- ============================================================================

ALTER TABLE llm_call
  ADD COLUMN status     ENUM('ok','error') NOT NULL DEFAULT 'ok'
             COMMENT 'error 行的 cache_key 恒为 NULL，只作日志不参与命中',
  ADD COLUMN error_text TEXT NULL COMMENT '异常类型与消息',
  ADD KEY idx_llm_status (status, created_at);
