-- 导览站「游客互动」的两张表。可重复执行（IF NOT EXISTS / INSERT IGNORE）。
--
--   mysql --defaults-file=~/.my.cnf ari < web_api/sql/tour_qa.sql
--
-- ⚠ tour_topic 是游客数据，重跑不出来。改结构只在本文件末尾追加 ALTER，不要 DROP 重建。
--   它与 artwork 之间用软键 (museum_key, place_id) 关联，不建外键（AGENTS.md 第 6 条）：
--   place_id 是 web_api/tour/data/<馆>.json 里的地点 id。

CREATE TABLE IF NOT EXISTS tour_topic (
  id                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  museum_key        VARCHAR(32)  NOT NULL,
  place_id          VARCHAR(64)  NOT NULL,
  visitor_id        VARCHAR(64)  NOT NULL COMMENT '浏览器里生成的匿名设备号，不对外返回',
  question          VARCHAR(500) NOT NULL,
  answer            TEXT         NULL,
  status            ENUM('pending','answered','failed') NOT NULL DEFAULT 'pending',
  is_public         TINYINT(1)   NULL COMMENT '模型判断是不是正常的参观提问；NULL = 还没判',
  valid             TINYINT(1)   NOT NULL DEFAULT 1 COMMENT '人工下架置 0',
  model             VARCHAR(64)  NULL,
  effort            VARCHAR(16)  NULL,
  prompt_hash       CHAR(64)     NULL COMMENT 'sha256(provider|model|effort|system|user)',
  reused_from       BIGINT UNSIGNED NULL COMMENT '沿用了哪一行的答案（没调模型）',
  prompt_tokens     INT          NULL,
  completion_tokens INT          NULL,
  cached_tokens     INT          NULL,
  latency_ms        INT          NULL,
  error             VARCHAR(500) NULL,
  created_at        DATETIME     NOT NULL COMMENT 'UTC',
  answered_at       DATETIME     NULL COMMENT 'UTC',
  PRIMARY KEY (id),
  KEY ix_place (museum_key, place_id, id),
  KEY ix_visitor (visitor_id, created_at),
  KEY ix_hash (prompt_hash),
  KEY ix_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='导览站游客提问与 AI 回答';

-- 提问条数上限。每次提问现读、不缓存：改一行，下一条提问就按新值算。设成 0 = 关掉。
--   UPDATE tour_qa_setting SET value = 50 WHERE name = 'per_visitor_per_day';
CREATE TABLE IF NOT EXISTS tour_qa_setting (
  name       VARCHAR(40)  NOT NULL,
  value      INT UNSIGNED NOT NULL,
  note       VARCHAR(200) NOT NULL,
  updated_at TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='导览站游客互动的提问条数上限';

-- INSERT IGNORE：重跑本文件不会把已经改过的值冲回初值。
INSERT IGNORE INTO tour_qa_setting (name, value, note) VALUES
  ('per_visitor_per_day', 20,   '每个设备 24 小时内最多提问几条'),
  ('per_ip_per_hour',     120,  '每个 IP 每小时最多提问几条（只在内存里计数，服务重启后清零）'),
  ('site_per_day',        1000, '全站 24 小时内最多提问几条；设成 0 就是关掉提问');
