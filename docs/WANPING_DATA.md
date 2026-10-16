# 宛平城主要参观点资料整理

本轮为 2026-10-15 的资料整理：来源、V3 评分、独立审计与中英清单已生成，同类组按用户确认口径归并。
用户随后要求接入App和Web并策划免费线、全面线；本页末尾记录该阶段，生产业务表仍未导入。

## 范围与方法

用户确认：**宛平城为主，连同卢沟桥、抗战馆和雕塑园的主要参观点**。
不深入扩抓抗战馆全部藏品。现有 39 条：人工类型提示为 site 3、node 28、object 8；最终类型以 V3 模型结果为准。
整体、建筑、展陈、展区、组合雕塑分层记录，父子关系明确；这不是 39 个互不重叠的路线站点。

原始资料来自丰台区政府、丰台时报、北京旅游网与中国人民抗日战争纪念馆网站。
官网原文逐字摘录，与编者说明分列，不用模型记忆补齐现场信息。
信息提取与评分沿用 `gpt-5.6-luna`（Codex 订阅）；V3 三阶段 high / medium / xhigh。
审计沿用 `claude-sonnet-5`（Claude 订阅）、medium、slim；审计不改评级。
模型调用经过 `llm_call` 缓存，失败即停；评分与审计任务套现有 `llm_guard.py`。

## 文件

- `utils/import_data/wanping_source_capture.json`：网页工具提取文本及失败记录。**不是原始 HTTP 响应**；本机直连部分官网超时。
- `utils/import_data/wanping_bridge_museum_index.json`：卢沟桥历史博物馆官方搜索索引摘录；详情正文未取得。
- `utils/import_data/wanping_build.py`：按已保存的来源行号取原文、维护稳定身份键与 source_seq、生成 JSON / Excel；零网络。
- `utils/import_data/wanping_seq_map.csv`：身份键到稳定序号的映射，新增只追加，不重新编号。
- `utils/import_data/wanping_site_data.json`：39 条来源清单、逐条证据、父节点与未决项。
- `utils/import_data/artworks/宛平城_参观点清单.xlsx`：来源清单、逐条出处、说明与待补。
- `utils/import_data/wanping_pipeline.py`：复用现有 `tier_v3` 与 `audit_meta` 函数的本地适配器，不另写评级算法与审计提示词。
- `utils/import_data/wanping_export.py`：核对来源版本、评分与审计覆盖后导出本地审计版，零数据库写入。
- `utils/import_data/exports/展品_宛平城及周边_本地审计版.xlsx`：中英参观点、逐条来源证据、同类组、说明。导出目录沿用仓库的 gitignore。
- `utils/import_data/wanping_final.json`：本地资料、评分与审计合并结果，可复核、可再导出。
- `utils/import_data/wanping_translations.json` / `wanping_translations.csv`：106 段本地译文，明确标 AI翻译，不伪装成馆方英文或人工校对；尚未合并进通用译名表。
- `utils/import_data/wanping_images.json`：四个整体的官方图片链接，其中三张读取成功、一张超时；不挪用整体图片给子节点。
- `wanping_smoke_*`、`wanping_stage*`、`wanping_ratings.json`、`wanping_audit*`：均在 `utils/import_data/` 内，已成功调用的输出应保留。
- `wanping_peer_groups.json`：用户确认的归并口径；`wanping_peer_groups_proposal.json` 保留此前提案。
- `wanping_grouped_stage*`、`wanping_grouped_ratings.json`、`wanping_grouped_review.csv`：归并后的当前评分；原始 `wanping_ratings.json` 不覆盖。
- `wanping_group_change_report.json`：归并前后逐字段差异。`wanping_grouped_audit_patch.jsonl` 为受影响十条的独立复审原始输出；审计原版另存 `.original_groups`。
- `wanping_verification_report.json`：来源哈希、评分保留范围、审计覆盖、工作簿行数、英文残留扫描与成品哈希的验收记录。
- `wanping_final_归并前.json`、`wanping_export_report_归并前.json` 与导出目录中 `…_归并前.xlsx`：归并前版本。

