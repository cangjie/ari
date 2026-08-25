-- =====================================================================
-- 世界文化城市 / 文化点位 数据库  (MySQL 8.0)
-- 数据来源：500cities_tier_v2.xlsx
--   sheet1_城市列表         500 行 -> city
--   sheet2_博物馆遗产地列表   825 行 -> cultural_site
--   sheet3_等级变动明细      380 行 -> cultural_site_tier_change
--
-- 命名约定：主表名用完整的 cultural_site；表内的列名、索引名、约束名一律
-- 用短别名 site（site_id / flagship_site_id / idx_site_* / ck_site_*），
-- 避免 idx_cultural_site_track_score 这类过长标识符。本库中 site 即 cultural_site。
--
-- 多语种约定：所有展示文本不直接存在主表，而是存一个内容ID（*_cid）指向
-- content，由 content_text 按语种给出文本。主表另留规范名 *_key 作为标识符：
--   *_key  —— 标识符，取源数据原值，用于唯一约束 / 索引 / 导入时的字典查找，不用于展示
--   *_cid  —— 内容ID，展示时 join content_text 按 locale 取对应语种
-- 之所以两者并存：内容ID只能保证「ID不重复」，保证不了「文本不重复」，
-- uk_city_name_country / uk_site_name_city 这类去重约束必须落在 *_key 上。
-- =====================================================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

DROP VIEW  IF EXISTS v_cultural_site_full;
DROP VIEW  IF EXISTS v_artwork_full;
DROP TABLE IF EXISTS artwork;
DROP TABLE IF EXISTS gallery;
DROP TABLE IF EXISTS museum;
DROP TABLE IF EXISTS cultural_site_tier_change;
DROP TABLE IF EXISTS cultural_site;
DROP TABLE IF EXISTS city;
DROP TABLE IF EXISTS content_text;
DROP TABLE IF EXISTS content;

SET FOREIGN_KEY_CHECKS = 1;

