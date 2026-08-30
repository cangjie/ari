#!/usr/bin/env python3
"""灌入 metadata 的键字典（meta_key）。

metadata 是纯 key-value：每件展品收集若干条「键 = 值」，键和值都是多语种内容，
都存进 content / content_text。本脚本只负责**键**这一半 —— 值由各自的填充脚本
按需写入，用到什么键就引哪个键。

**这不是模版。** 字典不规定哪件展品该有哪些键，不校验，不分组。它存在的唯一
理由是 AGENTS.md 数据库约定第 2 条：内容ID保证不了文本不重复，「年代」若被
写成两个 content 行，程序按键取值时就会漏。字典把「一个规范键名 <-> 一段
多语种显示名」钉死，唯一约束落在 key_name 上。

**新增键不必改这个脚本**，直接往 meta_key 插一行即可；此处只是一份常用起手集，
覆盖两类需求：
  编目事实   —— 展品本身是什么（年代、材质、作者、尺寸、工艺……）
  参观规划   —— V3.0 第九、十节算 VisitScore 与路线要用但库里没有的量

content ID 段见 schema_meta.sql 文件头：本数据集占 2,000,000 段。

用法：
    python3 meta_seed.py --dry-run
    python3 meta_seed.py
"""
from __future__ import annotations

import argparse
import os
import sys

import pymysql

CONTENT_ID_BASE = 2_000_000
KIND_KEY = "meta_key_name"

