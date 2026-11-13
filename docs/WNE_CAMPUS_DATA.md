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
- 用户于 2026-11-13 在会话中确认已取得学校授权，未提供书面授权文件及条件。以此为依据补入 WNE 官网十张照片：九个楼宇或设施条目各一张，以及 Sleith 生物医学工程实验室补图；图注限定到来源可确认的主体，未将照片冒充具体房号。仍有地点或房间未找到可对应的照片，保持无图。
- 学校官网图片的页面及原图链接、原件和发布版哈希见 `utils/import_data/wne_official_photo_manifest.json`。原件保存在忽略目录 `utils/import_data/exports/wne_official_originals/`；`wne_official_photos.py` 使用 Pillow 将其缩放并转为本地 JPEG，`wne_visitor_details.py` 在生成时校验哈希并绑定条目。具体授权范围与条件以学校授权原文为准。
- `wne_official_photo_refs.py` 收录学校官网上的建筑或设施图片页面链接，供访客跳转浏览，未复制图片，也不将建筑图冒充具体房间的照片。图片页面本身并不证明第三方有转载权限。

## 地图与经典路线

- 地图：OpenStreetMap 校园快照（`wne_route_build.py`），建筑、步道、道路、水体、林地。快照文件不入库。
- 路线：访客中心出发，经过 14 处可定位的地点，沿校园步道回到访客中心，约 4.4 公里。步行时间按 60 米/分估计（约 73 分钟），停留时间为人工估计（170 分钟）。游览顺序以路线数据为准，不是学校地图编号顺序。
- 导览：GPS 在靠近建筑中心约 20 米时提示“到附近”，不代表已到门口。模拟游览已验证到访客中心的到站提示。
- 访客停车与室内资料：路线说明以学校驾车指引的 Welcome Center 停车场为出发建议，地图起点仍是访客中心建筑中心，停车场位置和停车场至建筑的路程未实测、未计入。各站补充学校公开的用途、部分房号及性别包容卫生间；实验室、卫生间和办公室开放情况需现场确认，公开无依据的房号不猜测。路线站点 `seq` 指向清单中对应的实际条目，地图上的数字仍是游览顺序。
- 楼内房间补充见 `wne_rooms.py`：学校的表格、手册及活动记录逐项附来源；旧手册与活动用途注明年份或待核状态，不把临时会议推断为专属教室或办公室。2021年手册的数学中心303室现作为历史资料列出，明确提示位置待确认。房间只挂在对应楼宇介绍中，不作为GPS点，开放权限需向学校确认。
- 未能在 OSM 中定位的地点：校园整体（无单独建筑）、Lyman and Leslie Wood 礼堂（在 Sleith 楼内，不单独定位）。它们只在清单中出现。

## 重新生成

```bash
cd utils/import_data
python3 wne_source_capture.py     # 重新抓取（可选）
python3 wne_audit_build.py        # 生成审计输入
python3 wne_build.py --check      # 只检查，不写文件
python3 wne_build.py              # 生成清单，会覆盖现有地图与路线；必须接着执行下一步
python3 wne_route_build.py --raw /路径/wne_osm_raw.json  # 重建地图路线并补充访客资料；需原 OSM 快照
python3 wne_visitor_details.py    # 仅更新已有路线的访客资料，无需原始快照
```

## 待办

1. 校园地图的楼号目前只在校园地图页面有来源，清单里的楼号仅保留在能对上来源的条目中。
2. 16 条中有 12 条地点有图；Emerson Hall、Churchill Hall、Wood 礼堂及 Rivers Memorial Hall 尚无可准确对应的照片。房间级图片仍需核对具体主体。
3. 路线的建筑位置是 OSM 建筑中心，不是门口；GPS 到附近提示的半径为 20 米（估计）。
4. 评级：未做。评分与独立审计完成后才能发布有评级的版本。
5. Android 应用会读取含导览的景区数据：本页新增的 GPS 导览使用与南锣鼓巷相同的字段结构，但还未在真机上验证。
