# 文化城市 / 文化点位 数据库

从 `500cities_tier_v2.xlsx` 建库并导入。**所有展示文本都是中英双语的**，
存在 `content` / `content_text` 两张表里，主表只引用内容ID。

| 文件 | 作用 | 什么时候改它 |
|---|---|---|
| `schema.sql` | 建表语句（MySQL 8.0）：`content`、`content_text` + `city`、`cultural_site`、`cultural_site_tier_change` + 一个双语宽表视图 | 要加字段、改类型、调索引时 |
| `import_data.py` | 读 Excel → 清洗 → 拆内容表 → 写库 | 要改清洗规则时 |
| `dual_attribute_overrides.csv` | 人工判定表：哪些点位既是博物馆又是遗址 | **最常改的就是它**，改完重跑脚本即可 |
| `translations_city.csv` | 译名表：城市名 615 段 | 要改城市 / 国家译名时 |
| `translations_site.csv` | 译名表：点位名 824 段 | 要改馆名 / 遗址名译名时 |
| `translations_text.csv` | 译名表：定级理由、变动原因、门类、数据来源 977 段 | 要改长文本译文时 |
| `make_translation_skeleton.py` | 按 Excel 增量更新上面三个译名表 | 换了新版 Excel 之后 |
| `translate_templates.py` | 翻译定级理由里的 860 条模板串 | 改维度词译法时 |

**译名必须留在这些 CSV 里，不能只改数据库。** 导入脚本每次都清空重灌，
写在库里的译名重跑一次就没了。

---

## 一、准备

需要 Python 3.8+ 和 MySQL 8.0。装两个库：

```bash
pip3 install openpyxl pymysql
```

`openpyxl` 读 Excel，`pymysql` 连 MySQL。只想先本地验证的话，`pymysql` 可以不装（见第三步）。

## 二、建库建表

数据库和账号已经建好（`ari` 库 / `ari` 账号）。只需建表：

```bash
mysql -h 44.207.251.65 -u ari -p ari < schema.sql
```

从零开始的话先建库：

```bash
mysql -u root -p -e "CREATE DATABASE ari CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;"
```

`schema.sql` 开头带 `DROP TABLE IF EXISTS`，重复执行会**清空重建**，正式环境注意。

## 三、导入数据

Excel 和这些文件放同一个目录，然后：

```bash
# 先空跑一遍：不连 MySQL，写进本地 SQLite 文件，确认清洗结果对不对
python3 import_data.py --excel 500cities_tier_v2.xlsx --sqlite ./check.db

# 确认无误后正式导入
python3 import_data.py --excel 500cities_tier_v2.xlsx \
    --host 44.207.251.65 --port 3306 --user ari --password 你的密码 --database ari
```

密码也可以放环境变量 `MYSQL_PASSWORD`，避免写进命令行历史：

```bash
export MYSQL_PASSWORD='你的密码'
python3 import_data.py --excel 500cities_tier_v2.xlsx --host 44.207.251.65
```

跑完应该看到：

```
读取双属性判定表 … 52 条（其中 5 条标记为存疑）
  属性分布：仅博物馆 421 / 仅遗址地 353 / 双属性 51
读取译名表 … 2416 条 / 共 2416 段可翻译文本（其中 13 条标记为存疑）
  content                   2416 段（city_name 500、country_name 115、site_name 824、tier_reason 629、change_reason 331、collection_type 10、data_source 7）
  content_text              4832 行（原始 2416 / 人工校对 2266 / AI翻译 137 / 存疑 13）
  city                       500 行
  cultural_site              825 行
  cultural_site_tier_change  380 行
  flagship_site_id 回填 500 个城市
```

数量对不上就是哪里出了问题。脚本自带自检，发现城市重复、外键孤儿、名称冲突会直接中止并报出原因，不会写半截数据进库。

导入可以反复执行，每次都会先清空五张表再重灌，不会累积重复数据。
走公网导入约需 2–3 分钟，慢在 500 次 `flagship_site_id` 回填是逐条 UPDATE。

---

## 四、改判定表

Excel 只有 `赛道` 一个二选一字段，表达不了「既是博物馆又是遗址」。所以 `is_museum` / `is_heritage_site` 两个布尔字段先按赛道打底，再由 `dual_attribute_overrides.csv` 覆盖。

改法：用 Excel 或文本编辑器打开，加一行

```csv
name,city,is_museum,is_heritage_site,confidence,reason
莫高窟,敦煌,1,1,确定,数字展示中心与藏经洞陈列馆
```

