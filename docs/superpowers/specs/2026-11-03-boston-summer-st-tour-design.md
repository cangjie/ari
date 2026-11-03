# Boston Summer Street 导览上线设计

## 意图

把现有的波士顿 Summer Street 双语清单制作成与宛平城、南锣鼓巷及什刹海一致的线上导览内容。游客可在 Web 和现有 Android App 中查看完整清单、真实照片、互动地图和两条步行方案，并在选择路线后使用 GPS 当前位置、地图跟随和到达附近提醒。

## 已批准范围

- 导览 key 使用 `boston_summer_st`。
- 范围为 Downtown Crossing，经 South Station、Fort Point，到 Seaport；自由之路市中心站点作为西端步行衔接内容。
- 线上保留当前双语清单全部 53 条及当前 V3 工作评级：S0 / A12 / B11 / C30。
- 增加两条主题路线：纯观光路线、观光加美食路线。
- 为路线主要站点和路线中出现的餐饮节点配置真实照片。
- Web 与现有 Android App 读取同一线上内容；不修改或重打 APK。
- 不写入生产业务数据库，不改 Nginx，不改其他景区内容。

## 产品形态

### 清单

完整清单显示中英文名称、简介、区域、类型、地址、访问边界、Tier、Core、来源和编者说明。自由之路整体与市中心 11 站分别保留；北端及查尔斯敦 5 站只在资料对照中保留，不作为 Summer Street 线上清单或路线站点。

商铺的 Tier 只衡量文化和游览价值，不表示口味、服务、价格或平台口碑。营业、门票、预约和临时闭馆均明确提示出行当天复核。

### 纯观光路线

路线从自由之路西端进入 Downtown Crossing，再沿 Summer Street 方向前往 Seaport。候选站序为：

1. Boston Common
2. Massachusetts State House
3. Park Street Church / Granary Burying Ground
4. King's Chapel & Burying Ground
5. Boston Latin School Site / Benjamin Franklin Statue
6. Old Corner Bookstore
7. Old South Meeting House
8. Old State House / Boston Massacre Site
9. Faneuil Hall
10. South Station
11. Fort Point Channel Landmark District
12. Boston Wharf Company Office Building & Sign
13. Boston Tea Party Ships & Museum
14. Martin's Park / Fort Point Channel waterfront
15. Summer Street Steps / Harbor Way
16. Institute of Contemporary Art / Seaport Harborwalk

相邻且共享一个公共街道参考点的对象可在界面合并为一个路线停靠说明，但清单身份和评分保持独立。最终道路和距离由 OSM 公共步行网络计算，不手写直线距离。

### 观光加美食路线

路线保留主要历史和滨水节点，把餐饮作为可选择的停靠点，不暗示必须在每家消费。候选站序为：

1. Old South Meeting House / Downtown Crossing
2. Tatte Bakery Summer Street
3. South Station
4. High Street Place
5. Fort Point Channel Landmark District
6. Boston Tea Party Ships & Museum
7. Flour Bakery Fort Point
8. Row 34 或 Trillium Fort Point
9. Summer Street Steps / Harbor Way
10. Coquette 或 M.J. O'Connor's
11. Harpoon Boston Brewery 或 Legal Sea Foods Boston Harborside

页面区分主路线站点和可选商铺。用餐时间不计入路线总时长；具体营业、预订、年龄限制和消费由游客出行当天核实。

实际必经餐饮节点固定为 Tatte、High Street Place、Flour、Row 34、Coquette 和 Harpoon。Trillium、M.J. O'Connor's 与 Legal Sea Foods Boston Harborside 作为附近备选，只在路线说明和地图清单中出现，不参与必经路径、路线总时长或 GPS 到达提醒。

## 导航

导航复用南锣鼓巷现有 collection 导览能力：

