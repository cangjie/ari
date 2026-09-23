#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 PEM 的展厅表从「展品主题标签」换成官网的实体展厅，**定向迁移**，不重灌。

为什么不直接跑 `import_artworks.py`：那个脚本是全表重灌，`DELETE FROM artwork`
清的是全表，13348 件、7 个馆的 `artwork.id` 与 `museum.id` 全部重新发号，
之后按 AGENTS.md 第 6 条还得补跑四个已评级馆的 `--apply-tier` 和
`llm_cache.py --refresh-ids`，再重导 Excel。为了 PEM 的 26 个展厅牵动这一串，
风险和收益不成比例。

所以是两条腿：
  · `import_artworks.py` + `pem_gallery_data.py` 已经改好 —— 管**将来**，
    下次谁跑全量重灌，得到的是同一个结果；
  · 本脚本 —— 管**现在**，只动 PEM 的展厅与展品的 gallery_id。
两条腿的结果必须一致，验证方式见仓库 PROGRESS 对应条目。

用法（在服务器上，SQL 从标准输出接走）：
    python3 migrate_pem_galleries.py --content-id-base 1017658 > migrate.sql
    sudo mysql --defaults-file=/etc/mysql/debian.cnf ari < migrate.sql

生成的 SQL 是一个存储过程，整体在一个事务里，任一前置/后置断言不成立就
ROLLBACK 并报错 —— 不存在「改了一半」的中间态。
"""

import argparse
import sys

import pem_gallery_data as P

LANG_ZH, LANG_EN = "zh-CN", "en"


def q(v):
    """SQL 字符串字面量。"""
    if v is None:
        return "NULL"
    return "'" + str(v).replace("\\", "\\\\").replace("'", "''") + "'"


def assert_eq(expr, want, what):
    """生成一条「取值必须等于 want，否则带实际值中止」的断言。"""
    return f"""
  SELECT {expr} INTO v_n;
  IF v_n <> {want} THEN
    SET @msg = CONCAT('[中止] {what}：预期 {want}，实际 ', v_n);
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = @msg;
  END IF;"""


def build(base):
    g_list = list(P.GALLERIES)
    # 内容ID 逐个显式分配，与导入器同段（1,000,000 起的展品段）
    cid = {g["name_en"]: base + i for i, g in enumerate(g_list)}

    targets = sorted({t for t in P.LABEL_MAP.values() if t})
    excluded = sorted(k for k, v in P.LABEL_MAP.items() if v is None)
    # 每个实体展厅应当收到多少件 —— 由映射本身推不出来，交给后置断言从库里核
    old_labels = sorted(P.LABEL_MAP)

    out = []
    w = out.append

    w("-- 由 migrate_pem_galleries.py 生成，勿手工编辑。")
    w(f"-- 新展厅名内容ID：{base} – {base + len(g_list) - 1}")
    w("")
    w("DROP PROCEDURE IF EXISTS ari_migrate_pem_galleries;")
    w("DELIMITER $$")
    w("CREATE PROCEDURE ari_migrate_pem_galleries()")
    w("BEGIN")
    w("  DECLARE v_mid INT UNSIGNED DEFAULT NULL;")
    w("  DECLARE v_n BIGINT DEFAULT NULL;")
    w("  DECLARE EXIT HANDLER FOR SQLEXCEPTION")
    w("  BEGIN")
    w("    ROLLBACK;")
    w("    RESIGNAL;")
    w("  END;")
    w("")
    w("  START TRANSACTION;")
    w("")
    w("  SELECT id INTO v_mid FROM museum WHERE key_name = 'pem';")
    w("  IF v_mid IS NULL THEN")
    w("    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = '[中止] museum 里没有 pem';")
    w("  END IF;")
    w("")
    w("  -- ---------- 前置断言：库必须正是我们以为的样子 ----------")
    w(assert_eq("(SELECT COUNT(*) FROM gallery WHERE museum_id = v_mid)", 23,
                "迁移前 PEM 展厅数"))
    w(assert_eq("(SELECT COUNT(*) FROM artwork WHERE museum_id = v_mid)", 196,
                "PEM 展品数"))
    olds = ", ".join(q(k) for k in old_labels)
    w(assert_eq(
        f"(SELECT COUNT(*) FROM gallery WHERE museum_id = v_mid AND name_key IN ({olds}))",
        len(old_labels), "迁移前 PEM 展厅名与 LABEL_MAP 的键对得上的个数"))
    news = ", ".join(q(g["name_en"]) for g in g_list)
    w(assert_eq(f"(SELECT COUNT(*) FROM gallery WHERE name_key IN ({news}))", 0,
                "新展厅名在 gallery 表里预先存在的个数（含其它馆）"))
    w(assert_eq(f"(SELECT COUNT(*) FROM content WHERE id BETWEEN {base} AND {base + len(g_list) - 1})",
                0, "拟占用的内容ID区间里已存在的行数"))
    w("")
    w("  -- ---------- 1/5 新展厅名的内容与双语文本 ----------")
    w("  INSERT INTO content (id, kind) VALUES")
    w(",\n".join(f"    ({cid[g['name_en']]}, 'gallery_name')" for g in g_list) + ";")
    w("")
    w("  -- 英文是源数据（原始）；中文来自源表的「中文参考」列，是整理出来的译名，")
    w("  -- 不是官方中文，如实标成 AI翻译。同 translations_artwork_names.csv 里那 26 行。")
    w("  INSERT INTO content_text (content_id, lang, text, source) VALUES")
    rows = []
    for g in g_list:
        c = cid[g["name_en"]]
        rows.append(f"    ({c}, {q(LANG_EN)}, {q(g['name_en'])}, '原始')")
        rows.append(f"    ({c}, {q(LANG_ZH)}, {q(g['name_zh'])}, 'AI翻译')")
    w(",\n".join(rows) + ";")
    w("")
    w("  -- ---------- 2/5 26 个实体展厅 ----------")
    w("  -- 整份基准表入库，包括没有展品落在上面的 20 个：它是 PEM 的展厅清单，")
    w("  -- 不是展品的副产品。theme/location/minutes/url 源表不提供，留 NULL。")
    w("  INSERT INTO gallery (museum_id, name_key, name_cid) VALUES")
    w(",\n".join(f"    (v_mid, {q(g['name_en'])}, {cid[g['name_en']]})" for g in g_list) + ";")
    w("")
    w("  -- ---------- 3/5 展品改挂到实体展厅 ----------")
    for tgt in targets:
        srcs = sorted(k for k, v in P.LABEL_MAP.items() if v == tgt)
        w(f"  -- {' + '.join(srcs)}  ->  {tgt}")
        w("  UPDATE artwork a")
        w("    JOIN gallery og ON og.id = a.gallery_id AND og.museum_id = v_mid")
        w(f"    JOIN gallery ng ON ng.museum_id = v_mid AND ng.name_key = {q(tgt)}")
        w("    SET a.gallery_id = ng.id")
        w(f"  WHERE og.name_key IN ({', '.join(q(s) for s in srcs)});")
        w("")
    w("  -- 不对应任何实体房间的标签：置 NULL。官网没有证明它是独立展厅，")
    w("  -- 就不据此填展厅（用户 2026-09-21 定）。")
    w("  UPDATE artwork a")
    w("    JOIN gallery og ON og.id = a.gallery_id AND og.museum_id = v_mid")
    w("    SET a.gallery_id = NULL")
    w(f"  WHERE og.name_key IN ({', '.join(q(k) for k in excluded)});")
    w("")
    w("  -- ---------- 4/5 删掉 23 个旧标签 ----------")
    w("  -- 先断言没有展品还挂在上面。artwork.gallery_id 的外键是 ON DELETE SET NULL，")
    w("  -- 漏掉哪个标签，这里直接删就会把它的展品静默变成 NULL —— 正是要防的那种。")
    w(assert_eq(
        f"(SELECT COUNT(*) FROM artwork a JOIN gallery g ON g.id = a.gallery_id"
        f" WHERE g.museum_id = v_mid AND g.name_key IN ({olds}))", 0,
        "删除前仍挂在旧标签上的展品数"))
    w("")
    w("  DROP TEMPORARY TABLE IF EXISTS tmp_old_cid;")
    w("  CREATE TEMPORARY TABLE tmp_old_cid (cid INT UNSIGNED PRIMARY KEY);")
    w(f"  INSERT INTO tmp_old_cid (cid) SELECT DISTINCT name_cid FROM gallery"
      f"   WHERE museum_id = v_mid AND name_key IN ({olds});")
    w(f"  DELETE FROM gallery WHERE museum_id = v_mid AND name_key IN ({olds});")
    w("")
    w("  -- 旧展厅名的内容行也一并回收，但只回收没有任何展厅再引用的")
    w("  DELETE ct FROM content_text ct JOIN tmp_old_cid t ON t.cid = ct.content_id")
    w("  WHERE NOT EXISTS (SELECT 1 FROM gallery g WHERE g.name_cid = ct.content_id);")
    w("  DELETE c FROM content c JOIN tmp_old_cid t ON t.cid = c.id")
    w("  WHERE NOT EXISTS (SELECT 1 FROM gallery g WHERE g.name_cid = c.id);")
    w("  DROP TEMPORARY TABLE tmp_old_cid;")
    w("")
    w("  -- ---------- 5/5 后置断言 ----------")
    w(assert_eq("(SELECT COUNT(*) FROM gallery WHERE museum_id = v_mid)",
                len(g_list), "迁移后 PEM 展厅数"))
    w(assert_eq("(SELECT COUNT(*) FROM artwork WHERE museum_id = v_mid)", 196,
                "迁移后 PEM 展品数（不该有增减）"))
    w(assert_eq("(SELECT COUNT(*) FROM artwork WHERE museum_id = v_mid AND gallery_id IS NOT NULL)",
                106, "迁移后挂上实体展厅的展品数"))
    w(assert_eq("(SELECT COUNT(*) FROM artwork WHERE museum_id = v_mid AND gallery_id IS NULL)",
                90, "迁移后展厅为空的展品数"))
    w(assert_eq(
        "(SELECT COUNT(*) FROM gallery g JOIN content_text ct ON ct.content_id = g.name_cid"
        " WHERE g.museum_id = v_mid)", len(g_list) * 2,
        "迁移后 PEM 展厅名的文本行数（26 个展厅 × 中英 2 条）"))
    w(assert_eq(
        "(SELECT COUNT(*) FROM gallery g JOIN content_text ct ON ct.content_id = g.name_cid"
        " AND ct.lang = 'en' WHERE g.museum_id = v_mid AND ct.text REGEXP '[一-鿿]')", 0,
        "英文侧混入中文的展厅名数（零回落）"))
    w("")
    w("  COMMIT;")
    w("END$$")
    w("DELIMITER ;")
    w("")
    w("CALL ari_migrate_pem_galleries();")
    w("DROP PROCEDURE ari_migrate_pem_galleries;")
    w("")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--content-id-base", type=int, required=True,
                    help="新展厅名占用的内容ID起点。必须落在展品段（1,000,000–1,999,999）"
                         "的空档里，且区间内不能有现存行 —— 生成的 SQL 会先断言这一点")
    a = ap.parse_args()
    base = a.content_id_base
    if not 1_000_000 <= base <= 1_999_999 - len(P.GALLERIES):
        sys.exit(f"[fatal] --content-id-base {base} 不在展品段 1,000,000–1,999,999 内。"
                 f"metadata 段从 2,000,000 起，撞上去会和 meta_seed.py 抢ID。")
    sys.stdout.write(build(base))


if __name__ == "__main__":
    main()