`name` 和 `city` 必须和数据库里的**完全一致**（对不上脚本会警告 `判定表有 N 条未匹配到点位`，方便查笔误）。`#` 开头的行是注释，会被跳过。

改完重跑第三步即可，不用动 SQL。

判定标准写在 CSV 文件头部：`is_heritage_site=1` 要求该不可移动本体**在成为博物馆之前**已因自身用途（宫殿／宗教／陵墓／遗址／名人居所／军事）具备遗产价值。为陈列而新建或改建的馆舍不算——所以卢浮宫、冬宫算，台北故宫、卫城博物馆不算。

标了 `存疑` 的 5 行建议复核：奥赛博物馆、那不勒斯国立考古博物馆、三星堆博物馆、9/11 Memorial & Museum、玛雅世界大博物馆。

---

## 五、多语种是怎么存的

一段内容一个ID，语种文本挂在 `content_text` 上：

```
city.name_key  '巴黎'        ← 标识符：撑唯一约束、索引、脚本查找，不展示
city.name_cid  → content.id  ← 内容ID
                    └── content_text (cid, 'zh-CN', '巴黎',  '原始')
                    └── content_text (cid, 'en',    'Paris', '人工校对')
```

**为什么 `*_key` 和 `*_cid` 并存**：内容ID只能保证「ID不重复」，保证不了
「文本不重复」。`uk_city_name_country`、`uk_site_name_city` 这类去重约束
必须落在 `*_key` 上，否则数据库拦不住两条一模一样的城市。
`*_key` 取源数据原值，从不用于展示。

**去重是真去重**：115 个国家名只占 115 行 content（而不是 500 行），
7 条 `data_source` 只占 7 行（而不是 825 行）。改一处译文全库生效。

`content_text.source` 标出每条文本的来路：

| 值 | 含义 | 条数 |
|---|---|---|
| `原始` | 来自源 Excel，未经翻译 | 2416 |
| `人工校对` | 通行既定译名，或模板串的确定性翻译 | 2266 |
| `AI翻译` | 机器翻译，正常可用 | 137 |
| `存疑` | 拿不准，**优先复核** | 13 |

捞出待复核项：

```sql
SELECT c.kind, t.text FROM content_text t
JOIN content c ON c.id = t.content_id WHERE t.source = '存疑';
```

`lang` 用 BCP-47 标签（`zh-CN` / `en`）。加日语法语只是往 `content_text`
多插行，不用动表结构。

### 改译名

改对应的 `translations_*.csv`，`key` 列必须和原文**逐字一致**
（对不上脚本会警告 `译名表有 N 条未匹配到原文`），改完重跑第三步。

换了新版 Excel 之后，先增量更新译名表骨架 —— 已填的译文会保留，
只追加新出现的原文，源数据里消失的条目会被报出来：

```bash
python3 make_translation_skeleton.py --dry-run   # 先看会怎么变
python3 make_translation_skeleton.py             # 确认后写入
python3 translate_templates.py                   # 补上新增的模板串
```

`translations_text.csv` 里 860/977 条是机器生成的定长模板
（`强项:…、…;弱项:…。`），由 `translate_templates.py` 按 11 个维度词 +
5 种尾注翻译。改维度词译法改那个脚本里的 `DIMENSIONS`，不要逐条手改 CSV。

---

## 六、表结构速查

**content**（2416 行）/ **content_text**（4832 行）— 见上一节。

**city**（500 行）— 城市榜单
`city_rank` 排名唯一，五项分项得分 + `score_total`，`flagship_site_id` 指向代表性点位。
名称与国家各有 `*_key` + `*_cid` 一对；`continent` 是 6 个固定值的 ENUM，
是代码不是自由文本，没有进内容表，英文在应用层用常量映射。

**cultural_site**（825 行）— 文化点位，博物馆和遗址地统一收录

- `name_key` / `name_cid` — 规范名 + 内容ID
- `is_museum` / `is_heritage_site` — 事实属性，可同时为真，约束保证至少一个为真
- `track` — 评级赛道，与上面两个字段正交，决定 S 级名额（博物馆 20 + 遗址地 20）和 `dim1`–`dim6` 的含义
- `dim1`–`dim6` — 六个评分维度各 0–10 分，含义随赛道不同，写在列注释里
- `tier_reason_cid` / `collection_type_cid` / `data_source_cid` — 长文本只有内容ID，无 key（无去重需求）
- `annual_visitors` / `visitors_year` — 从原表混装的一列拆出来的

**cultural_site_tier_change**（380 行）— v1→v2 的等级升降档记录，带规则版本号，出 v3 时直接追加。

---

## 七、常用查询

