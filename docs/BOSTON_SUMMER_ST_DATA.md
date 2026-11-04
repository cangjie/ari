# Boston Summer Street 导览资料

覆盖 Downtown Crossing、South Station、Fort Point 至 Seaport，并衔接自由之路市中心站点。主清单共 53 条，其中 21 条为商铺；自由之路整体与组成站点并非互不重叠的地点。Excel 的“自由之路16站”页另保留北端及查尔斯敦 5 站作范围外对照。

资料按走廊内文化参观优先级进行 V3 评级，S 1、A 12、B 10、C 30；评级不评价餐饮口味、服务或价格。商铺营业、场馆开放、门票、预约及临时封闭均须当日核实。独立审计提示 21 条可结合更多历史或参观资料复核评级，导览与 Excel 均作提示；茶室一项关于独立遗产空间价值的审计意见与评分判断存在分歧，原意见和复核理由均保留。

`boston_summer_st_revision_v3_draft.json` 是评分输入，`boston_summer_st_v3_ratings.json` 保留评分时真实输入哈希；`boston_summer_st_v3_rating_audit_request.json` 和 `_results.json` 保存独立审计输入及结果。正文引文、HTTP 快照、补充来源及每条引用关系分别在 `_verified_evidence_draft.json`、`_v3_source_capture.json` 和 `_v3_site_data.json`；引文必须逐字存在于保存的正文中。V2 评分及审计留存用于追溯，不能冒充 V3。评分和独立审计均按会话授权调用模型；只使用现有模型调用缓存，不向业务数据表登记景区或重灌资料。

不带 `v2`/`v3` 后缀的早期资料包是已作废的历史中间版本：它曾把编辑英文简介误标为来源引文，且部分来源未成功取得正文。其文件内“独立审计完成”等旧状态不能作为发布依据；现行构建只使用 V3，并对引文逐字核验。

导览有两条固定起点路线：纯观光约 5.4 公里、18 站；观光加美食约 4.4 公里、11 站。距离、步行时间及停留为估计，餐饮排队时间另计。路线沿保存的 OSM 公共道路计算，地铁与公交快速交通站点使用 MBTA 官方 GTFS；25 处浏览参考点、24 处独立 GPS 附近提醒点并不代表场馆或商铺入口。夏街阶梯实际在两条线路中；波士顿码头标牌在 Fort Point 路线点中作为相关条目保留。道路通行、临时封闭、定位精度与真实入口以现场为准。

17 张图片已检查主体、文件哈希和 Wikimedia Commons 署名许可元数据，页面展示作者、许可及处理说明。依用户确认，夏街阶梯、Harbor Way 绿地和波士顿码头屋顶标牌暂时无图；缺少可确认授权图片的餐饮节点也可无图。`boston_summer_st_photo_review.json`、`_photo_license_check.json` 与 `_photos.json` 保存核查及身份关系；未选图片不进入发布清单。

`tour_build.py --museum boston_summer_st --check` 核对数据重建，`tour_itinerary_maps.py --museum boston_summer_st --check` 核对路线图与 PNG 哈希。真实手机定位、场馆进入和现场可达性未由自动测试证明；线上状态应以实际部署版本及 HTTPS 访问结果为准。
