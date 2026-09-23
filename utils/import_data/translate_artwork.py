#!/usr/bin/env python3
"""给展品名称与简介补英译。**中文源的馆导出英文版之前必须先跑这个。**

`import_artworks.py` 的规矩是「原文永远保底写入，即使译名表缺这一条」——
所以缺译**不报错**，只是英文版 Excel 里整片是中文，要等 `export_excel.py`
的 CJK 扫描才发现。mfa_boston_ext 导入后实测：名称缺 3476 段、简介缺 4464 段。

**译文写两处，缺一不可**（AGENTS.md 硬性约定）：
  · `translations_artwork_names.csv` / `translations_artwork_text.csv`
    —— 权威源。导入器每次清空重灌，只写在库里的译文重跑一次就没了。
  · `content_text` 的 en 行 —— 让译文立刻生效，不必为了看效果重跑整个导入。

译名表的 key 必须与 `import_artworks.collect_contents` 登记的**逐字一致**：
  artwork_name        -> `artwork.name_key`（源数据原值，**不是展示名**）
  artwork_description -> 简介原文
名称那一条尤其要紧：2026-09-04 把 seq 4434 的展示名改成《历代帝王像》之后，
展示名与 key 已经不同，拿展示名当 key 会让这条译文永远匹配不上。

用法：
    python3 translate_artwork.py --museum mfa_boston_ext --dump            # 看缺多少
    python3 translate_artwork.py --museum mfa_boston_ext --model <型号>     # 译并写两处
"""
from __future__ import annotations

import argparse
import csv
import pathlib
import sys

import meta_lib as M

FILES = {
    "artwork_name": ("translations_artwork_names.csv", "展品名称、馆名与展厅名"),
    "gallery_name": ("translations_artwork_names.csv", "展品名称、馆名与展厅名"),
    "artwork_description": ("translations_artwork_text.csv", "展品简介与评级理由"),
    # 2026-09-23 补：这个 kind 原本两个方向都没覆盖，于是 PEM 新增展品的 181 条门类
    # 一直没有中文，导出时整片回落。它不在 artwork 的 *_key 列上，只能取内容表那一行。
    "artwork_medium": ("translations_artwork_medium.csv", "展品门类与材质"),
}

WHAT = {"artwork_name": "名称", "gallery_name": "展厅名", "artwork_description": "简介",
        "artwork_medium": "门类或材质"}

SYS_ZH2EN = """把博物馆展品的{what}从中文译成英文。这是藏品编目数据，不是宣传文案。

- 已经是英文的部分**原样保留**，只译中文。很多条目是中英混排
  （`《观音菩萨像》Guanyin, Bodhisattva of Compassion（中国，金代…）`），
  英文题名已经在里面了，不要再造一个。
- 人名、机构名用通行原文拼写（「约翰·辛格·沙金」= John Singer Sargent）；
  **认不出是谁就保留中文并把 confidence 填 doubt** —— 造一个不存在的拼写
  比留着中文更糟。
- 朝代、年代按英文习惯：「金代」= Jin dynasty、「12 世纪初」= early 12th century、
  「公元前 883–859 年」= 883–859 BCE
- 材质按文物术语：「绢本设色」= ink and color on silk
- 藏品编号、URL、纯数字原样照抄

**不要增补原文没有的信息，不要解释，不要润色。** 逐条对应返回。"""

SYS_EN2ZH = """把博物馆展品的{what}从英文译成简体中文。这是藏品编目数据，不是宣传文案。

- 人名、机构名按通行中译（John Singleton Copley = 约翰·辛格尔顿·科普利）；
  **没有通行译名就保留原文拼写**，不要音译生造 —— 造一个不存在的中文名
  比留着英文更糟，这种情况 confidence 填 doubt。
- 朝代、年代按中文习惯：`early 19th century` = 19 世纪早期、`about 1800` = 约 1800 年、
  `883–859 BCE` = 公元前 883–859 年
- 材质按文物术语：`ink and color on silk` = 绢本设色、`Lacquered wood, gold leaf` = 髹漆木胎、金箔
- 藏品编号、URL、纯数字原样照抄；**原文里的日文/中文书名与题名原样保留**
  （`支那北京城建築 = Shina Pekinjō Kenchiku` 这类本来就是原题，不要改写）
- 入藏信息保留捐赠人原名与年份：`Gift of John T. Prince, 1846` = 1846 年 John T. Prince 捐赠

**不要增补原文没有的信息，不要解释，不要润色。** 逐条对应返回。"""

