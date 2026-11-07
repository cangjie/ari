# Greater Boston 景点导览设计

## 意图

在现有多景区导览站中增加一份波士顿市区与周边地区的双语景点导览，沿用已发布 Boston Summer Street 导览的资料、来源、路线、地图与 GPS 做法。它面向首次及再次到访的游客，既能按地区和类型浏览，也能按主题选择步行游览或周边一日行程。

## 用户已确定的范围

- 覆盖波士顿全市各社区及周边，不局限于自由之路或 Summer Street。
- 明确包括 Cambridge 的 Harvard 与 MIT、波士顿的 Museum of Fine Arts（MFA），以及 Salem 的 Peabody Essex Museum（PEM）。
- 明确纳入 Concord 与 Lexington 的历史小镇与相关景点。
- 资料类别包括：大学、博物馆、名胜古迹、公园、特色建筑、特色街道、著名餐厅。
- 以此前波士顿自由之路／Summer Street 项目的方法为参考：来源可追溯、中文与英文内容、精选地点清单、实地可读的路线地图，以及有可靠公共位置依据的 GPS 附近提醒。

## 范围建议与产品形态

### 地域分层

1. **波士顿市内**：覆盖市政府定义范围内的社区，不只市中心；候选重点包括 Downtown、North End、Charlestown、Beacon Hill、Back Bay、Fenway、Jamaica Plain、Roxbury、Dorchester、South Boston、Seaport 等。
2. **紧邻城市**：Cambridge 为明确重点；Somerville、Brookline、Quincy 等只收录具有可核实游客价值的地点，不为凑齐市镇而扩张。
3. **周边一日行程**：Salem、Concord 与 Lexington 作为独立区域模块。其他更远地点须有同等级的游客锚点和可说明的交通方式，才加入本版。

**范围边界是编辑精选，不是 Greater Boston 全部市镇或所有商业机构的名录。** 不穷举校园内每幢建筑、每家餐厅或所有街道；优先收录具有明确文化、建筑、自然、历史或旅行吸引力，且游客可以实际辨认或进入的对象。最终条数由证据核对和去重决定，不预设凑数指标。

### 新景区与既有内容

- **本设计的实现决定**：新建独立导览 key，暂定 `boston_area`，Web 与现有 Android App 通过服务器 `catalog.json` 共用同一份导览数据。Boston Summer Street 是已发布的窄走廊路线；分开保留它，能避免全域导览改动其路线与游客入口。
- 现有 `boston_summer_st` 保持独立走廊导览，不改名、不删路线、不用新数据覆盖。两份导览可有必要的景点交集，但新资料包内同一实体只保留一个稳定身份，并可注明与另一导览的关联。
- 使用现有 `collection` 内容模式，完整地点清单与可导航点位分开保存；未能核实 GPS 位置的地点仍显示在清单中。
- 主交付为可在现有 Web/App 浏览的双语导览；同时保留便于复核的来源清单/Excel 与本地构建资料。生产上线另行安排，在用户审阅本地成品后再确定时间。

### 地点类别与筛选标准

- **大学**：校园作为可步行浏览的整体对象；另列能独立解释且有可靠位置的建筑、庭院或大学博物馆。说明哪些区域是公共空间、哪些建筑仅限预约或活动入内，不暗示游客能进入教学空间。
- **博物馆与名胜古迹**：优先依据机构官网、城市或州政府、国家公园管理局等一手资料；区分展馆、遗址、纪念物、历史街区与整条步道，避免把整体路线与每个组成站点混作一个互不重叠的列表。
- **公园**：记清公共范围、季节性设施、渡轮或特殊交通依赖；公园范围、景点位置与入口分开记录。
- **特色建筑与街道**：收录有建筑/城市史依据或可辨识公共观赏价值的地点。只有外观可看时明确标记“外观浏览”，不把建筑地址当作可入内证明。
- **著名餐厅**：精选有可说明的历史、地方代表性、权威奖项或官方旅游资料依据的具体分店。餐厅可以成为可选路线停靠点；资料不做口味、服务、性价比或实时营业背书，奖项与营业状态按注明日期核对。
- 同一地点可有多个类别标签，但身份、主要名称与地图位置保持唯一；校园、街道、博物馆群等大范围对象不得拿中心点冒充入口或路线站点。

### 路线与地图

用若干互相独立的街区步行路线和周边一日行程组织内容，不画成一条贯穿全区域的长步道。候选主题包括：

- 自由之路与市中心历史区；
- Beacon Hill 与 Black Heritage Trail；
- Back Bay 建筑、街道与公共图书馆；
- Fenway 博物馆区与 Emerald Necklace；
- Harvard Square／哈佛校园与 Cambridge 博物馆；
- MIT／Kendall Square 建筑与科技；
- North End、海港与 Charlestown；
- Salem 的 PEM、海事史和历史街道；
- Lexington—Concord 的 Minute Man 历史线路及本地文学/自然点。

候选主题需经过路网、现场边界与站点顺序核实后确定，不承诺每个类别都必须独立生成一条路线。餐厅作为可选停留，不要求消费；用餐、排队、购票时间与交通接驳分别说明。

- 继续使用已保存的 OSM 公共步行网络计算街区路线，不用两点直线距离冒充步行距离。
- GPS 只绑定有来源的公共道路参考点或可验证入口；说明提醒点不是门票入口。路线位置未知或可达性存疑时不触发提醒。
- Salem、Concord/Lexington 等跨城模块把公共交通接驳与当地步行路段分开。时刻、票价、季节渡轮与班次只作带日期的规划资料，提醒游客出行当日查官方交通和场馆公告。
- 复用现有 collection 线路图和到站提醒能力，不实现逐路口语音导航、不引入站外地图服务或前端资源。

