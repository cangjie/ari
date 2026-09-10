#!/usr/bin/env python3
"""确认 mfa_boston 的 203 件里，哪些与 mfa_boston_ext 是同一件东西。

**为什么需要这一步（2026-09-10）**

两批 MFA 数据是同一个馆的两次导入，用户要求合并成一个馆、重复以 ext 为准。
难点是**两批的命名方式完全不同**，没有共同标识符可依靠：
    old#1  水月观音木雕
    ext#124 《观音菩萨像》Guanyin, Bodhisattva of Compassion（中国，金代，12 世纪初…）
ext 那 4329 件 Wikidata 来源的大多没有馆藏号，所以对不上编号。

流程是**启发式召回 + 模型确认**，不是让模型两两比对 4464×203：
  1. 名称 token 权重 2.0、简介 token 0.6，过滤掉过于常见的 token，取 top3；
     实测 4 对已知真重复（水月观音/小舞者/捣练图/博伊特的女儿们）全部命中。
  2. 召回必然带误召（「神奈川冲浪里」召回了「赤富士」和「茶室」——
     都是错的），所以**必须逐对确认**，不能直接采信分数。

判定标准写死为「是不是同一件实物」，不是「像不像」「是不是同一位艺术家」——
同一艺术家的不同作品、同一题材的不同版本都必须判 false。
"""
import json, pathlib, sys
import audit_meta as A

SYS = """判断两条博物馆藏品记录是否指向**同一件实物**。

这两条来自同一个博物馆的两批数据，命名方式不同：一批是中文短名，
另一批是「作者《题名》中文（年代，材质）」的长格式。

判 true 的标准：**同一件具体的实物**。作者、题名、年代、材质要能对得上
（允许译名与格式差异，如「爱德华·达利·博伊特的女儿们」=「爱德华·达里·博伊特的女儿」）。

判 false 的情形，**这几类最容易误判，务必分清**：
  · 同一位艺术家的**不同作品**（北斋《神奈川冲浪里》≠ 北斋《凯风快晴（赤富士）》）；
  · 同一题材的**不同件**（两尊不同的观音像、两件不同的青花罐）；
  · 一件是具体展品、另一件是展厅或专辑（「日本茶室复原空间」不等于任何单件）；
  · 同一作品的**不同版本/摹本**若馆方按两件收藏，也判 false。

拿不准就判 false —— 误合并会让两件不同的东西的评分与审计数据张冠李戴，
而漏合并只是留下一条重复记录，后者代价小得多。

reason 用中文，一句话说明依据。"""

SCHEMA = {"type":"object","properties":{"items":{"type":"array","items":{
    "type":"object","properties":{
        "old_seq":{"type":"integer"},
        "same_as_ext_seq":{"type":["integer","null"]},
        "reason":{"type":"string"}},
    "required":["old_seq","same_as_ext_seq","reason"],
    "additionalProperties":False}}},
  "required":["items"],"additionalProperties":False}

def fmt(x):
    p=[f"[old#{x['old_seq']}] {x['old_name']}"]
    if x['old_desc']: p.append(f"  简介: {x['old_desc']}")
    p.append("  候选：")
    for c in x['cands']:
        p.append(f"   - ext#{c['ext_seq']}: {c['ext_name']}")
        if c['ext_desc']: p.append(f"     简介: {c['ext_desc']}")
    return "\n".join(p)

def main():
    model = sys.argv[1] if len(sys.argv)>1 else "gpt-5.6-luna"
    cands = json.loads(pathlib.Path("merge_cands.json").read_text(encoding="utf-8"))
    client = A.LazyClient("~/.openai_key")
    out=[]
    B=10
    for i in range(0,len(cands),B):
        chunk=cands[i:i+B]
        want={x["old_seq"] for x in chunk}
        user=("逐条判断下面每件 old 记录是否与某个候选指向同一件实物。\n"
              "是就填该候选的 ext_seq，都不是就填 null。\n\n"
              + "\n\n".join(fmt(x) for x in chunk))
        d=A.ask(client, model, SYS, user, "merge_confirm", SCHEMA, None,
                museum_key="mfa_boston", scope=f"merge {i+1}-{i+len(chunk)}",
                validate=lambda r,w=want: w <= {y["old_seq"] for y in r["items"]})
        out += d["items"]
        print(f"  {min(i+B,len(cands))}/{len(cands)}")
    pathlib.Path("merge_pairs.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    dup=[x for x in out if x["same_as_ext_seq"]]
    print(f"\n确认重复 {len(dup)} 对，独有 {len(out)-len(dup)} 件")

if __name__ == "__main__":
    main()