SYS_OF = {"zh2en": SYS_ZH2EN, "en2zh": SYS_EN2ZH}
# 目标语种字段名随方向变，schema 也跟着变 —— 字段名写死成 "en" 的话，
# en2zh 方向拿到的就是一个叫 en 的中文，后面每一步都会当它是英文。
SCHEMA_OF = {d: {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {
        "type": "object",
        "properties": {"i": {"type": "integer"}, t: {"type": "string"},
                       "confidence": {"type": "string",
                                      "enum": ["official", "AI", "doubt"]}},
        "required": ["i", t, "confidence"], "additionalProperties": False}}},
    "required": ["items"], "additionalProperties": False,
} for d, t in (("zh2en", "en"), ("en2zh", "zh"))}

CONF_ZH = {"official": "官方", "AI": "AI", "doubt": "存疑"}

# 译名表的 confidence 说的是「这条译文有多可信」，content_text.source 说的是
# 「这条文本从哪来」—— 两件事。
#
# ⚠ **模型声称 official（通行译名）不等于有人校对过。** 早先这里把 官方 映射成
# 「人工校对」，于是 2026-09-23 那 65 条 PEM 中文被记成了人工校对，而它们全是模型
# 当场译的，没有任何人看过。出处一旦夸大，后面读的人就无从分辨哪些真被人核过。
# 「通行译名」这个信号保留在译名表的 confidence 列里，库里只如实记 AI翻译。
SRC_OF = {"官方": "AI翻译", "AI": "AI翻译", "存疑": "存疑"}


def missing(cur, museum: str, direction: str = "zh2en") -> dict[str, list[tuple[int, str]]]:
    """按 kind 取出**需要英译**的内容 -> [(content_id, key 原文)]。

    两种都算需要译：
      ① 压根没有 en 行；
      ② 有 en 行但**里面含中文** —— 那是「原文保底写入」留下的，
         `import_data.build_content_rows` 在译名表缺条目时会把原文两边都写一遍，
         看着有英文其实没有。只查 ① 会漏掉这一类：2026-09-06 实测漏了 67 个
         展品名称，导出时英文版整片带中文才发现。
    """
    if direction == "en2zh":
        return missing_en2zh(cur, museum)
    out: dict[str, list[tuple[int, str]]] = {}
    # 名称：key 取 artwork.name_key，不取展示名
    cur.execute("""SELECT DISTINCT a.name_cid, a.name_key FROM artwork a
        JOIN museum m ON m.id = a.museum_id AND m.key_name = %s
        LEFT JOIN content_text e ON e.content_id = a.name_cid AND e.lang = 'en'
        WHERE a.name_cid IS NOT NULL
          AND (e.text IS NULL OR e.text REGEXP '[一-鿿]')""", (museum,))
    out["artwork_name"] = list(cur.fetchall())
    # 展厅名。**别漏了这一张表** —— 它不在 artwork 上，2026-09-06 第一次导出时
    # 81 个展厅名一段没译，而每件展品都带展厅列，英文版因此报出 14893 处漏中文。
    cur.execute("""SELECT DISTINCT g.name_cid, g.name_key FROM gallery g
        JOIN museum m ON m.id = g.museum_id AND m.key_name = %s
        LEFT JOIN content_text e ON e.content_id = g.name_cid AND e.lang = 'en'
        WHERE g.name_cid IS NOT NULL
          AND (e.text IS NULL OR e.text REGEXP '[一-鿿]')""", (museum,))
    out["gallery_name"] = list(cur.fetchall())
    # 简介：没有 *_key 列，原文就是 zh-CN 那一行
    cur.execute("""SELECT DISTINCT a.description_cid, z.text FROM artwork a
        JOIN museum m ON m.id = a.museum_id AND m.key_name = %s
        JOIN content_text z ON z.content_id = a.description_cid AND z.lang = 'zh-CN'
        LEFT JOIN content_text e ON e.content_id = a.description_cid AND e.lang = 'en'
        WHERE a.description_cid IS NOT NULL
          AND (e.text IS NULL OR e.text REGEXP '[一-鿿]')""", (museum,))
    out["artwork_description"] = list(cur.fetchall())
    cur.execute("""SELECT DISTINCT a.medium_cid, z.text FROM artwork a
        JOIN museum m ON m.id = a.museum_id AND m.key_name = %s
        JOIN content_text z ON z.content_id = a.medium_cid AND z.lang = 'zh-CN'
        LEFT JOIN content_text e ON e.content_id = a.medium_cid AND e.lang = 'en'
        WHERE a.medium_cid IS NOT NULL
          AND (e.text IS NULL OR e.text REGEXP '[一-鿿]')""", (museum,))
    out["artwork_medium"] = list(cur.fetchall())
    return out