# (key_name, 中文, English, 备注)
KEYS = [
    # ---------- 编目事实 ----------
    ("period",            "年代",         "Period",                  "朝代或世纪，如「清」「19世纪」"),
    ("date_text",         "确切纪年",     "Date",                    "有确切纪年时填，如「宣德三年」「1889」"),
    ("material",          "材质",         "Material",                "可多值：木、漆、金各占一行"),
    ("technique",         "工艺",         "Technique",               "制作或装饰工艺"),
    ("object_form",       "器型·类别",    "Object Form",             "器物形制或作品类型，自由文本"),
    ("artist",            "作者",         "Artist",                  "画家、工匠、作坊；可多值"),
    ("school",            "流派·画派",    "School",                  ""),
    ("cultural_context",  "文化归属",     "Cultural Attribution",    "如「徽州」「大和民族」「毛利」"),
    ("origin_place",      "产地",         "Place of Origin",         ""),
    ("excavation_place",  "出土地",       "Excavation Site",         "含出土年份更好"),
    ("accession_no",      "馆藏编号",     "Accession Number",        "馆方编号，原样照录"),
    ("dimensions",        "尺寸",         "Dimensions",              "整段描述；拆分值另见高/宽/深/直径"),
    ("height_cm",         "高",           "Height",                  "单位 cm，数值另存 value_num"),
    ("width_cm",          "宽",           "Width",                   "单位 cm"),
    ("depth_cm",          "深",           "Depth",                   "单位 cm"),
    ("diameter_cm",       "直径",         "Diameter",                "单位 cm"),
    ("weight_kg",         "重量",         "Weight",                  "单位 kg"),
    ("support",           "载体",         "Support",                 "如布面、绢本、纸本、木板"),
    ("mounting",          "装裱形式",     "Mounting",                "卷、轴、册、镜心等"),
    ("inscription",       "铭文·题识",    "Inscription",             "铭文、题跋、签名"),
    ("mark",              "款识",         "Mark",                    "年款、堂号、作坊款"),
    ("kiln",              "窑口",         "Kiln",                    ""),
    ("glaze",             "釉色",         "Glaze",                   ""),
    ("provenance",        "流传经历",     "Provenance",              "递藏、入藏途径"),
    ("condition",         "保存状况",     "Condition",               "完整、残件、修复情况"),
    ("subject",           "题材",         "Subject",                 "描绘或表现的内容"),
    # ---------- 参观规划：V3.0 第九、十节 ----------
    ("viewing_minutes",   "建议观看时长", "Suggested Viewing Time",  "分钟；RouteUtility 的分母之一"),
    ("floor",             "楼层",         "Floor",                   ""),
    ("zone",              "区位",         "Zone",                    "展厅内的分区"),
    ("walk_minutes",      "自入口步行分钟", "Walk Time from Entrance", "分钟；用于估算新增步行时间"),
    ("needs_reservation", "是否需预约",   "Requires Reservation",    "是/否"),
    ("is_rotating",       "是否轮展",     "On Rotation",             "是/否；影响可观看门槛"),
    ("accessible",        "无障碍可达",   "Wheelchair Accessible",   "是/否"),
    ("gate_g",            "开放与可观看门槛 G", "Visibility Gate (G)", "0–1；不可观看时为 0，Core 与 Tier 不变"),
    ("mod_condition_mc",  "条件修正 Mc",  "Condition Modifier (Mc)", "季节、天气、修缮、光线；算法未规定范围"),
    ("mod_route_mr",      "路线修正 Mr",  "Route Modifier (Mr)",     "绕路、拥挤、叙事衔接、同类重复"),
    # Ma：V3.0 第九节明确八类观众，范围 -0.5 ~ +0.5
    ("ma_general",              "观众修正·普通游客",   "Audience Modifier - General Visitor",      "-0.5 ~ +0.5"),
    ("ma_chinese",              "观众修正·中国游客",   "Audience Modifier - Chinese Visitor",      "-0.5 ~ +0.5"),
    ("ma_family",               "观众修正·家庭",       "Audience Modifier - Family",               "-0.5 ~ +0.5"),
    ("ma_kids",                 "观众修正·儿童",       "Audience Modifier - Kids",                 "-0.5 ~ +0.5"),
    ("ma_art_lover",            "观众修正·艺术爱好者", "Audience Modifier - Art Lover",            "-0.5 ~ +0.5"),
    ("ma_history_lover",        "观众修正·历史爱好者", "Audience Modifier - History Lover",        "-0.5 ~ +0.5"),
    ("ma_architecture_lover",   "观众修正·建筑爱好者", "Audience Modifier - Architecture Lover",   "-0.5 ~ +0.5"),
    ("ma_religious_heritage",   "观众修正·宗教遗产参观者", "Audience Modifier - Religious Heritage Visitor", "-0.5 ~ +0.5"),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="artwork_meta 非空时仍重灌字典（被引用的键会因外键失败）")
    args = ap.parse_args()

    conn = pymysql.connect(read_default_file=os.path.expanduser("~/.my.cnf"),
                           charset="utf8mb4", autocommit=False)
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM artwork_meta")
    used = cur.fetchone()[0]
    if used and not args.force:
        sys.exit(f"artwork_meta 已有 {used} 行取值在引用这些键，重灌字典会被外键挡下。"
                 f"要新增键请直接 INSERT，不要重跑本脚本；确实要重来请加 --force")

    cur.execute("DELETE FROM meta_key")
    # 只删键名，不碰值：meta_value_text 归各填充脚本管
    cur.execute(f"DELETE FROM content_text WHERE content_id IN "
                f"(SELECT id FROM content WHERE kind = '{KIND_KEY}')")
    cur.execute(f"DELETE FROM content WHERE kind = '{KIND_KEY}'")

    contents, texts, rows = [], [], []
    cid = CONTENT_ID_BASE
    for i, (k, zh, en, note) in enumerate(KEYS, 1):
        cid += 1
        contents.append((cid, KIND_KEY))
        # content_text.source 是固定 ENUM（原始/AI翻译/存疑/人工校对）。
        # 中文是本脚本拟定的原文记「原始」；英文由模型生成、尚无人校对记「AI翻译」。
        texts.append((cid, "zh-CN", zh, "原始"))
        texts.append((cid, "en", en, "AI翻译"))
        rows.append((k, cid, note or None, i * 10))

    print(f"键 {len(rows)} 个；content 新增 {len(contents)} 条 "
          f"（ID {CONTENT_ID_BASE + 1}–{cid}），content_text {len(texts)} 行")

    cur.executemany("INSERT INTO content (id, kind) VALUES (%s,%s)", contents)
    cur.executemany("INSERT INTO content_text (content_id, lang, text, source)"
                    " VALUES (%s,%s,%s,%s)", texts)
    cur.executemany("INSERT INTO meta_key (key_name, name_cid, note, sort_order)"
                    " VALUES (%s,%s,%s,%s)", rows)

    if args.dry_run:
        conn.rollback(); print("\n--dry-run：已回滚")
    else:
        conn.commit(); print("\n已提交")
    conn.close()


if __name__ == "__main__":
    main()
