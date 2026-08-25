#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
按源 Excel 生成 / 更新三个译名表骨架。

从 Excel 抽出全部去重原文，原文那一侧的语种列填好，另一侧留空待译。
**合并式更新**：已填的译文原样保留，只追加新出现的原文；源数据里已消失的
条目会被移出并报告，不会静默丢弃 —— 那通常意味着 Excel 改了名字。

用法：
  python make_translation_skeleton.py                     # 就地更新三个 CSV
  python make_translation_skeleton.py --dry-run           # 只报告会怎么变，不写文件

依赖：openpyxl
"""

import argparse
import csv
import os

from import_data import (LANG_ZH, collect_contents, detect_lang, load_overrides,
                         load_translations, read_excel)

# 按复核负担拆分：名称要核准专名，长理由要核语句通顺，枚举几乎不用核
FILES = {
    "translations_city.csv": (["city_name", "country_name"], "城市名与国家名"),
    "translations_site.csv": (["site_name"], "文化点位名称"),
    "translations_text.csv": (["tier_reason", "change_reason",
                               "collection_type", "data_source"], "定级理由、变动原因、门类与数据来源"),
}

HEADER = ["kind", "key", "zh", "en", "confidence"]

BANNER = """\
# {desc}
#
# key        —— 原文，去重键，须与源 Excel 逐字一致，不要改
# zh / en    —— 两个语种的文本；原文那一侧已填好，另一侧待译
# confidence —— 官方 / AI / 存疑，只描述「译出来的那一半」
#                官方 = 通行的既定译名（Louvre = 卢浮宫）
#                AI   = 机器翻译，正常可用
#                存疑 = 拿不准，优先人工复核（grep 存疑 即可捞出）
#
# 本文件由 make_translation_skeleton.py 生成与增量更新，可直接手工编辑。
"""


def read_existing(path, kinds=None):
    """读回已填内容 -> {(kind, key): (zh, en, confidence)}"""
    if not os.path.exists(path):
        return {}
    return load_translations([path], kinds) if kinds else load_translations([path])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--excel", default="500cities_tier_v2.xlsx")
    ap.add_argument("--overrides", default="dual_attribute_overrides.csv")
    ap.add_argument("--dry-run", action="store_true", help="只报告，不写文件")
    ap.add_argument("--artworks", action="store_true",
                    help="改为生成展品译名表（artworks/ 下六个源文件）")
    args = ap.parse_args()

    if args.artworks:
        build_artworks(args.dry_run)
        return

    cities, sites, changes = read_excel(args.excel, load_overrides(args.overrides))
    buckets = collect_contents(cities, sites, changes)

    for path, (kinds, desc) in FILES.items():
        existing = read_existing(path)
        rows, kept, added = [], 0, 0
        for kind in kinds:
            for key in buckets[kind]:
                lang = detect_lang(key)
                zh, en, conf = existing.get((kind, key), (None, None, ""))
                if zh or en:
                    kept += 1
                else:
                    added += 1
                # 原文那一侧始终以 Excel 为准回填，避免手滑改坏了对不上
                if lang == LANG_ZH:
                    zh = key
                else:
                    en = key
                rows.append([kind, key, zh or "", en or "", conf])

        live = {(k, key) for k in kinds for key in buckets[k]}
        dropped = [k for k in existing if k not in live]

        todo = sum(1 for r in rows if not r[2] or not r[3])
        print(f"{path}：{len(rows)} 段（保留已填 {kept} / 新增 {added} / 仍缺译 {todo}）"
              + (f"，移出 {len(dropped)} 条源数据中已消失的：{dropped[:3]}" if dropped else ""))

        if args.dry_run:
            continue
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(BANNER.format(desc=desc))
            w = csv.writer(f)
            w.writerow(HEADER)
            w.writerows(rows)


# ---------------------------------------------------------------- 展品译名表
ARTWORK_FILES = {
    "translations_artwork_names.csv": (["artwork_name", "museum_name",
                                        "gallery_name", "gallery_theme"],
                                       "展品名称、馆名与展厅名"),
    "translations_artwork_text.csv": (["artwork_description", "artwork_tier_reason"],
                                      "展品简介与故宫评级理由"),
    "translations_artwork_medium.csv": (["artwork_medium"], "门类 / 材质 / 媒材"),
}


def build_artworks(dry_run=False):
    """按 artworks/ 下六个源文件生成 / 更新展品译名表骨架。"""
    import import_artworks as ia

    items, galleries = ia.read_all(ia.ARTWORK_DIR)
    buckets = ia.collect_contents(items, galleries)
    pairs = ia.collect_pairs(items)      # 源数据自带的中英对照，不必再译

    for path, (kinds, desc) in ARTWORK_FILES.items():
        existing = read_existing(path, ia.CONTENT_KINDS)
        rows, kept, added, skipped = [], 0, 0, 0
        for kind in kinds:
            for key in buckets[kind]:
                if (kind, key) in pairs:
                    skipped += 1         # 源文件已给出另一语种，无需人译
                    continue
                lang = detect_lang(key)
                zh, en, conf = existing.get((kind, key), (None, None, ""))
                if zh or en:
                    kept += 1
                else:
                    added += 1
                if lang == LANG_ZH:
                    zh = key
                else:
                    en = key
                rows.append([kind, key, zh or "", en or "", conf])

        live = {(k, key) for k in kinds for key in buckets[k]}
        dropped = [k for k in existing if k not in live]
        todo = sum(1 for r in rows if not r[2] or not r[3])
        print(f"{path}：{len(rows)} 段待译（保留已填 {kept} / 新增 {added} / 仍缺译 {todo}）"
              f"，源数据自带双语跳过 {skipped}"
              + (f"，移出 {len(dropped)} 条已消失的" if dropped else ""))

        if dry_run:
            continue
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(BANNER.format(desc=desc))
            w = csv.writer(f)
            w.writerow(HEADER)
            w.writerows(rows)


if __name__ == "__main__":
    main()