# 「缺中文」= 没有 zh-CN 行，或那一行其实是英文。后者有两种：
#   ① 原文保底写入留下的（译名表缺条目时，import_data 会把原文两边都写一遍）；
#   ② **被 detect_lang 误判的** —— 它只要看到汉字就判中文，于是一条引用了日文原书名
#      （`支那北京城建築 = Shina Pekinjō Kenchiku`）的英文编目行被整条存成了 zh-CN。
#      所以除了「完全没有汉字」，还要捞「汉字占比极低的长文本」。
#      阈值定 10% 且只对长度 > 30 的文本生效：短题名里混几个汉字是正常的
#      （`Salem Stories 展厅`），不该被当成英文重译。
_LATIN = ("(z.text IS NULL OR z.text NOT REGEXP '[一-鿿]'"
          " OR (CHAR_LENGTH(z.text) > 30 AND CHAR_LENGTH(z.text)"
          " - CHAR_LENGTH(REGEXP_REPLACE(z.text, '[一-鿿]', ''))"
          " < CHAR_LENGTH(z.text) * 0.1))")


def missing_en2zh(cur, museum: str) -> dict[str, list[tuple[int, str]]]:
    """按 kind 取出**需要中译**的内容 -> [(content_id, 源英文)]。"""
    out: dict[str, list[tuple[int, str]]] = {}
    for kind, sql in (
        ("artwork_name", f"""SELECT DISTINCT a.name_cid, a.name_key FROM artwork a
            JOIN museum m ON m.id = a.museum_id AND m.key_name = %s
            LEFT JOIN content_text z ON z.content_id = a.name_cid AND z.lang = 'zh-CN'
            WHERE a.name_cid IS NOT NULL AND {_LATIN}"""),
        ("gallery_name", f"""SELECT DISTINCT g.name_cid, g.name_key FROM gallery g
            JOIN museum m ON m.id = g.museum_id AND m.key_name = %s
            LEFT JOIN content_text z ON z.content_id = g.name_cid AND z.lang = 'zh-CN'
            WHERE g.name_cid IS NOT NULL AND {_LATIN}"""),
        # 简介没有 *_key 列。源文优先取 en 行；被误判成 zh-CN 的那类没有 en 行，
        # 就拿 zh-CN 里那段英文当源文（写入时会先把它补成 en 行，见 main）
        ("artwork_medium", f"""SELECT DISTINCT a.medium_cid, COALESCE(e.text, z.text)
            FROM artwork a JOIN museum m ON m.id = a.museum_id AND m.key_name = %s
            LEFT JOIN content_text e ON e.content_id = a.medium_cid AND e.lang = 'en'
            LEFT JOIN content_text z ON z.content_id = a.medium_cid AND z.lang = 'zh-CN'
            WHERE a.medium_cid IS NOT NULL AND {_LATIN}
              AND COALESCE(e.text, z.text) IS NOT NULL"""),
        ("artwork_description", f"""SELECT DISTINCT a.description_cid,
                COALESCE(e.text, z.text) FROM artwork a
            JOIN museum m ON m.id = a.museum_id AND m.key_name = %s
            LEFT JOIN content_text e ON e.content_id = a.description_cid AND e.lang = 'en'
            LEFT JOIN content_text z ON z.content_id = a.description_cid AND z.lang = 'zh-CN'
            WHERE a.description_cid IS NOT NULL AND {_LATIN}
              AND COALESCE(e.text, z.text) IS NOT NULL"""),
    ):
        cur.execute(sql, (museum,))
        out[kind] = list(cur.fetchall())
    return out