## 当前发现与资料边界

1. 丰台区历史文化页同时写“明崇祯十三年（1638年）”，与其他官方页面的 1638–1640 建城表述存在纪年口径问题。独立审计已标记该矛盾，原文照录。
2. 县衙、卢沟驿、兴隆寺、拱极营被官方明确记为复建，不能描述为完整保存的明代原构。
3. 2025 年抗战馆改扩建后，基本陈列为《为了民族解放与世界和平》，馆方列出八部分及英烈专区；不沿用旧基本陈列目录。
4. 卢沟桥石狮的 501、502、492 等数字在不同官方材料中并存，暂不自行选择一个覆盖其余来源。
5. 雕塑园收录官方明确点名的四大主题分区、纪念碑、两件具名雕塑；尚未取得全部 38 尊的逐件资料，不编造缺失题名。
6. 卢沟桥历史博物馆仅按官方索引摘录列为一个节点；武俊碑、腰牌、铁犀牛等的当前展位与原件/复制品尚未核实，不作为可参观单件入表。
7. 历史报道、“长期基本陈列”与今天实时开放是不同信息；当前状态先保留未知，不据此承诺门票、开放时间或具体展厅。
8. 资料整理首版未取得地图、热区坐标、完整图片与停留时间；后续导览接入另行补充OSM几何和策划时间，不回填为官网原文。

## 执行与验收

环境：使用 `utils/import_data/.venv/bin/python`，已有 PyMySQL / openpyxl；`python3` 可生成来源 Excel。
开工时只读核对生产库 10 个 museum key，未存在 `wanping`；存量合计 31426 条。

```sh
python3 utils/import_data/wanping_build.py --check
python3 utils/import_data/wanping_build.py
utils/import_data/.venv/bin/python -u utils/import_data/llm_guard.py --provider openai_codex --stage 'tier_stage%' --museum wanping --every 5 -- utils/import_data/.venv/bin/python -u utils/import_data/wanping_pipeline.py tier-grouped
utils/import_data/.venv/bin/python -u utils/import_data/llm_guard.py --provider anthropic_cli --stage 'audit_%' --museum wanping --every 5 -- utils/import_data/.venv/bin/python -u utils/import_data/wanping_pipeline.py audit
utils/import_data/.venv/bin/python -u utils/import_data/llm_guard.py --provider openai_codex --stage 'trans_wanping%' --museum wanping --every 5 -- utils/import_data/.venv/bin/python -u utils/import_data/wanping_pipeline.py translate
utils/import_data/.venv/bin/python -u utils/import_data/llm_guard.py --provider openai_codex --stage audit_trans --museum wanping --every 5 -- utils/import_data/.venv/bin/python -u utils/import_data/wanping_pipeline.py audit-translate
python3 utils/import_data/wanping_export.py
```

以上为现有产物的续跑指令；原分组的首次评分使用 `tier`，已完成，不需重跑。
`tier-grouped` 复用原阶段一及未受影响组，仅重算用户确认归并的两组 CR，并复测适用的 S 候选。
`audit` 在归并评分存在时仅复审 seq 20–29，再与保留的其他 29 条审计合成完整 39 条。

来源检查已通过：39 个身份键和序号无重复，父节点均可解析；初始 Excel 39 行、49 条出处。
冒烟 3 件：宛平城 site / ER 9 / Core 9.2345 / S；顺治门 node / ER 7.5 / Core 7.255 / A；卢沟晓月碑 object / ER 0 / Core 6.525 / B。
冒烟模型输出已保存。汇总适配器曾因重复传入 seq 失败，定位后只重建汇总，未重调模型。

全量结果：39 条，site 3 / node 28 / object 8，V3 为 **S5 / A16 / B16 / C2**。
S 级为宛平城、城墙弹痕、卢沟桥、中国人民抗日战争纪念馆、《为了民族解放与世界和平》基本陈列。
冒烟与全量的批次上下文不同，具体分值与评级可能不同，冒烟只验证链路，不作为全量的一部分合并。

