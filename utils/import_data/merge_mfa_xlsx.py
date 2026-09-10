#!/usr/bin/env python3
"""把 MFA 两份导出的 Excel 合成一份。**只动文件，不碰数据库。**

**为什么会有两份（2026-09-10）**

`mfa_boston`（203 件）与 `mfa_boston_ext`（4464 件）是同一个馆的两批导入，
库里是两个 museum key，所以 `export_excel.py` 导出成了两个文件。用户指出
「本来就不存在什么扩充清单」—— 对外只该有一个波士顿美术馆。

库层面的合并要迁移约 4.7 万行派生数据（软键 `(museum_key, source_seq)` 无外键，
迁错了不报错），是另一件事；这里只做导出结果的合并。

**重复以 ext 为准**（用户 2026-09-10 定）。16 对重复由 `merge_confirm.py` 判定：
启发式召回（名称 token 权重 2.0、简介 0.6）+ 模型逐对确认。不能只靠召回分数 ——
「神奈川冲浪里」会召回「赤富士」，同一作者的不同作品，必须由模型判掉。
判定结果落在 `merge_pairs.json`，其中 old→ext 的 16 对在合并时**丢弃 old 那条**。

各 sheet 的合并方式：
  S/A/B/C/无评级   两边行拼接（ext 在前），列结构相同
  metadata明细     同上
  元数据审计汇总    **不能拼接** —— 它是「指标 / 值」的汇总块，两份的同名指标
                   拼在一起会出现两行「对象总数」。这里重新算一遍。
"""
import json, pathlib, sys
import openpyxl
from openpyxl.utils import get_column_letter

SRC = {
    "zh-CN": ("exports/zh-CN/展品_波士顿美术馆.xlsx",
              "exports/zh-CN/展品_波士顿美术馆（扩充清单）.xlsx",
              "exports/zh-CN/展品_波士顿美术馆_合并.xlsx"),
    "en": ("exports/en/Artworks - Museum of Fine Arts, Boston.xlsx",
           "exports/en/Artworks - Museum of Fine Arts, Boston (Extended List).xlsx",
           "exports/en/Artworks - Museum of Fine Arts, Boston (Merged).xlsx"),
}
ROW_SHEETS_ZH = ("S", "A", "B", "C", "无评级", "metadata明细")
SUMMARY_ZH = ("元数据审计汇总", "Metadata Audit Summary")


def dup_old_seqs() -> set[int]:
    """被判为与 ext 重复、因而要从 old 侧丢弃的 source_seq。"""
    p = pathlib.Path("merge_pairs.json")
    if not p.exists():
        sys.exit("缺 merge_pairs.json —— 先跑 merge_confirm.py")
    return {x["old_seq"] for x in json.loads(p.read_text(encoding="utf-8"))
            if x["same_as_ext_seq"]}


SEQ_HEADERS = ("序号", "源序号", "No.", "source_seq", "Source Seq")


def seq_col(ws) -> int:
    """找出序号列的下标（1 起）。**找不到就报错退出，绝不返回 None。**

    第一版返回 None、调用方遇 None 就跳过过滤 —— 于是英文版表头叫「No.」
    而不是「序号」时，16 件重复**一件都没被剔除，而且不报错**
    （2026-09-10 实测：英文版 S 表 ext 38 + old 15 全进去了）。
    静默降级比崩掉危险得多：中文版对了、英文版错了，两个文件件数不一致，
    不逐个数根本看不出来。
    """
    hdr = [str(c.value or "").strip() for c in next(ws.iter_rows(min_row=1, max_row=1))]
    for i, h in enumerate(hdr, 1):
        if h in SEQ_HEADERS:
            return i
    raise SystemExit(f"sheet「{ws.title}」找不到序号列，表头是 {hdr[:8]}；"
                     f"认得的列名：{SEQ_HEADERS}")


def main() -> None:
    drop = dup_old_seqs()
    print(f"重复（以 ext 为准，丢弃 old 侧）：{len(drop)} 件 -> seq {sorted(drop)}")
    for lang, (f_old, f_ext, f_out) in SRC.items():
        po, pe = pathlib.Path(f_old), pathlib.Path(f_ext)
        if not (po.exists() and pe.exists()):
            print(f"[skip] {lang}: 缺文件"); continue
        wo = openpyxl.load_workbook(po)
        we = openpyxl.load_workbook(pe)
        out = openpyxl.Workbook(); out.remove(out.active)
        print(f"\n[{lang}]")
        for ws_e in we.worksheets:
            title = ws_e.title
            nw = out.create_sheet(title)
            rows_e = list(ws_e.iter_rows(values_only=True))
            for r in rows_e: nw.append(r)
            n_ext = max(len(rows_e) - 1, 0)

            if any(title == t for t in SUMMARY_ZH):
                print(f"  {title:<18} {n_ext:>5}（汇总块，只取 ext 侧，old 侧另计）")
                continue

            ws_o = wo[title] if title in wo.sheetnames else None
            n_add = n_skip = 0
            if ws_o is not None:
                sc = seq_col(ws_o)
                for r in list(ws_o.iter_rows(values_only=True))[1:]:
                    if isinstance(r[sc - 1], (int, float)) and int(r[sc - 1]) in drop:
                        n_skip += 1; continue
                    nw.append(r); n_add += 1
            print(f"  {title:<18} ext {n_ext:>5} + old {n_add:>4}"
                  f"{f'（跳过重复 {n_skip}）' if n_skip else ''} = {n_ext + n_add}")
            # 列宽照抄 ext 侧，别让合并后的表变成一堆挤在一起的窄列
            for i in range(1, ws_e.max_column + 1):
                L = get_column_letter(i)
                if ws_e.column_dimensions[L].width:
                    nw.column_dimensions[L].width = ws_e.column_dimensions[L].width
            nw.freeze_panes = "A2"
        pathlib.Path(f_out).parent.mkdir(parents=True, exist_ok=True)
        out.save(f_out)
        print(f"  -> {f_out}")


if __name__ == "__main__":
    main()