## 来源、证据与评级

- 每条地点保存稳定身份键、中文/英文名、类别、所在市镇/街区、简介、地址或范围、访问边界、来源 URL、核验日期和适用说明。
- 事实描述优先使用大学/博物馆/餐厅自身官网、Boston/Cambridge/Salem/Concord/Lexington 政府或旅游机构、NPS、MBTA 和其他运营机构的直接资料；保留实际读取的页面正文或明确标记的网页解析快照。搜索摘要不得伪装成原文证据。
- 营业、开放、票价、预约、临时闭馆、渡轮和季节条件均按核对日期保存；页面提示出行当天向运营方复核，不声称持续实时准确。
- 沿用 V3 文化/参观优先级框架和独立内容审计规范，不改算法、不以餐饮质量给餐厅打分。证据不足时降低置信度或留空，记录待复核项，不由类别推断内容。
- 生成来源/资料审计报告和可筛选的双语 Excel 工作簿；图片只在对象身份、来源、作者/许可和文件哈希均可核实时发布。路线关键站优先配图，不为达到比例使用错配或无许可图片。

## 构建边界

- 复用 `tour_collection_build.py`、`tour_collection_media.py`、`tour_collection_experience.py`、`tour_build.py` 与 `tour_itinerary_maps.py`。
- 新增 `utils/import_data/boston_area_*` 源资料与配置，生成 `web_api/tour/data/boston_area.json` 及对应图片/路线图，并在 `web_api/tour/catalog.json` 中登记新 key。
- 不写入业务数据库、不修改其他景区、不重打 Android APK、不改 Nginx/服务器配置；导览页使用现有静态客户端与 collection 模式。
- 该设计要求先形成可审阅的本地版本。是否部署及部署时间，待交付前根据变更内容、停机/影响说明另行决定。

## 非目标与避免的失败

- 不宣称这是整个大波士顿所有景点或所有餐厅的穷尽清单。
- 不把大学教学楼、私有院落、住宅、餐厅内部或活动场地当成始终对游客开放。
- 不把路线接驳、开放季、票价、餐厅奖项或餐饮点评写成无日期的永久事实。
- 不把 V3 Tier 解释为餐厅口味排名、地点质量排名或当天是否营业。
- 不把未核实的中心点/地址当成精确入口、地图轨迹或 GPS 提醒。
- 不改变既有自由之路/Summer Street 内容与其他景区数据。

## 成功判据

- 覆盖所有用户指定地区与七类内容，且每条发布记录有稳定身份、双语文本、直接来源、访问边界和核验日期。
- 同一实体没有重复的主清单身份；整体路线、组成站点、大学校园/建筑群和具体建筑的层级关系清晰。
- 主题路线只沿有来源的公共步道生成；周边交通和当地步行分段表达，未知入口不编造。
- 关键照片具备对象绑定与许可记录；无可靠图的条目可不配图。
- 新景区在 Web/App 从服务器清单加载；既有 Boston Summer Street、宛平城、伪满皇宫及其他清单内容保持原状。
- 本地数据与地图可由仓库现有构建器重建，且复核资料足以让维护者追溯每项来源和处理理由。

## 设计依据与初步来源

- [Meet Boston：社区导览](https://www.meetboston.com/explore/neighborhoods/)用于确认波士顿不能只按市中心组织，社区页面覆盖 Dorchester、Seaport、Beacon Hill、Jamaica Plain、Fenway 等区域。
- [Boston.gov：Things to do around Boston](https://www.boston.gov/departments/tourism-sports-and-entertainment/things-do-around-boston)列出自由之路、Black Heritage Trail、公园、博物馆、图书馆与餐饮/市场等类别。
- [Cambridge Office for Tourism：旅行提示](https://cambridgeusa.org/10-things-you-should-know-for-your-trip-to-cambridge-ma/)将大学、博物馆、公园、遗产路线和餐饮都列为游客活动，并提供 Cambridge 与 Boston 的交通背景。
- [City of Salem：Experience Salem](https://salemma.gov/home/pages/experience-salem)列出 PEM、历史区、博物馆、公园及 Salem Ferry；[PEM 访客信息](https://pem.org/visit)说明通勤铁路步行接驳，以及季节渡轮连接 Boston 与 Salem。
- [Concord 市政府旅游页面](https://www.concordma.gov/3696/Tourism)提供历史、博物馆、景点与游客中心入口。
- [NPS：Minute Man National Historical Park 景点](https://www.nps.gov/mima/planyourvisit/placestogo.htm)说明该园区横跨 Lexington、Lincoln、Concord，Battle Road Trail 约五英里，并区分步道、游客中心、历史建筑开放与季节运营；[NPS 交通与地图](https://home.nps.gov/mima/planyourvisit/directions-transportation.htm)列出 MBTA 和步行/自行车接驳边界。

## 留给实施者决定

- 证据核验后每个区域的最终条目数、精确路线站序、停留估时、路线图范围与版式。
- 额外邻近城镇是否满足“明确游客价值”筛选标准；不得为补数量扩大范围。
- 个别条目是否适合上图或纳入路线；以来源、许可、公共访问和地图身份证据为准。
