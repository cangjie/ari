# 大波士顿导览资料（boston_area）

上线形式：清单模式（`mode=collection`），不带地图、不带 GPS，**未公布评级**。页面显示“未评级”，评级筛选与商铺筛选在没有对应条目时自动隐藏。

## 收录范围

- 来源：`utils/import_data/boston_area_list.py` 的 73 条候选，其中 44 条抓到官方页面正文并通过原文审计（`boston_area_v3_audit_results_haiku55.json`，支持与地址支持均为真）。
- 未抓到正文或地址未通过审计的条目不上线，见 `boston_area_v3_audit_disposition.json`。
- 三条参考路线（`boston_area_routes.py`）：四日主路线（含餐厅）、两日备选一（含餐厅）、两日备选二（不含餐厅）。路线只以文字形式出现在清单说明中，不是路线页。

## 步行与停留

- 步行距离：OpenStreetMap 行人路网上的最短路径（`boston_area_walk.py`，原始 Overpass 数据不入库，见 `boston_area_osm_fetch.py`）。按 60 米/分估计。
- 无法在路网上连通的段按直线估算并标注“现场确认”；超过 1.5 公里的未连通段标为公共交通，不给步行时间。
- 停留时间全部为人工估计。

## 照片

- 29 张，来自 Wikimedia Commons，许可为 CC0、公有领域、CC BY 或 CC BY-SA，逐张目视核对主体。
- 署名、许可与原图页面见 `boston_area_photo_manifest.json`，页面上以“图片出处 / 作者 / 许可”形式展示。

## 重新生成

```bash
cd utils/import_data
python3 boston_area_build.py --check      # 只检查，不写文件
python3 boston_area_build.py              # 写 web_api/tour/data/boston_area.json 并登记 catalog
python3 boston_area_routes.py --check
```

## 待办（上线后）

1. **V3 评分**：`boston_area_rate.py` 已写好，阶段一因 Codex 额度用尽未完成。需要定打分方式（额度恢复后用 gpt-5.6-luna，或改 API）。
2. **独立审计**：评分完成后，用与打分不同厂商的模型做一次审计，发布有评级的版本前必须完成。
3. **路线页**：目前路线只是说明文字，没有逐站路线视图。
4. **四个未过审站**：Harvard Square、State House、Harvard University、Rose Kennedy Greenway 已从路线移除，来源补齐后可再加入。
5. **英文**：部分“访问”说明只有中文。