`v_cultural_site_full` 是**双语并排**的，供人工核对译文用。
应用侧不要用它取展示文本 —— 它把两个语种都取出来了，该按 locale 参数化查询。

```sql
-- 双语宽表：核对译文用
SELECT 名称_zh, 名称_en, 所在城市_zh, 所在城市_en, 新Tier, 综合得分
FROM v_cultural_site_full ORDER BY 综合得分 DESC LIMIT 20;

-- 应用查询：按 locale 取，缺则回落到中文，再缺回落到规范名
-- 825 条点位里 575 条原文只有中文，回落是必须的
SELECT COALESCE(t_pref.text, t_fb.text, s.name_key) AS name, s.tier, s.score_total
FROM cultural_site s
LEFT JOIN content_text t_pref ON t_pref.content_id = s.name_cid AND t_pref.lang = ?
LEFT JOIN content_text t_fb   ON t_fb.content_id   = s.name_cid AND t_fb.lang = 'zh-CN'
ORDER BY s.score_total DESC;

-- 按国家筛选：走 country_key 索引，不用 join content_text
SELECT name_key, city_rank FROM city WHERE country_key = '法国' ORDER BY city_rank;

-- 所有博物馆（含双属性的 51 条）
SELECT name_key, tier FROM cultural_site WHERE is_museum = 1 ORDER BY score_total DESC;

-- 双属性点位
SELECT s.name_key, c.name_key AS city, s.track, s.tier
FROM cultural_site s JOIN city c ON c.id = s.city_id
WHERE s.is_museum AND s.is_heritage_site
ORDER BY s.score_total DESC;

-- 每条赛道的 S 级名单（应各 20 条）
SELECT track, COUNT(*) FROM cultural_site WHERE tier = 'S' GROUP BY track;

-- 升了 2 档以上的点位和原因（中文）
SELECT s.name_key, t.tier_from, t.tier_to, ct.text AS reason
FROM cultural_site_tier_change t
JOIN cultural_site s ON s.id = t.site_id
LEFT JOIN content_text ct ON ct.content_id = t.change_reason_cid AND ct.lang = 'zh-CN'
WHERE t.tier_delta >= 2 ORDER BY t.tier_delta DESC;

-- 某个城市的全部点位
SELECT s.name_key, s.track, s.tier, s.is_museum, s.is_heritage_site
FROM cultural_site s JOIN city c ON c.id = s.city_id
WHERE c.name_key = '北京';

-- 还缺多少英文（现在应为 0）
SELECT c.kind, COUNT(*) FROM content c
WHERE NOT EXISTS (SELECT 1 FROM content_text WHERE content_id = c.id AND lang = 'en')
GROUP BY c.kind;
```

**注意 N+1**：列表页要展示 4 个可翻译字段就是 4~8 次 join。
`(content_id, lang)` 是主键，单次查找走聚簇索引很快，但不要逐行去查文本 ——
先批量取 cid，再一次性把文本查回来。

---

## 八、已知数据问题

- 7 个城市的「博物馆遗产地数量」列与实际行数对不上（暹粒、布哈拉、平遥、忻州、马六甲、图尔、杜塞尔多夫），是原表名称含中文逗号被拆行后又合并留下的。这一列是派生值，没有入库，脚本只警告不阻断。
- 遗址地赛道里有些点位实际设有博物馆（莫高窟、龙门石窟等），但名称里没有「博物馆」字样，未标 `is_museum=1`。需要的话在判定表里补。
- `annual_visitors` 只有 96 条有值，其中 2 条没有年份。
- 罗马的 `flagship_site_id` 指向 MAXXI（C 级 51.9），但同城的卡比托利欧博物馆是 A 级 78.4。原表「代表性机构」列本身就这么写的，脚本忠实照搬。要改就改 Excel。
- 13 条译文标了 `存疑`，多为原表信息不足或名称本身可疑，例如 `Te Papa Wai – Ulster Museum`（Te Papa 在新西兰、Ulster Museum 在贝尔法斯特，像是原表串行）、`内城`／`柱廊群`／`老大学` 这类没有上下文的泛称。`SELECT ... WHERE source = '存疑'` 可全部列出。

---

## 九、展品数据集（六个博物馆 8884 件）

`artworks/` 下六个源文件格式各不相同，由 `import_artworks.py` 归一后导入
`museum` / `gallery` / `artwork` 三张表，文本同样走 `content` / `content_text`。