def read_csv(path: pathlib.Path) -> tuple[list[str], list[dict], set[str]]:
    """返回 (注释行, 数据行, 已有 key 集合)。文件不存在时给空骨架。"""
    if not path.exists():
        return ["# 由 translate_artwork.py 生成\n"], [], set()
    with path.open(encoding="utf-8") as f:
        head = [ln for ln in f if ln.lstrip().startswith("#")]
    with path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader([ln for ln in f if not ln.lstrip().startswith("#")]))
    return head, rows, {(r.get("key") or "").strip() for r in rows}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--museum", required=True)
    ap.add_argument("--dump", action="store_true", help="只报告缺多少，不调 API")
    ap.add_argument("--model", default="")
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--key-file", default="~/.openai_key")
    ap.add_argument("--size", type=int, default=40, help="每次请求译多少条")
    ap.add_argument("--direction", choices=["zh2en", "en2zh"], default="zh2en",
                    help="zh2en=中译英（中文源的馆）；en2zh=英译中（PEM/哈佛这类英文源的馆）")
    ap.add_argument("--provider", choices=["openai", "codex_cli"], default="openai",
                    help="codex_cli = 本机 codex exec 的 ChatGPT 订阅，不需要 API key")
    args = ap.parse_args()
    tgt = "en" if args.direction == "zh2en" else "zh"
    lang = "en" if args.direction == "zh2en" else "zh-CN"

    base = pathlib.Path(__file__).resolve().parent
    conn = M.connect()
    cur = conn.cursor()
    need = missing(cur, args.museum, args.direction)
    word = "英译" if args.direction == "zh2en" else "中译"
    for kind, rows in need.items():
        print(f"{kind:22s} 缺{word} {len(rows)} 段")
    if args.dump:
        return
    if not args.model:
        sys.exit("需要 --model")
    if not any(need.values()):
        print("没有要译的。")
        return

    import audit_meta as A
    if args.provider == "codex_cli":
        import codex_cli
        if not codex_cli.available():
            sys.exit("找不到 codex 可执行文件")
        A.CODEX_CLI = args.model
        client = None
    else:
        client = A.LazyClient(args.key_file)
    effort = A.norm_effort(args.effort)

    for kind, rows in need.items():
        if not rows:
            continue
        fname, desc = FILES[kind]
        path = base / fname
        head, csv_rows, have = read_csv(path)
        what = WHAT.get(kind, "文本")
        n_doubt = 0
        for i in range(0, len(rows), args.size):
            chunk = rows[i:i + args.size]
            # 用序号对齐而不是原文：简介动辄上百字，让模型回抄一遍原文既费
            # token 又容易被改动一两个字符，那样就对不上了。
            into = "英文" if args.direction == "zh2en" else "简体中文"
            user = (f"请逐条译成{into}，共 {len(chunk)} 条：\n"
                    + "\n".join(f"[{j}] {txt}" for j, (_, txt) in enumerate(chunk)))
            # 漏译的校验交给 llm_cache 在**写缓存之前**做：早先是拿到结果再查，
            # 残缺答案已经进了缓存，重跑必然命中同一条、在同一处再崩。
            want = set(range(len(chunk)))
            data = A.ask(client, args.model, SYS_OF[args.direction].format(what=what),
                         user, f"trans_{kind}", SCHEMA_OF[args.direction], effort,
                         museum_key=args.museum,
                         scope=f"{kind} {i + 1}-{i + len(chunk)}",
                         validate=lambda d, w=want: w <= {x["i"] for x in d["items"]})
            got = {d["i"]: d for d in data["items"]}
            miss = set(range(len(chunk))) - set(got)
            if miss:
                raise SystemExit(f"{kind} 漏译 {len(miss)} 条（下标 {sorted(miss)[:5]}）")
            for j, (cid, key) in enumerate(chunk):
                d = got[j]
                conf = CONF_ZH.get(d["confidence"], "AI")
                if d["confidence"] == "doubt":
                    n_doubt += 1
                # ⓪ en2zh 方向：源英文可能只存在于一条被误判成 zh-CN 的行里
                # （detect_lang 见到汉字就判中文）。直接往 zh-CN 写中文会把英文原文冲掉，
                # 所以先把源文补成 en 行；已有 en 行时这句是空操作。
                if args.direction == "en2zh":
                    cur.execute("INSERT INTO content_text (content_id, lang, text, source)"
                                " VALUES (%s,'en',%s,'原始')"
                                " ON DUPLICATE KEY UPDATE content_id=content_id", (cid, key))
                # ① 立刻写库，让译文生效
                cur.execute("INSERT INTO content_text (content_id, lang, text, source)"
                            " VALUES (%s,%s,%s,%s)"
                            " ON DUPLICATE KEY UPDATE text=VALUES(text), source=VALUES(source)",
                            (cid, lang, d[tgt], SRC_OF[conf]))
                # ② 落译名表，重灌后仍在。key 恒为原文那一侧
                if key not in have:
                    row = ({"zh": key, "en": d["en"]} if args.direction == "zh2en"
                           else {"zh": d["zh"], "en": key})
                    csv_rows.append({"kind": kind, "key": key, **row, "confidence": conf})
                    have.add(key)
            conn.commit()
            print(f"  {kind} {min(i + args.size, len(rows))}/{len(rows)}")
        cols = ["kind", "key", "zh", "en", "confidence"]
        with path.open("w", encoding="utf-8", newline="") as f:
            f.writelines(head)
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore",
                               lineterminator="\n")
            w.writeheader()
            w.writerows(csv_rows)
        print(f"  -> {fname} 共 {len(csv_rows)} 行"
              + (f"，其中本轮 {n_doubt} 条标了存疑" if n_doubt else ""))
    conn.commit()
    print("\n译文已写入 content_text 与译名表两处。")


if __name__ == "__main__":
    main()
