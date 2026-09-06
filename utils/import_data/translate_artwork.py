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
}

WHAT = {"artwork_name": "名称", "gallery_name": "展厅名", "artwork_description": "简介"}

SYS = """把博物馆展品的{what}从中文译成英文。这是藏品编目数据，不是宣传文案。

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

SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {
        "type": "object",
        "properties": {"i": {"type": "integer"}, "en": {"type": "string"},
                       "confidence": {"type": "string",
                                      "enum": ["official", "AI", "doubt"]}},
        "required": ["i", "en", "confidence"], "additionalProperties": False}}},
    "required": ["items"], "additionalProperties": False,
}

CONF_ZH = {"official": "官方", "AI": "AI", "doubt": "存疑"}


def missing(cur, museum: str) -> dict[str, list[tuple[int, str]]]:
    """按 kind 取出**需要英译**的内容 -> [(content_id, key 原文)]。

    两种都算需要译：
      ① 压根没有 en 行；
      ② 有 en 行但**里面含中文** —— 那是「原文保底写入」留下的，
         `import_data.build_content_rows` 在译名表缺条目时会把原文两边都写一遍，
         看着有英文其实没有。只查 ① 会漏掉这一类：2026-09-06 实测漏了 67 个
         展品名称，导出时英文版整片带中文才发现。
    """
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
    args = ap.parse_args()

    base = pathlib.Path(__file__).resolve().parent
    conn = M.connect()
    cur = conn.cursor()
    need = missing(cur, args.museum)
    for kind, rows in need.items():
        print(f"{kind:22s} 缺英译 {len(rows)} 段")
    if args.dump:
        return
    if not args.model:
        sys.exit("需要 --model")
    if not any(need.values()):
        print("没有要译的。")
        return

    import audit_meta as A
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
            user = (f"请逐条译成英文，共 {len(chunk)} 条：\n"
                    + "\n".join(f"[{j}] {txt}" for j, (_, txt) in enumerate(chunk)))
            data = A.ask(client, args.model, SYS.format(what=what), user,
                         f"trans_{kind}", SCHEMA, effort, museum_key=args.museum,
                         scope=f"{kind} {i + 1}-{i + len(chunk)}")
            got = {d["i"]: d for d in data["items"]}
            miss = set(range(len(chunk))) - set(got)
            if miss:
                raise SystemExit(f"{kind} 漏译 {len(miss)} 条（下标 {sorted(miss)[:5]}）")
            for j, (cid, key) in enumerate(chunk):
                d = got[j]
                conf = CONF_ZH.get(d["confidence"], "AI")
                if d["confidence"] == "doubt":
                    n_doubt += 1
                # ① 立刻写库，让译文生效
                cur.execute("INSERT INTO content_text (content_id, lang, text, source)"
                            " VALUES (%s,'en',%s,%s)"
                            " ON DUPLICATE KEY UPDATE text=VALUES(text), source=VALUES(source)",
                            (cid, d["en"], "AI翻译" if conf != "官方" else "人工校对"))
                # ② 落译名表，重灌后仍在
                if key not in have:
                    csv_rows.append({"kind": kind, "key": key, "zh": key,
                                     "en": d["en"], "confidence": conf})
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