| 馆 | key_name | 件数 | 源文件表头 |
|---|---|---|---|
| 波士顿美术馆 | `mfa_boston` | 203 | 第 1 行，`Master` 页 |
| 皮博迪·埃塞克斯博物馆 | `pem` | 196 | 第 1 行，`All Tiers` 页 |
| 哈佛艺术博物馆 | `ham` | 204 | 第 1 行，`All Tiers` 页 |
| 中国国家博物馆 | `nmc` | 365 | **第 4 行** |
| 故宫博物院 | `palace` | 1757 | **第 4 行** |
| 首都博物馆 | `capital` | 6159 | **第 4 行** |

```bash
python3 import_artworks.py --sqlite ./aw.db                    # 空跑
python3 import_artworks.py --host 44.207.251.65 --user ari --database ari
```

### 两个导入器如何共存

`content` 表被两个数据集共用，靠 **kind 划分所有权 + ID 分段** 隔离：

| 数据集 | kind | 内容ID段 |
|---|---|---|
| 榜单 `import_data.py` | `city_name`…`data_source` | 1 – 999,999 |
| 展品 `import_artworks.py` | `museum_name`、`gallery_*`、`artwork_*` | 1,000,000 起 |

各自清空时只删自己名下的 kind。**改动任一导入器的清空逻辑前先想清楚这一点** ——
早先的版本无条件 `DELETE FROM content`，会把另一侧的文本一起删掉；
而展品外键是 RESTRICT，真删起来是整个导入直接报错。

回归测试：导完展品后再跑一次 `import_data.py`，两侧行数都应不变。

### museum.site_key 是软链，不是外键

`import_data.py` 每次重灌都 `DELETE FROM cultural_site`。若 `museum` 硬外键指过去，
RESTRICT 会让榜单导入失败，CASCADE 会静默删光展品。何况六个馆里
PEM / 哈佛 / 首博三家根本不在 `cultural_site`（占 6560 件展品）。

```sql
SELECT m.key_name, cs.tier FROM museum m
LEFT JOIN cultural_site cs ON cs.name_key = m.site_key;
```

### on_view 是三态，不是布尔

| 源值 | on_view |
|---|---|
| MFA `IsCurrentlyOnView=True` / 国博「当前在展（基本陈列）」/ 故宫「当前在展」/ 首博「✅ 当前在展」 | `在展` 2514 |
| HAM `On View=False` | `未在展` 40 |
| PEM（源文件无在展字段，只有 `Has Image`）/ 首博「馆藏（在展状态未知）」 | `未知` 6330 |

**不要把 PEM 的「有没有图」当成「在不在展」** —— 那是两回事，源文件没给在展信息。

### 唯一键只能是 (museum_id, source_seq)

展品名在馆内不唯一：故宫「寿山石十八罗汉像之一」同展厅 18 件、
首博「明金冥钱」50 件 —— 本来就是成组文物。只有源表序号能做键。
MFA 的 `Rank` 也不行：它是每个 Tier 段内各自从 1 排的，在 `Master` 页里会撞。

### 译名

```bash
python3 make_translation_skeleton.py --artworks   # 生成/增量更新三个译名表
python3 translate_reasons.py                      # 拼出故宫 976 段评级理由
```

`translate_reasons.py` 把评级理由按分号切成原子短语再拼回去：
976 段只需 423 个翻译单位（词表在 `reason_atoms.tsv` / `reason_families.tsv`），
且同一原子在任何一段里译法一致。改词表等于改所有含该原子的理由。

**注意 `load_translations` 要传本侧的 kind 集合**，否则译名会被当成未知 kind
整批丢掉，且只留一行 warn，极易漏看。

## 十、展品数据的已知问题

- **MFA 文件名叫「1300」，实际只有 203 行有数据**，其余 1097 行是空占位，
  `Master` 页还混入过一行表头。缺口在源文件，不是导入问题。
- **首博 6159 件里 6133 件未确认在展**，尽管文件名是「在展文物清单」——
  来源疑似馆藏总目而非在展清单。已用 `on_view='未知'` 如实记录，不做推断。
- **国博的「展品简介」其实是出土/尺寸元信息**（如「1976年河南安阳市殷墟妇好墓出土」
  「东汉 高45厘米」），名不副实；故宫与首博的该列则是展厅级套话
  （故宫 6 段覆盖 1757 件），靠内容表自动去重。
- **PEM / 哈佛的 `tier_c` 与 `Tier` 不一致**（36 / 86 条），按约定取 `tier_c`；
  故宫同理取「Tier（重评）」。旧评级不入库。
- 国博 45 件、首博 639 件源数据无 Tier，`artwork.tier` 为 NULL。
- 故宫「不可替代性得分」实测 -26 ~ 98，负分来自「去重降分」惩罚项，是合法值。