Claude sonnet-5 / medium / slim 已审 39 条，归并后复审 seq 20–29，其他 29 条原审计逐字段保留。
当前需复核 1 条（seq 1，纪年换算矛盾）；15 条共 15 项缺口，均为 tier_sensitive=false。
原审计为 7 项，归并后的十条复审另提出 8 项展览现状确认缺口；这不代表来源内容发生改变。
其他缺口涉及城墙原构/修缮边界、专题展当前展期、雕塑分区逐件清单。审计发现的问题没有覆盖原文或修改评级。
本批没有生成 sig_* 推断型 metadata，故没有可送阶段三的 Evidence Packet claims；这里的完成范围是本地逐件 slim 审计及 B/C 兜底、补译。
英文名称、简介、编者说明与审计自由文本已成对；导出英文主表的文本列 CJK 扫描为 0 处。

**同类组已按用户确认修正：** 原模型将基本陈列整体及前四部分放在一组、后四部分及英烈专区放在另一组。
用户 2026-10-15 选择“展览整体单列；八部分及英烈专区合为一组”。现为 seq 20 单列“抗战馆基本陈列整体”，seq 21–29 归入“抗战馆基本陈列分区”，总组数仍为 20。
受影响十条已重算 CR、Core，seq 20 已重测 S-ness；39 条原阶段一维度分均保留，其他 29 条评分逐字段不变（仅附加原组名溯源字段）。
十条评级均未跨档，全量分布仍为 S5 / A16 / B16 / C2。原评分、原审计及归并前导出均保留，不能用新组名解释旧评分。

存量 10 馆开工与结束的逐馆行数已只读复核，合计均为 31426；本轮仅写模型缓存，不写生产业务资料。
生产登记、metadata 入库、通用译名表同步与标准数据库中英导出尚未执行。导览接入直接使用已审计本地包，见后文。
阶段计量在 `wanping_usage_report.json`；Claude 输入 token 有仓库已知缺口，不把它当完整账单。
资料整理与分组归并阶段记录41次成功调用、0次失败；含后续导览发布，当前共45次成功、1次额度耗尽失败。各阶段型号与档位均保留在计量报告中。
归并版验收已通过：中英各 39 条、来源证据 49 条、同类组 20 组；英文主文本列无中文残留，原版备份保留。

## App / Web与两条路线（2026-10-15）

用户要求把宛平城与伪满皇宫一样放到App、Web，并策划免费及全面游览路线。
沿用两端共用的服务器 `web_api/tour/data/*.json`。用户随后纠正：App应引用Web或API，景区变化不能每次改App。
最终采用App直接打开线上Web首页，服务器 `catalog.json` 控制上架、下架与排序；同一份资料同步给原生定位缓存。
新增 `tour_package_build.py` 支持已审计本地资料包，避免为发布一个景区而重灌存量展品库。
原数据库读取方式和伪满皇宫生成方式保留；游客互动仍读同一份导览JSON，不另建资料副本。

### 来源与定位

- `wanping_access.json` 保存费用/开放依据与检索日期；卢沟桥20元、登城30元是官方旧文参考价，不能当作实时售票承诺。
- 抗战馆常规时间取2026-02-03的文旅丰台发布，基本参观免费免预约；半景画独立预约。官网首页另列2026-05-09须知，但未取得该篇正文，不冒充已核验。
- 2026-08-15的单日免票活动仅作反例留存，不用于推导日常免票。雕塑园较早名录只支持免费、非全天开放，不推断今天几点开门。
- OSM原始HTTP XML为 `wanping_osm_response.xml`；导览范围的道路、节点为 `wanping_osm_data.json`。Overpass查询失败后改用OSM官方map API。
- 7个到达点承接全部39条资料：东门、抗战馆、宛平广场、宛平大街、西门、卢沟桥、雕塑园西侧到达点。分展区、雕塑与碑刻没有单独位置依据，按所属整体阅读，不伪造独立热区。
- OSM西门节点误标“顺治门”；按官方原文的东门顺治、西门永昌命名，坐标仍保留OSM要素编号。导览定位包围框不是法定景区边界。
- 2026-10-15首次下载官网图片均超时，失败历史保留在 `wanping_photo_report.json`。2026-10-16经用户指定的2222映射通道补图，当前成果见下方“图片收录”记录。