- 互动地图显示道路、滨水空间、代表建筑轮廓、路线顺序和两条路线。
- 路线使用 WGS-84 坐标和保存的 OSM 数据，沿允许步行的公共道路求路。
- 每个主路线站点绑定附近公共街道参考点；参考点不是检票入口、商铺入口或允许进入区域。
- 选择主题后启用浏览器 GPS 或 App 原生 GPS，显示当前位置、跟随地图，并在进入估计提醒半径时提示到达附近。
- 精度阈值、重复提醒和离开后重新触发规则沿用南锣鼓巷现有实现。
- 不实现 Google Maps 式逐路口语音转向，不调用站外地图服务，不新增第三方前端资源。
- 两条路线均采用固定起终点，不提供多公共交通起点变体。纯观光路线从 Park Street 站附近开始，在 Courthouse 站附近结束；观光加美食路线从 Downtown Crossing 站附近开始，在 Silver Line Way 站附近结束。起终点具体出口按 MBTA 与 OSM 可核实资料确定，临时关闭以现场为准。

## 照片

- 路线主站和路线中的餐饮节点各用对应对象的独立照片；相邻对象不借用同一张图冒充。
- 优先使用场馆、政府或经营者官网可用于本导览的图片；许可不明确时使用 Wikimedia Commons 的明确开放许可图片。
- 每张照片保存来源 URL、作者、许可、原始文件标识、原图和发布图 SHA-256、图注及绑定 ID。
- 只做 EXIF 方向校正、等比缩小和 JPEG/PNG 编码；不生成、不裁切主体、不去水印。
- 未找到可靠照片的非路线条目保持无图。

## 资料、评级与审计

- 当前 53 条 V3 评级作为评分基线，评分算法、阈值和模型不改。
- 补存实际用于发布的来源文本或明确标记的网页解析快照；搜索摘要不能冒充 HTTP 原文。
- 独立审计读取清单、评分、来源和发布绑定，检查身份、事实、照片错配、路线语义及游客决策风险；审计不自行改 Tier。
- 如果审计发现事实问题，修正文案或绑定并保留处理记录；若证据不足，保留工作评级并在页面中说明其边界。

## 构建与兼容

- 复用 `tour_collection_build.py`、`tour_collection_media.py`、`tour_collection_experience.py` 和 `tour_build.py` 的 collection 数据结构。
- 为 Boston 新增独立的清单、媒体、OSM、体验和展示配置文件，生成 `web_api/tour/data/boston_summer_st.json` 与 `web_api/tour/img/boston_summer_st/` 资源。
- 在 `web_api/tour/catalog.json` 追加目的地，不写死前端景区 key。
- 现有 App 继续打开线上首页并读取服务器清单；本轮不新增 Kotlin 代码，不重打 APK。
- 问答接口若复用现有 collection 支持，仅加载发布数据中已有材料，不发送生产写入测试问题。

## 验证与上线

- 构建器检查 53 条身份、双语覆盖、评级覆盖、来源、照片绑定、OSM 节点、两条路线、步行连通性和 GPS 参考点。
- 浏览器场景覆盖：首页卡片、清单筛选、详情、图片实际解码、两条路线切换、路线绘制、GPS 模拟定位、到达附近提醒、返回行为和旧 App 桥接。
- 回归检查既有景区仍可打开，宛平城和南锣鼓巷路线及导航不受影响。
- 内容提交并推送 `master` 后，服务器执行 `git pull --ff-only`；静态内容无需重启服务。若后端问答代码没有变化，则不重启 `ari-web-api`。
- 在 `tour.snowmeet.top` 和 `tour.arimuseum.org` 验证 catalog、JSON、照片、路线资源、浏览器交互和只读问答入口。公网检查不替代波士顿现场步行、实际 GPS、门店营业或 Android 真机验收。

## 实现者可自行决定

- 共享公共街道参考点的相邻站点在路线卡片中的合并方式。
- 每条路线的精确停留分钟数，但必须在来源和常识边界内标成估计。
- 照片最终数量，只要每个路线主要站点和路线餐饮节点均有自身匹配照片，且许可记录完整。
- OSM 地图范围、投影和画布尺寸，只要完整覆盖两条路线并保持手机端可读。

## 非目标

- 不提供逐路口语音导航。
- 不承诺实时营业、实时门票、无障碍状态或现场排队时长。
- 不把全部自由之路北端和查尔斯敦站点纳入本次路线。
- 不重做当前 V3 算法，不把消费评价混入文化参观 Tier。
- 不修改 Android 原生定位算法、APK、Nginx 或生产业务库。