-- ---------------------------------------------------------------------
-- 内容表：一段内容一个ID，多语种文本挂在 content_text 上
--
-- 按去重文本建条目，同文本共享同一个ID：115 个国家名只占 115 行而非 500 行，
-- 7 条 data_source 只占 7 行而非 825 行。改一处译文全库生效。
-- ---------------------------------------------------------------------
-- kind 同时划分「内容归谁所有」：两个导入器各管一批 kind，各自只删自己那批，
-- 并在互不重叠的ID段里显式分配ID，因此任一侧单独重跑都不会动到另一侧。
--   import_data.py     城市/点位榜单   前 7 种    ID 1 – 999,999
--   import_artworks.py 六馆展品        后 7 种    ID 1,000,000 起
CREATE TABLE content (
  id   INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '内容ID，由导入器按数据集分段显式分配',
  kind ENUM('city_name','country_name','site_name','tier_reason',
            'change_reason','collection_type','data_source',
            'museum_name','gallery_name','gallery_theme',
            'artwork_name','artwork_description','artwork_medium','artwork_tier_reason')
       NOT NULL COMMENT '内容归类：既便于按类清点未译项，也界定两个导入器各自的清空范围',

  PRIMARY KEY (id),
  KEY idx_content_kind (kind)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='可翻译内容的身份表，本身不存文本；榜单 2416 段 + 展品若干';

CREATE TABLE content_text (
  content_id INT UNSIGNED NOT NULL COMMENT '内容ID，外键 content.id',
  lang       VARCHAR(10)  NOT NULL COMMENT '语种，BCP-47 标签：zh-CN / en；加语种只是多插行，不动表结构',
  text       VARCHAR(512) NOT NULL COMMENT '该语种下的文本，实测最长 116 字符',
  source     ENUM('原始','AI翻译','存疑','人工校对') NOT NULL DEFAULT '原始'
             COMMENT '文本来源：原始=来自源 Excel；AI翻译=脚本从译名表写入；存疑=AI 译文且译者自标不确定，优先复核；人工校对=已人工确认或采用通行官方译名',

  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),

  PRIMARY KEY (content_id, lang),
  KEY idx_ct_lang_text (lang, text(64)) COMMENT '支撑按语种做前缀搜索',
  KEY idx_ct_source (source) COMMENT '支撑「捞出所有待复核 AI 译文」',
  CONSTRAINT fk_ct_content FOREIGN KEY (content_id) REFERENCES content (id)
    ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='内容的多语种文本；(content_id, lang) 唯一，同一内容同一语种只有一条';

-- ---------------------------------------------------------------------
-- 城市表
-- ---------------------------------------------------------------------
CREATE TABLE city (
  id                  INT UNSIGNED      NOT NULL AUTO_INCREMENT COMMENT '城市ID',
  name_key            VARCHAR(64)       NOT NULL   COMMENT '城市规范名（取源数据中文原值，如「梵蒂冈城」），标识符不用于展示',
  name_cid            INT UNSIGNED      NOT NULL   COMMENT '城市名内容ID -> content.id',
  country_key         VARCHAR(64)       NOT NULL   COMMENT '国家规范名（中文原值），标识符不用于展示；115 个不同值',
  country_cid         INT UNSIGNED      NOT NULL   COMMENT '国家名内容ID -> content.id',
  continent           ENUM('亚洲','欧洲','非洲','北美洲','南美洲','大洋洲')
                                        NOT NULL   COMMENT '所在大洲；6 个固定值是代码不是自由文本，故保留 ENUM，英文在应用层用常量映射',

  -- 五个分项得分，Excel 中均为 0-100 的整数，留 DECIMAL(4,1) 余量以便日后细化
  score_art_museum    DECIMAL(4,1)      NOT NULL DEFAULT 0 COMMENT '艺术博物馆得分 0-100',
  score_history       DECIMAL(4,1)      NOT NULL DEFAULT 0 COMMENT '历史文明得分 0-100',
  score_archaeology   DECIMAL(4,1)      NOT NULL DEFAULT 0 COMMENT '考古宗教遗产得分 0-100',
  score_architecture  DECIMAL(4,1)      NOT NULL DEFAULT 0 COMMENT '建筑文化价值得分 0-100',
  score_accessibility DECIMAL(4,1)      NOT NULL DEFAULT 0 COMMENT '旅游可达性得分 0-100',
  score_total         DECIMAL(5,2)      NOT NULL DEFAULT 0 COMMENT '综合得分 0-100，实测 33.6-94.1',

  city_rank           SMALLINT UNSIGNED NOT NULL   COMMENT '综合排名，1 起，实测 1-500，全表唯一',
  category            ENUM('综合类','艺术博物馆','考古遗址','历史建筑群','宗教遗产')
                                        NOT NULL   COMMENT '城市文化类型',
  flagship_site_id    INT UNSIGNED      NULL       COMMENT '代表性点位，指向 cultural_site.id；导入时二次回填',

  created_at          DATETIME(3)       NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at          DATETIME(3)       NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),

  PRIMARY KEY (id),
  UNIQUE KEY uk_city_name_country (name_key, country_key) COMMENT '城市名在本数据集内已全局唯一，仍带上国家防重名（如未来出现同名城市）；落在 *_key 上，内容ID挡不住文本重复',
  UNIQUE KEY uk_city_rank (city_rank),
  KEY idx_city_country (country_key) COMMENT '按国家筛选走此索引，不必 join content_text',
  KEY idx_city_continent_rank (continent, city_rank),
  KEY idx_city_score_total (score_total DESC),
  KEY idx_city_flagship (flagship_site_id),
  KEY idx_city_name_cid (name_cid),
  KEY idx_city_country_cid (country_cid),
  CONSTRAINT fk_city_name_content    FOREIGN KEY (name_cid)    REFERENCES content (id)
    ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_city_country_content FOREIGN KEY (country_cid) REFERENCES content (id)
    ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT ck_city_score_range CHECK (
        score_art_museum    BETWEEN 0 AND 100
    AND score_history       BETWEEN 0 AND 100
    AND score_archaeology   BETWEEN 0 AND 100
    AND score_architecture  BETWEEN 0 AND 100
    AND score_accessibility BETWEEN 0 AND 100
    AND score_total         BETWEEN 0 AND 100)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='文化城市榜单，500 行；排名与得分为城市自身属性，按评级规则 v2 不参与点位定级计算';

-- ---------------------------------------------------------------------
-- 文化点位表：博物馆 + 遗址地 统一收录
-- ---------------------------------------------------------------------
CREATE TABLE cultural_site (
  id              INT UNSIGNED    NOT NULL AUTO_INCREMENT COMMENT '文化点位ID',
  city_id         INT UNSIGNED    NOT NULL COMMENT '所在城市，外键 city.id；国家/大洲不再冗余存储，从 city 关联取',
  name_key        VARCHAR(128)    NOT NULL COMMENT '点位规范名（取源数据原值，中英文混排，实测最长 72 字符），标识符不用于展示',
  name_cid        INT UNSIGNED    NOT NULL COMMENT '点位名内容ID -> content.id',
  -- 事实属性：两个独立布尔，可同时为真（故宫博物院、兵马俑、托普卡帕宫均为双属性）
  is_museum        BOOLEAN NOT NULL DEFAULT FALSE COMMENT '是否为博物馆：有登录藏品与策展体系的机构',
  is_heritage_site BOOLEAN NOT NULL DEFAULT FALSE COMMENT '是否为遗址地：不可移动本体在成为博物馆之前已因自身用途（宫殿/宗教/陵墓/遗址/名人居所/军事）具备遗产价值；为陈列目的新建或改建的馆舍不计',

  -- 评级归属：与上面两个事实属性正交。双属性条目按规则 v2 只在其中一条赛道参评
  track           ENUM('博物馆','遗址地') NOT NULL COMMENT '评级赛道：M 博物馆 / H 遗址地。双属性条目按主属性择一归入，两条赛道各自排名互不挤占名额（S 级各 20 个）',

  -- 评级结果
  tier            ENUM('S','A','B','C') NOT NULL COMMENT '新等级（规则 v2）',
  tier_prev       ENUM('S','A','B','C') NULL     COMMENT '原等级（规则 v1），无历史版本时为 NULL',
  tier_delta      TINYINT         NOT NULL DEFAULT 0 COMMENT '等级变动档数：正=升档，负=降档，0=不变；由 tier_prev 与 tier 计算得出',
  score_total     DECIMAL(5,2)    NOT NULL COMMENT '加权综合得分 0-100，实测 33.65-98.16',

  -- 六个评分维度，各 0-10 分。含义随赛道不同：
  --   博物馆：藏品世界唯一性 / 文明叙事完整度 / 学术与国际影响力 / 国际认知指数 / 展陈与公众体验 / 规模与保障
  --   遗址地：原真性与完整性 / 文明地位(OUV) / 现场震撼度 / 国际认知指数 / 阐释与配套 / 保存状况与可达性
  dim1            DECIMAL(3,1)    NOT NULL COMMENT '维度1：藏品世界唯一性(M) / 原真性与完整性(H)，权重 3.0 / 2.8',
  dim2            DECIMAL(3,1)    NOT NULL COMMENT '维度2：文明叙事完整度(M) / 文明地位OUV(H)，权重 2.0 / 2.7',
  dim3            DECIMAL(3,1)    NOT NULL COMMENT '维度3：学术与国际影响力(M) / 现场震撼度(H)，权重 1.8 / 1.5',
  dim4            DECIMAL(3,1)    NOT NULL COMMENT '维度4：国际认知指数 IRI（已去人口化），权重 1.7 / 1.5',
  dim5            DECIMAL(3,1)    NOT NULL COMMENT '维度5：展陈与公众体验(M) / 阐释与配套(H)，权重 1.0',
  dim6            DECIMAL(3,1)    NOT NULL COMMENT '维度6：规模与保障(M) / 保存状况与可达性(H)，权重 0.5',
  tier_reason_cid INT UNSIGNED    NULL     COMMENT '定级理由内容ID -> content.id；长文本无去重需求，故只有 cid 没有 key',

  -- 原表「年参观人数/说明」是一列混装两种值，此处拆开
  annual_visitors BIGINT UNSIGNED NULL     COMMENT '年参观人次，实测 81 万-905 万；仅 96/825 条有值',
  visitors_year   SMALLINT UNSIGNED NULL   COMMENT '参观人次统计年份，2024 或 2025；2 条只有人次无年份',
  collection_type_cid INT UNSIGNED NULL    COMMENT '门类内容ID -> content.id；152 条有值，去重后仅 10 个',
  data_source_cid     INT UNSIGNED NULL    COMMENT '原数据来源内容ID -> content.id；825 条有值，去重后仅 7 个',

  created_at      DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at      DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),

  PRIMARY KEY (id),
  UNIQUE KEY uk_site_name_city (name_key, city_id) COMMENT '名称本身不唯一（「城市宫殿博物馆」在斋浦尔与乌代布尔各一座），须与城市联合唯一；落在 name_key 上',
  KEY idx_site_city (city_id),
  KEY idx_site_tier_score (tier, score_total DESC),
  KEY idx_site_track_score (track, score_total DESC) COMMENT '支撑「按赛道取 Top N」的名额控制查询',
  KEY idx_site_visitors (annual_visitors DESC),
  KEY idx_site_is_museum (is_museum, tier),
  KEY idx_site_is_heritage (is_heritage_site, tier),
  KEY idx_site_name_cid (name_cid),
  CONSTRAINT fk_site_city FOREIGN KEY (city_id) REFERENCES city (id)
    ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_site_name_content       FOREIGN KEY (name_cid)            REFERENCES content (id)
    ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_site_reason_content     FOREIGN KEY (tier_reason_cid)     REFERENCES content (id)
    ON UPDATE CASCADE ON DELETE SET NULL,
  CONSTRAINT fk_site_collection_content FOREIGN KEY (collection_type_cid) REFERENCES content (id)
    ON UPDATE CASCADE ON DELETE SET NULL,
  CONSTRAINT fk_site_source_content     FOREIGN KEY (data_source_cid)     REFERENCES content (id)
    ON UPDATE CASCADE ON DELETE SET NULL,
  CONSTRAINT ck_site_dim_range CHECK (
        dim1 BETWEEN 0 AND 10 AND dim2 BETWEEN 0 AND 10 AND dim3 BETWEEN 0 AND 10
    AND dim4 BETWEEN 0 AND 10 AND dim5 BETWEEN 0 AND 10 AND dim6 BETWEEN 0 AND 10),
  CONSTRAINT ck_site_score_range CHECK (score_total BETWEEN 0 AND 100),
  CONSTRAINT ck_site_has_attribute CHECK (is_museum = TRUE OR is_heritage_site = TRUE)
    /* 两个属性不能同时为假，否则这条记录不该出现在本表 */,
  CONSTRAINT ck_site_visitors_year CHECK (visitors_year IS NULL OR visitors_year BETWEEN 1900 AND 2100),
  CONSTRAINT ck_site_tier_delta CHECK (tier_delta BETWEEN -3 AND 3)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='文化点位（博物馆 455 + 遗址地 370 = 825 行）；等级衡量点位自身不可替代性，不继承所在城市排名';

ALTER TABLE city
  ADD CONSTRAINT fk_city_flagship FOREIGN KEY (flagship_site_id) REFERENCES cultural_site (id)
  ON UPDATE CASCADE ON DELETE SET NULL;

-- ---------------------------------------------------------------------
-- 等级变动历史表
-- ---------------------------------------------------------------------
CREATE TABLE cultural_site_tier_change (
  id                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '变动记录ID',
  site_id           INT UNSIGNED    NOT NULL COMMENT '文化点位，外键 cultural_site.id',
  rule_version_from VARCHAR(16)     NOT NULL DEFAULT 'v1' COMMENT '变动前所依据的规则版本',
  rule_version_to   VARCHAR(16)     NOT NULL DEFAULT 'v2' COMMENT '变动后所依据的规则版本',
  tier_from         ENUM('S','A','B','C') NOT NULL COMMENT '原等级',
  tier_to           ENUM('S','A','B','C') NOT NULL COMMENT '新等级',
  tier_delta        TINYINT         NOT NULL COMMENT '变动档数：+1/+2/+3 升档，-1/-2 降档',
  score_total       DECIMAL(5,2)    NULL     COMMENT '变动后综合得分快照',
  change_reason_cid INT UNSIGNED    NULL     COMMENT '变动原因内容ID -> content.id；长文本无去重需求，故只有 cid 没有 key',
  changed_at        DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '记录写入时间',

  PRIMARY KEY (id),
  UNIQUE KEY uk_change_site_version (site_id, rule_version_from, rule_version_to)
    COMMENT '同一点位在同一次版本升级中只记一条',
  KEY idx_change_delta (tier_delta),
  KEY idx_change_to (tier_to),
  CONSTRAINT fk_change_site FOREIGN KEY (site_id) REFERENCES cultural_site (id)
    ON UPDATE CASCADE ON DELETE CASCADE,
  CONSTRAINT fk_change_reason_content FOREIGN KEY (change_reason_cid) REFERENCES content (id)
    ON UPDATE CASCADE ON DELETE SET NULL,
  CONSTRAINT ck_change_delta CHECK (tier_delta BETWEEN -3 AND 3 AND tier_delta <> 0),
  CONSTRAINT ck_change_moved CHECK (tier_from <> tier_to)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='规则版本升级导致的等级变动明细，v1->v2 共 380 条';

-- ---------------------------------------------------------------------
-- 常用视图：把 cultural_site 与 city 拼回 Excel 的宽表形态
--
-- 双语并排，供人工核对译文质量用。应用侧不要用这个视图取展示文本 ——
-- 它把两个语种都取出来了；web_api 应按请求 locale 做参数化查询并回落：
--   COALESCE(请求语种, 'zh-CN', *_key)
-- 回落是必须的：825 条点位里 575 条目前只有中文。
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW v_cultural_site_full AS
SELECT
  s.id,
  c.city_rank                AS 城市排名,
  s.tier                     AS 新Tier,
  s.tier_prev                AS 原Tier,
  CASE WHEN s.tier_delta > 0 THEN CONCAT('↑升 ', s.tier_delta, ' 档')
       WHEN s.tier_delta < 0 THEN CONCAT('↓降 ', -s.tier_delta, ' 档')
       ELSE '—' END          AS 等级变动,
  s.track                    AS 评级赛道,
  s.is_museum                AS 是博物馆,
  s.is_heritage_site         AS 是遗址地,
  CASE WHEN s.is_museum AND s.is_heritage_site THEN '博物馆+遗址地'
       WHEN s.is_museum                        THEN '博物馆'
       ELSE '遗址地' END     AS 属性,
  s.name_key                 AS 名称_key,
  sn_zh.text                 AS 名称_zh,
  sn_en.text                 AS 名称_en,
  c.name_key                 AS 所在城市_key,
  cn_zh.text                 AS 所在城市_zh,
  cn_en.text                 AS 所在城市_en,
  c.country_key              AS 所在国家_key,
  co_zh.text                 AS 所在国家_zh,
  co_en.text                 AS 所在国家_en,
  c.continent                AS 所在大洲,
  s.score_total              AS 综合得分,
  s.dim1, s.dim2, s.dim3, s.dim4, s.dim5, s.dim6,
  tr_zh.text                 AS 定级理由_zh,
  tr_en.text                 AS 定级理由_en,
  s.annual_visitors          AS 年参观人数,
  s.visitors_year            AS 统计年份,
  cl_zh.text                 AS 门类_zh,
  cl_en.text                 AS 门类_en,
  ds_zh.text                 AS 原数据来源_zh,
  ds_en.text                 AS 原数据来源_en
FROM cultural_site s
JOIN city c ON c.id = s.city_id
LEFT JOIN content_text sn_zh ON sn_zh.content_id = s.name_cid            AND sn_zh.lang = 'zh-CN'
LEFT JOIN content_text sn_en ON sn_en.content_id = s.name_cid            AND sn_en.lang = 'en'
LEFT JOIN content_text cn_zh ON cn_zh.content_id = c.name_cid            AND cn_zh.lang = 'zh-CN'
LEFT JOIN content_text cn_en ON cn_en.content_id = c.name_cid            AND cn_en.lang = 'en'
LEFT JOIN content_text co_zh ON co_zh.content_id = c.country_cid         AND co_zh.lang = 'zh-CN'
LEFT JOIN content_text co_en ON co_en.content_id = c.country_cid         AND co_en.lang = 'en'
LEFT JOIN content_text tr_zh ON tr_zh.content_id = s.tier_reason_cid     AND tr_zh.lang = 'zh-CN'
LEFT JOIN content_text tr_en ON tr_en.content_id = s.tier_reason_cid     AND tr_en.lang = 'en'
LEFT JOIN content_text cl_zh ON cl_zh.content_id = s.collection_type_cid AND cl_zh.lang = 'zh-CN'
LEFT JOIN content_text cl_en ON cl_en.content_id = s.collection_type_cid AND cl_en.lang = 'en'
LEFT JOIN content_text ds_zh ON ds_zh.content_id = s.data_source_cid     AND ds_zh.lang = 'zh-CN'
LEFT JOIN content_text ds_en ON ds_en.content_id = s.data_source_cid     AND ds_en.lang = 'en';

-- =====================================================================
-- 展品数据集：六个博物馆的在展/馆藏文物清单
--   MFA 波士顿 203 / PEM 196 / 哈佛 204 / 国博 365 / 故宫 1757 / 首博 6159
--   合计 8884 条，约 172 个展厅
--
-- 与上面的城市/点位榜单是两个独立数据集，仅共用 content / content_text。
-- 由 import_artworks.py 导入，见该脚本与 README 第九节。
-- =====================================================================

-- ---------------------------------------------------------------------
-- 博物馆：展品的来源馆，6 行
-- ---------------------------------------------------------------------
CREATE TABLE museum (
  id          INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '博物馆ID',
  key_name    VARCHAR(32)  NOT NULL COMMENT '稳定短标识，如 mfa_boston / palace；导入脚本按它认馆',
  name_cid    INT UNSIGNED NOT NULL COMMENT '馆名内容ID -> content.id',
  site_key    VARCHAR(128) NULL     COMMENT '软链 cultural_site.name_key；不是外键，理由见下',
  source_file VARCHAR(128) NOT NULL COMMENT '源 Excel 文件名，便于溯源',

  created_at  DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at  DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),

  PRIMARY KEY (id),
  UNIQUE KEY uk_museum_key (key_name),
  KEY idx_museum_site (site_key),
  CONSTRAINT fk_museum_name_content FOREIGN KEY (name_cid) REFERENCES content (id)
    ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='展品来源馆。site_key 刻意做成软链而非外键：import_data.py 每次重灌都 DELETE FROM cultural_site，硬外键 RESTRICT 会让榜单导入失败、CASCADE 会静默删光展品；且 6 个馆里 PEM/哈佛/首博 3 个根本不在 cultural_site 中。查询时 LEFT JOIN cultural_site ON name_key = site_key 即可';

-- ---------------------------------------------------------------------
-- 展厅：约 172 行
-- ---------------------------------------------------------------------
CREATE TABLE gallery (
  id                INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '展厅ID',
  museum_id         INT UNSIGNED NOT NULL COMMENT '所属博物馆，外键 museum.id',
  name_key          VARCHAR(255) NOT NULL COMMENT '展厅规范名（源数据原值），标识符不用于展示',
  name_cid          INT UNSIGNED NOT NULL COMMENT '展厅名内容ID -> content.id',
  theme_cid         INT UNSIGNED NULL     COMMENT '展厅主题内容ID；仅故宫「展厅索引」页提供',
  location          VARCHAR(255) NULL     COMMENT '展厅位置，如「武英殿正殿、工字廊」；仅故宫提供',
  suggested_minutes SMALLINT UNSIGNED NULL COMMENT '建议停留分钟数；仅故宫提供',
  official_url      VARCHAR(512) NULL     COMMENT '展厅官方页面',

  created_at        DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at        DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),

  PRIMARY KEY (id),
  UNIQUE KEY uk_gallery_museum_name (museum_id, name_key),
  KEY idx_gallery_name_cid (name_cid),
  CONSTRAINT fk_gallery_museum       FOREIGN KEY (museum_id) REFERENCES museum (id)
    ON UPDATE CASCADE ON DELETE CASCADE,
  CONSTRAINT fk_gallery_name_content FOREIGN KEY (name_cid)  REFERENCES content (id)
    ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_gallery_theme_content FOREIGN KEY (theme_cid) REFERENCES content (id)
    ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='展厅；location/suggested_minutes/theme_cid 只有故宫的 6 个展厅有值，其余馆的源文件不提供';

-- ---------------------------------------------------------------------
-- 展品：8884 行
-- ---------------------------------------------------------------------
CREATE TABLE artwork (
  id               INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '展品ID',
  museum_id        INT UNSIGNED NOT NULL COMMENT '所属博物馆，外键 museum.id',
  gallery_id       INT UNSIGNED NULL     COMMENT '所在展厅，外键 gallery.id；源数据缺展厅时为 NULL',
  source_seq       INT UNSIGNED NOT NULL COMMENT '源表的 序号/Rank；这是馆内唯一能成立的键',
  name_key         VARCHAR(255) NOT NULL COMMENT '展品规范名（源数据原值），标识符不用于展示；**馆内不唯一**',
  name_cid         INT UNSIGNED NOT NULL COMMENT '展品名内容ID -> content.id',
  description_cid  INT UNSIGNED NULL     COMMENT '简介内容ID；故宫/首博的简介实为展厅级套话，靠内容表自动去重',
  medium_cid       INT UNSIGNED NULL     COMMENT '门类/材质内容ID（Media·Type / Category / Medium）',

  tier             ENUM('S','A','B','C') NULL COMMENT '等级；取 tier_c / Tier（重评），旧评级不入库。国博 12.6%、首博 10.4% 的行源数据无 Tier',
  tier_reason_cid  INT UNSIGNED NULL     COMMENT '评级理由内容ID；仅故宫提供',
  irreplaceability DECIMAL(5,2) NULL     COMMENT '不可替代性得分；仅故宫提供。实测 -26 ~ 98：评级理由里有「同名同型第2件，去重降分 20」这类惩罚项，负分是合法结果',

  on_view          ENUM('在展','未在展','未知') NOT NULL DEFAULT '未知'
                   COMMENT '三态：PEM 源文件无在展字段、首博 6133/6159 为「馆藏（在展状态未知）」，都只能记未知',
  has_image        BOOLEAN      NULL     COMMENT '是否有配图；PEM/哈佛为源字段，中文馆由图片URL是否存在推出',
  image_url        VARCHAR(512) NULL     COMMENT '展品图片；仅中文馆提供',
  official_url     VARCHAR(512) NULL     COMMENT '官方页面；中文馆为展厅级链接',

  created_at       DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at       DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),

  PRIMARY KEY (id),
  UNIQUE KEY uk_artwork_source (museum_id, source_seq)
    COMMENT '名称在馆内不唯一（故宫「寿山石十八罗汉像之一」同展厅 18 件、首博「明金冥钱」50 件，本就是成组文物），唯一键只能落在源序号上',
  KEY idx_artwork_museum_tier (museum_id, tier),
  KEY idx_artwork_tier_onview (tier, on_view),
  KEY idx_artwork_gallery (gallery_id),
  KEY idx_artwork_name_cid (name_cid),
  KEY idx_artwork_name_key (name_key(64)),
  CONSTRAINT fk_artwork_museum         FOREIGN KEY (museum_id)       REFERENCES museum (id)
    ON UPDATE CASCADE ON DELETE CASCADE,
  CONSTRAINT fk_artwork_gallery        FOREIGN KEY (gallery_id)      REFERENCES gallery (id)
    ON UPDATE CASCADE ON DELETE SET NULL,
  CONSTRAINT fk_artwork_name_content   FOREIGN KEY (name_cid)        REFERENCES content (id)
    ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_artwork_desc_content   FOREIGN KEY (description_cid) REFERENCES content (id)
    ON UPDATE CASCADE ON DELETE SET NULL,
  CONSTRAINT fk_artwork_medium_content FOREIGN KEY (medium_cid)      REFERENCES content (id)
    ON UPDATE CASCADE ON DELETE SET NULL,
  CONSTRAINT fk_artwork_reason_content FOREIGN KEY (tier_reason_cid) REFERENCES content (id)
    ON UPDATE CASCADE ON DELETE SET NULL,
  CONSTRAINT ck_artwork_irreplaceability CHECK (irreplaceability IS NULL OR irreplaceability BETWEEN -100 AND 100)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='六馆展品清单 8884 条；文本全部走 content/content_text，主表只存内容ID';

-- ---------------------------------------------------------------------
-- 展品双语宽表：供人工核对译文用
-- 应用侧同样不要用它取展示文本，该按 locale 参数化查询并回落
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW v_artwork_full AS
SELECT
  a.id,
  mn_zh.text        AS 博物馆_zh,
  mn_en.text        AS 博物馆_en,
  m.site_key        AS 对应点位_key,
  g.name_key        AS 展厅_key,
  gn_zh.text        AS 展厅_zh,
  gn_en.text        AS 展厅_en,
  a.source_seq      AS 源序号,
  a.name_key        AS 名称_key,
  an_zh.text        AS 名称_zh,
  an_en.text        AS 名称_en,
  a.tier            AS 等级,
  a.on_view         AS 在展状态,
  a.irreplaceability AS 不可替代性得分,
  ad_zh.text        AS 简介_zh,
  ad_en.text        AS 简介_en,
  am_zh.text        AS 门类_zh,
  am_en.text        AS 门类_en,
  ar_zh.text        AS 评级理由_zh,
  ar_en.text        AS 评级理由_en,
  a.has_image       AS 有配图,
  a.image_url       AS 图片,
  a.official_url    AS 官方页面
FROM artwork a
JOIN museum m ON m.id = a.museum_id
LEFT JOIN gallery g ON g.id = a.gallery_id
LEFT JOIN content_text mn_zh ON mn_zh.content_id = m.name_cid         AND mn_zh.lang = 'zh-CN'
LEFT JOIN content_text mn_en ON mn_en.content_id = m.name_cid         AND mn_en.lang = 'en'
LEFT JOIN content_text gn_zh ON gn_zh.content_id = g.name_cid         AND gn_zh.lang = 'zh-CN'
LEFT JOIN content_text gn_en ON gn_en.content_id = g.name_cid         AND gn_en.lang = 'en'
LEFT JOIN content_text an_zh ON an_zh.content_id = a.name_cid         AND an_zh.lang = 'zh-CN'
LEFT JOIN content_text an_en ON an_en.content_id = a.name_cid         AND an_en.lang = 'en'
LEFT JOIN content_text ad_zh ON ad_zh.content_id = a.description_cid  AND ad_zh.lang = 'zh-CN'
LEFT JOIN content_text ad_en ON ad_en.content_id = a.description_cid  AND ad_en.lang = 'en'
LEFT JOIN content_text am_zh ON am_zh.content_id = a.medium_cid       AND am_zh.lang = 'zh-CN'
LEFT JOIN content_text am_en ON am_en.content_id = a.medium_cid       AND am_en.lang = 'en'
LEFT JOIN content_text ar_zh ON ar_zh.content_id = a.tier_reason_cid  AND ar_zh.lang = 'zh-CN'
LEFT JOIN content_text ar_en ON ar_en.content_id = a.tier_reason_cid  AND ar_en.lang = 'en';
