# 西新英格兰大学校园导览资料（wne_campus）

上线形式：清单模式（`mode=collection`），带校园地图与一条**经典校园路线**（步行与 GPS 导览），**未公布评级**。页面显示“未评级”，评级与商铺筛选在没有对应条目时自动隐藏。

## 收录范围

- 来源：学校官方页面（校园介绍、校园地图、校史、图书馆、艺术画廊、体育设施），`utils/import_data/wne_list.py` 共 16 条。
- 抓取：`wne_source_capture.py`（复用大波士顿的采集函数），正文留存在 `wne_source_capture.json`。
- 原文审计：`wne_audit_run.py`，模型 claude-haiku-5-5 medium，与大波士顿终审一致。最终结果 16 条全部通过，见 `wne_audit_results.json`。前两次结果保留为 `wne_audit_results_v1_before_address_fix.json` 与 `wne_audit_results_v2_before_text_fix.json`。
- 审计前的修改：地址统一为校区地址，去掉了来源页没有写明的楼号；Sleith 楼与 Wood 礼堂的描述改为与来源原文一致的说法。
- 未收录：MakerSpace（校园内位置未找到官方来源）、住宿楼（不作为景点）。

## 照片

- 3 张，来自 Wikimedia Commons，许可为公有领域（Public domain），记录见 `wne_photo_manifest.json`。
- 足球场看台照片只能确认是校园足球场，无法确认是 1,500 座的 Golden Bear Stadium，说明文字已如实标注。
- **其余 13 个地点没有可用的授权图片。** Commons 中没有 WNE 各建筑的照片；学校数字档案馆的照片页面没有写明使用许可。需要学校提供授权或由学校自行提供照片。

## 地图与经典路线

- 地图：OpenStreetMap 校园快照（`wne_route_build.py`），建筑、步道、道路、水体、林地。快照文件不入库。
- 路线：访客中心出发，按学校校园地图的编号顺序经过 14 处可定位的地点，沿校园步道回到访客中心，约 4.4 公里。步行时间按 60 米/分估计（约 73 分钟），停留时间为人工估计（170 分钟）。
- 导览：GPS 在靠近建筑中心约 20 米时提示“到附近”，不代表已到门口。模拟游览已验证到访客中心的到站提示。
- 未能在 OSM 中定位的地点：校园整体（无单独建筑）、Lyman and Leslie Wood 礼堂（在 Sleith 楼内，不单独定位）。它们只在清单中出现。

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
2. 13 个地点的照片需要授权或学校提供。
3. 路线的建筑位置是 OSM 建筑中心，不是门口；GPS 到附近提示的半径为 20 米（估计）。
4. 评级：未做。评分与独立审计完成后才能发布有评级的版本。
5. Android 应用会读取含导览的景区数据：本页新增的 GPS 导览使用与南锣鼓巷相同的字段结构，但还未在真机上验证。