### 策划路线

两条路线均从**顺治门（东门）**出发并返回，建议9:00开始，先看有闭馆时间的抗战馆。
步行按已记录的OSM道路连接，排除城墙顶道路和私人/禁止步行道路；免费线另排除卢沟桥桥面。
图上路线仅作步行顺序参考，不是实时导航；实际出入口、交通管制和临时关闭按现场指引。

| 路线 | 顺序 | 估计用时 | 门票 |
|---|---|---|---|
| 免费线 | 东门及弹痕 → 抗战馆基本陈列 → 宛平广场 → 宛平大街 → 西门外观及地面环城步道 → 雕塑园 → 返回东门 | 222.4分钟，约3小时45分钟（停留180、步行42.4） | 0元；不登城、不进入卢沟桥收费区 |
| 全面线 | 免费线基础上，西门后加入西城墙登城往返、卢沟桥桥面及石狮碑刻，再到雕塑园返回 | 306分钟，约5小时10分钟（停留255、步行51） | 成人参考约50元（登城30+桥20），优惠和当日报价另核 |

时间为本导览估计，未实走；不含交通、安检、排队、午餐和半景画候场。
整馆与基本陈列不重复计时；八部分及英烈专区合计占基本陈列90分钟，精读可另加30–60分钟。
普通周一或临时闭馆时跳过馆内，参考用时减少90分钟；这不保证其余场所当天一定开放。
县衙等沿街建筑只看外观；2025年临展与卢沟桥历史博物馆没有核实当前开放，不作为必访项目或必需门票。
“全面”指四大板块的主要内容，不代表所有39条是互不重叠的独立站点，也不保证不明开放项目可进。

配置在 `wanping_route_data.py` / `wanping_tour_data.py`。重生成与比对：

```sh
utils/import_data/.venv/bin/python utils/import_data/tour_build.py --museum wanping
utils/import_data/.venv/bin/python utils/import_data/tour_build.py --museum wanping --check
```

Web展示路线费用、逐站顺序、开放与预约提示，以及可打开的官方来源；问答材料读同样的约束。
App使用线上同一套页面与JSON，不再打包景区资料。旧包要安装新版一次，之后景区和顺序变化只更新服务器。
返回前台及回首页刷新清单；同步删除的景区也从原生定位引擎移除，缓存损坏或资料错误不覆盖最后有效快照。
服务器编辑 `web_api/tour/catalog.json` 的 `museums` 数组即可调整顺序及上/下架，移除数组项不会删除原始资料。
生成新景区时首次自动追加，后续重生成会保留现有排序和下架选择。
独立发布复核继续使用 `claude-sonnet-5` / medium，脚本为 `wanping_tour_audit.py`，结果及处理记录随仓库保留。

### 自动检查与边界

Web的pytest目前74项通过、3项真实数据库检查未启用；浏览器检查包含动态增删、反转排序、空清单、原生同步与两处景区回归。
Android标准构建、12项单测、lint通过；lint保留13项既有警告。原API26导航栏样式兼容错误已修正，没有提高最低系统版本。
发布前已核对新旧包的签名证书相同；未做安装和现场GPS验收。
路线/发布代码初审的两项important及两项minor已修正并经同模型复审确认；复审关于清单来源的提示已由服务器清单与浏览器测试覆盖。
补译35段时曾遇Codex额度耗尽，未自动重试或换模型；额度恢复核对后完成。错误调用留在计量中，不伪报全程零失败。

