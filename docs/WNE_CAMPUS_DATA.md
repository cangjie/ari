# 西新英格兰大学校园导览资料（wne_campus）

上线形式：清单模式（`mode=collection`），不带地图、不带 GPS、不带路线，**未公布评级**。页面显示“未评级”，评级与商铺筛选在没有对应条目时自动隐藏。

## 收录范围

- 来源：学校官方页面（校园介绍、校园地图、校史、图书馆、艺术画廊、体育设施），`utils/import_data/wne_list.py` 共 16 条。
- 抓取：`wne_source_capture.py`（复用大波士顿的采集函数），正文留存在 `wne_source_capture.json`。
- 原文审计：`wne_audit_run.py`，模型 claude-haiku-5-5 medium，与大波士顿终审一致。最终结果 16 条全部通过，见 `wne_audit_results.json`。前两次结果保留为 `wne_audit_results_v1_before_address_fix.json` 与 `wne_audit_results_v2_before_text_fix.json`。
- 审计前的修改：地址统一为校区地址，去掉了来源页没有写明的楼号；Sleith 楼与 Wood 礼堂的描述改为与来源原文一致的说法。
- 未收录：MakerSpace（校园内位置未找到官方来源）、住宿楼（不作为景点）。

## 照片

- 3 张，来自 Wikimedia Commons，许可为公有领域（Public domain），记录见 `wne_photo_manifest.json`。
- 足球场看台照片只能确认是校园足球场，无法确认是 1,500 座的 Golden Bear Stadium，说明文字已如实标注。

## 重新生成

```bash
cd utils/import_data
python3 wne_source_capture.py     # 重新抓取（可选）
python3 wne_audit_build.py        # 生成审计输入
python3 wne_build.py --check      # 只检查，不写文件
python3 wne_build.py              # 写 web_api/tour/data/wne_campus.json 并登记 catalog
```

## 待办

1. 校园地图的楼号目前只在校园地图页面有来源，清单里的楼号仅保留在能对上来源的条目中。
2. 需要时可补充校园步行路线（学校官方地图没有给出路线，需要用道路网计算）。
3. 评级：未做。评分与独立审计完成后才能发布有评级的版本。