动态同步审查的实际问题已处理：文字更新保留到站状态；移除当前景区或清空清单会停止对应原生服务；逐景区JSON显式重新校验缓存；页面切换重置桥接就绪状态。模型误将“回归测试”理解为下架伪满皇宫的建议未采纳，理由保存在 `wanping_review_disposition.json`。

### 发布验收

内容版本 `bf6d358` 已推送并部署；`ari-web-api` 已重启且active。公网首页、脚本、景区清单、宛平城与伪满皇宫资料均为HTTP200，正文与本地文件逐字节一致；两处景区问答列表GET正常，未发送线上测试问题。线上浏览器的宛平城、列表与只读问答场景全部通过。

新版App已替换 `/android/app`，旧包保留在服务器仓库外。新包与旧包签名证书相同；通过服务器对公开HTTPS下载地址完整读取8312316字节并核对SHA-256一致。本机外网请求也核对了HTTP200、文件类型和长度，完整下载因链路慢未作为完成依据。产物、方法与边界见 `wanping_release_report.json`；真机安装、现场定位、后台和悬浮窗仍待用户实机验收。

## 图片收录（2026-10-16）

收录12张照片：宛平城、顺治门、城墙、弹痕、宛平县衙外观、卢沟桥、桥栏石狮、卢沟晓月碑、抗战馆外观、雕塑园、抗战纪念碑、卢沟桥历史博物馆外观。来源为丰台区政府、丰台时报与北京旅游网图文页面，逐张核对图片、图注和可辨识的牌匾。没有对应照片的条目仍留空；馆外观不借给2025年基本陈列及各室内展区。

用户授权通过美国服务器2222端口映射的服务器下载；实际使用 `ubuntu@44.207.251.65:2222`，远端curl只输出到内存和SSH管道，未在中转机创建图片、脚本或临时文件。完整原件及来源HTML保存在本机忽略目录 `utils/import_data/exports/wanping_photo_originals/`。原件合计21325461字节；发布版合计1457885字节，单张最多175466字节。发布只做等比尺寸限制及JPEG编码，不裁切、生成、去水印或修饰内容；拍摄日期未注明，不当作实时现场照片。

- `wanping_tour_photos.json`：12张图的稳定条目、原图URL、来源页面、对应依据、原件及发布版SHA-256。
- `wanping_photo_sources.json`：官方原始HTML中的图片标签及邻近文字摘录；原始HTML哈希可回查。
- `web_api/tour/img/wanping/`：页面本地图片，不依赖游客访问官网图床。
- `tour_photo_build.py --manifest wanping_tour_photos.json`：用Pillow读取本机留存原件，重做编码并核对发布图片；加 `--write` 可恢复发布文件，原件不覆盖。应使用提供Pillow的工作区Python。
- `wanping_photo_audit.py`：沿用sonnet-5 medium，复核来源绑定和页面接入源码；模型仅收到文本与代码，不把该报告冒充直接看图的视觉审计。

生成器统一使用 `img/<景区>/<序号>.jpg`，校验条目身份与文件哈希。地点封面及每条记录各自的照片均可显示，同一照片不重复；照片旁列出对应图片出处，保留比例。App继续直接读取共用Web，无需重打包或替换APK。原有39条历史介绍、V3评分、业务数据库与两条路线不因补图而重跑或改写。

图片接入复核提出的四项意见已处理：地点封面改为显式配置、馆外观图注明确标示、县衙牌匾异名可见、非HTTPS来源仍保留纯文字出处。不会把所有父键非空的条目都排除做封面，因为地图城门本就属于古城整体。修正后由确定性测试和浏览器核对，未声称模型看过原图或二次复核最终代码。

本轮内容版本 `81f8653` 已推送并部署。公网JS、CSS、导览JSON与12张JPEG均返回HTTP200，完整正文或文件SHA-256与本地一致；线上浏览器逐张解码12张图片，并通过宛平城、伪满皇宫列表和只读问答回归。Web测试76项通过、3项真实数据库检查未启用。此次仅静态发布，无服务重启或APK替换。完整逐文件证据保存在 `wanping_photo_publish_report.json`。
