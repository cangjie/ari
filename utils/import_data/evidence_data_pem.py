# -*- coding: utf-8 -*-
"""PEM 展品的 Evidence Packet 数据。由 evidence_fill.py 读取。

**source_tier 如实标注**（提案第 4 节）：
  1 官方藏品库/UNESCO/国家文物机构   2 展览图录/学术论文/权威考古报告
  3 拍卖行/专业艺术数据库             4 Wikipedia 及一般网络资料，或未经核实的汇编

本批绝大多数只能标 4：PEM 官方藏品门户 explore-art.pem.org 已停止服务，
库里 official_url 为 0/196，外部可核实的只有 3 件（seq 5/15/16）。
证据主要来自源 Excel 的简介（来源不明的汇编）加领域知识。
**按提案规定，Tier 4 不足以单独支撑 S** —— 这正是本次实验要检验的东西之一，
不要为了让结论好看而把它填高。
"""

PACKETS = {

1: {  # 荫余堂
 "sig": {
  "sig_historical": ("清代徽州商人黄氏家族宅第，反映 18–19 世纪徽商的家族结构与聚居形态；"
                     "2003 年整体迁建入 PEM，是中美文化遗产合作的标志性案例。",
                     "Residence of the Huang merchant family of Huizhou, Qing dynasty; reflects "
                     "the household structure and settlement pattern of 18th–19th-century Huizhou "
                     "merchants. Relocated to PEM in 2003, a landmark case of US–China heritage cooperation."),
  "sig_art_historical": ("徽派民居的典型形制：马头墙、天井、木雕门罩与厅堂梁架，"
                         "是研究中国南方民居营造技艺的完整实例。",
                         "A complete example of Huizhou vernacular architecture — horse-head gables, "
                         "sky-well courtyard, carved timber door hoods and hall framing — for the study "
                         "of southern Chinese domestic building craft."),
  "sig_rarity": ("海外唯一一座整体拆迁复原的清代中国民居。同类整体迁建的中国建筑在西方博物馆中无第二例。",
                 "The only complete Qing-dynasty Chinese house dismantled and reassembled outside China. "
                 "No comparable whole-building relocation exists in another Western museum."),
  "sig_institutional": ("PEM 对外宣传与游客动线的第一目的地，需分时预约单独入场；"
                        "失去它，本馆最具辨识度的单一资产随之消失。",
                        "PEM's flagship attraction and the first stop on visitor routes, requiring a timed "
                        "ticket of its own. Losing it would remove the museum's single most recognizable asset."),
  "sig_category": ("本馆唯一的整体建筑类藏品，与其余 195 件可移动文物不构成同类竞争，"
                   "在「迁建历史建筑」这一类别中独占。",
                   "The museum's only whole-building holding; it competes with none of the other 195 movable "
                   "objects and stands alone in the category of relocated historic architecture."),
  "sig_cultural": ("可穿行体验，能同时解释徽商经济、宗族制度、风水观念与中国传统家庭起居，"
                   "叙事承载力远超单件器物。",
                   "Walk-through experience that simultaneously explains the Huizhou merchant economy, "
                   "lineage institutions, fengshui concepts and traditional Chinese domestic life — a narrative "
                   "capacity far beyond any single object."),
  "sig_provenance": ("由黄氏后人出让，经中美两国文物部门批准，拆解编号后运抵塞勒姆复原，"
                     "迁建过程本身有完整记录，构成独立的当代文献价值。",
                     "Transferred by descendants of the Huang family with approval from heritage authorities in "
                     "both countries; dismantled, numbered, shipped to Salem and rebuilt. The relocation itself is "
                     "fully documented and carries independent contemporary documentary value."),
  "sig_visual": ("16 间木构两层宅院，含天井与庭院，游客可入内行走；"
                 "空间尺度与材质观感是全馆最强的现场体验。",
                 "A 16-room, two-storey timber house with sky-well and courtyard that visitors walk through; "
                 "its spatial scale and material presence make it the museum's strongest on-site experience."),
  "sig_relations": ("庭院、天井、厅堂、厢房构成完整的空间序列与轴线关系；"
                    "现存于 Yin Yu Tang Courtyard 独立院落，与馆内其他展厅在空间上分离。",
                    "Courtyard, sky-well, main hall and wing rooms form a complete spatial sequence and axial "
                    "relationship; it stands in its own Yin Yu Tang Courtyard, spatially separate from the galleries."),
 },
 "conf": {"hs": "high", "iu": "high", "vi": "high", "va": "high",
          "ce": "high", "cr": "high", "er": "high"},
 "missing": ["缺具体建造年代（现仅知清代中晚期），需查 PEM 迁建工程报告",
             "缺原址地点的确切村名与现状",
             "缺 PEM 官方藏品编号"],
 "source_tier": 4,
},

2: {  # 南蛮屏风
 "sig": {
  "sig_historical": ("记录 16 世纪末至 17 世纪初葡萄牙商船抵达日本的场景，"
                     "是南蛮贸易与欧日首次持续接触的图像史料。",
                     "Depicts Portuguese trading ships arriving in Japan in the late 16th–early 17th century; "
                     "pictorial evidence of Nanban trade and the first sustained Europe–Japan contact."),
  "sig_art_historical": ("南蛮屏风是桃山至江户初期的特殊画科，以金地浓彩描绘异国人物与船舶；"
                         "本件为该画科的高水平例证。",
                         "Nanban screens are a distinct genre of the Momoyama to early Edo period, rendering "
                         "foreign figures and ships in heavy colour on gold ground; this is a high-quality example."),
  "sig_rarity": ("传世南蛮屏风数量有限且多藏于日本；"
                 "美国收藏中达到此规格与保存状况者少见。",
                 "Surviving Nanban screens are limited in number and mostly held in Japan; few in American "
                 "collections match this scale and state of preservation."),
  "sig_institutional": ("日本艺术板块的核心展件，同时支撑 PEM「跨洋接触与贸易」的主叙事，"
                        "与本馆的塞勒姆远洋贸易身份直接呼应。",
                        "Centrepiece of the Japanese art holdings and a pillar of PEM's core narrative of "
                        "transoceanic contact and trade, resonating directly with the museum's Salem maritime identity."),
  "sig_category": ("本馆唯一的日本屏风绘画，在该类别中无竞争者。",
                   "The museum's only Japanese folding screen; no competitor within the category."),
  "sig_cultural": ("能解释一整段历史进程：欧洲人东来、南蛮文化流行、以及随后的锁国政策，"
                   "教育承载力强。",
                   "Explains an entire historical arc — the arrival of Europeans, the vogue for Nanban culture, "
                   "and the subsequent seclusion policy — giving it strong educational capacity."),
  "sig_provenance": ("入藏途径与递藏链未见于现有资料，需查证。",
                     "Acquisition route and chain of ownership are not documented in available sources; "
                     "verification required."),
  "sig_visual": ("六曲金地大屏风，尺幅可观、色彩浓丽，现场辨识度与冲击力在日本馆居首。",
                 "A large six-panel screen on gold ground, substantial in scale and richly coloured; the most "
                 "visually commanding object in the Japanese gallery."),
  "sig_relations": ("屏风为独立可移动器物，与展厅空间无固定关系。",
                    "A free-standing movable object with no fixed relationship to the gallery architecture."),
 },
 "conf": {"hs": "high", "iu": "high", "vi": "high", "va": "medium",
          "ce": "high", "cr": "medium", "er": None},
 "missing": ["缺确切年代与画派归属（狩野派？土佐派？）",
             "缺递藏与入藏记录",
             "缺尺寸与材质技法（金笺设色？）",
             "未见学术出版物讨论本件的记录"],
 "source_tier": 4,
},

3: {  # 夏威夷库战神像
 "sig": {
  "sig_historical": ("库（Kū）是夏威夷四大主神之一，掌战争；此类神像用于战前仪式与祭祀，"
                     "是夏威夷宗教与王权制度的物证。**断代已更正**：源数据称「前接触期」，"
                     "但 PEM 官方记录为 19 世纪早期、1846 年 John T. Prince 捐赠，属接触后作品；"
                     "Wikidata 同一馆藏号 E12071 标 1825 年，与官方一致。",
                     "Kū, one of the four principal Hawaiian deities, governed war; such figures served pre-battle "
                     "ritual and sacrifice, documenting Hawaiian religion and kingship. **Date corrected**: the source data called it pre-contact, but PEM records it as early 19th century, gift of John T. Prince 1846 — a post-contact work; Wikidata gives 1825 for the same accession number E12071, consistent with PEM."),
  "sig_art_historical": ("夏威夷木雕神像以夸张的口部、突出的眉弓与紧绷的身体姿态著称，"
                         "本件为该风格的纪念碑式例证。",
                         "Hawaiian carved deity figures are distinguished by exaggerated mouths, projecting brow "
                         "ridges and taut bodily posture; this is a monumental example of the style."),
  "sig_rarity": ("夏威夷大型木雕神像传世极少，多数在 1819 年废除卡普制度时被毁；"
                 "本件为其后不久之作，北美收藏中同级者屈指可数。",
                 "Few large Hawaiian deity figures survive, most destroyed when the kapu system was abolished in 1819; this one dates from shortly after. Comparable pieces in North American collections can be counted on one hand."),
  "sig_institutional": ("PEM 的大洋洲收藏源自塞勒姆早期远洋航行，是本馆立馆根基之一；"
                        "本件为该板块的视觉与学术双重锚点，失去则整个板块塌陷。",
                        "PEM's Oceanic holdings originate in early Salem voyages and are foundational to the museum; "
                        "this figure anchors that section both visually and scholarly. Its loss would collapse the section."),
  "sig_category": ("大洋洲仪式人像雕刻中的首位，质量与稀缺性均居组内之冠。",
                   "First among the Oceanic ritual figure sculptures, leading its peer group in both quality and rarity."),
  "sig_cultural": ("能解释波利尼西亚的神系、卡普禁忌制度与酋长政治，"
                   "并牵出 1819 年宗教改革这一转折点。",
                   "Explains the Polynesian pantheon, the kapu system of prohibitions and chiefly politics, and "
                   "opens onto the religious revolution of 1819."),
  "sig_provenance": ("1846 年由 John T. Prince 捐赠（PEM 官方记录）。此前「早期航海者带回」的说法"
                     "未见官方佐证，捐赠人如何取得该像仍待查。",
                     "Gift of John T. Prince, 1846 (PEM official record). The earlier claim that it was brought back by early voyagers is not corroborated by the museum; how the donor obtained it remains unverified."),
  "sig_visual": ("纪念碑尺度木雕，造型威慑力强，是大洋洲馆的现场焦点；"
                 "即使不了解背景的普通观众也会驻足。",
                 "Monumental in scale and formidable in form, the focal point of the Oceanic gallery; it stops even "
                 "visitors with no background knowledge."),
  "sig_relations": ("独立展陈的可移动雕像，与展厅空间无固有关系。",
                    "A free-standing movable sculpture with no inherent relationship to the gallery space."),
 },
 "conf": {"hs": "high", "iu": "high", "vi": "high", "va": "high",
          "ce": "high", "cr": "high", "er": None},
 "missing": ["**已解决**：断代与馆藏号已由 PEM 官方记录确认（E12071，19 世纪早期，1846 年捐赠），"
             "源数据的「前接触期」为误，Wikidata 的 1825 年与官方一致",
             "缺 John T. Prince 取得该像的经过",
             "缺尺寸",
             "缺是否有夏威夷方面的归还诉求或协商记录（此类圣物常涉及）"],
 "source_tier": 1,
},

4: {  # 史贝霖 惠特兰船长夫妇成对肖像
 "sig": {
  "sig_historical": ("广州画师史贝霖（Spilum/Spoilum）为塞勒姆船长惠特兰夫妇所绘，"
                     "是中美早期直接贸易中人际往来的实物证据，约 18 世纪末至 19 世纪初。",
                     "Painted in Canton by the artist Spilum (Spoilum) for the Salem sea-captain Wheatland and his "
                     "wife; material evidence of personal contact in early direct Sino-American trade, c. late 18th–early 19th century."),
  "sig_art_historical": ("史贝霖是已知最早以西洋油画技法作肖像的中国画师之一，"
                         "本件为中国外销油画肖像的里程碑作品。",
                         "Spilum is among the earliest known Chinese painters to work in Western oil portraiture; "
                         "this pair is a landmark of the China-trade portrait genre."),
  "sig_rarity": ("成对留存且被绘者身份明确的外销油画肖像极少；"
                 "多数外销肖像已失去与具体人物的对应关系。",
                 "Very few China-trade oil portraits survive as a matched pair with the sitters identified; "
                 "most have lost their connection to specific individuals."),
  "sig_institutional": ("同时落在 PEM 两大支柱上——亚洲外销艺术与塞勒姆航海身份，"
                        "是把两条叙事缝合起来的关键物证。",
                        "Sits on both of PEM's pillars — Asian export art and Salem maritime identity — and is the key "
                        "object stitching the two narratives together."),
  "sig_category": ("中国外销西洋画法油画肖像组内的首位，尺幅与成对完整性均居先。",
                   "First in the peer group of China-trade Western-style oil portraits, leading in scale and pair completeness."),
  "sig_cultural": ("能解释广州十三行时期的订制机制：西方客户、中国画师、西洋技法、"
                   "本地作坊，四者如何在一件作品上交汇。",
                   "Explains the commissioning mechanism of the Canton hong era — how Western patron, Chinese painter, "
                   "European technique and local workshop converge in a single work."),
  "sig_provenance": ("被绘者为塞勒姆船长惠特兰，与东印度海洋学会圈层直接相关；"
                     "具体入藏年份与途径待查。",
                     "The sitters are the Salem captain Wheatland and his wife, directly connected to the East India "
                     "Marine Society circle; the acquisition year and route require verification."),
  "sig_visual": ("成对肖像并置展陈，人物尺度接近真人半身，"
                 "但画法平实、色彩克制，视觉张力不及大型器物。",
                 "Displayed as a facing pair at near half-life size, though the plain handling and restrained palette "
                 "give it less visual force than large three-dimensional objects."),
  "sig_relations": ("成对关系本身是构图与展陈的组成部分，两件须并置理解。",
                    "The pairing is itself part of the composition and display; the two must be read together."),
 },
 "conf": {"hs": "high", "iu": "high", "vi": "medium", "va": "medium",
          "ce": "high", "cr": "high", "er": None},
 "missing": ["缺确切创作年份", "缺尺寸与是否原框", "缺入藏年份与捐赠人",
             "史贝霖生卒与作品目录情况未核实"],
 "source_tier": 4,
},

7: {  # 拉什 船首像
 "sig": {
  "sig_historical": ("为美国早期海军护卫舰所雕的船首像，属美国建国初期海军建设的实物遗存。",
                     "A figurehead carved for an early United States Navy frigate; a surviving artefact of the "
                     "young republic's naval build-up."),
  "sig_art_historical": ("威廉·拉什（William Rush）是美国最早的本土雕塑家之一，"
                         "船首像是其主要创作门类，在美国雕塑史上有开创地位。",
                         "William Rush was among America's first native-born sculptors, and figureheads were his "
                         "principal genre; the form holds a founding place in American sculpture."),
  "sig_rarity": ("18 世纪末至 19 世纪初的美国大型船首像存世极少，"
                 "船只退役后多随船解体；本件为纪念碑尺度的完整例证。",
                 "Large American figureheads of the late 18th–early 19th century rarely survive, most having been "
                 "broken up with their ships; this is a complete example at monumental scale."),
  "sig_institutional": ("海事馆的体量与视觉核心，直接承载 PEM 的塞勒姆航海身份，"
                        "是该板块无可替代的实物。",
                        "The scale and visual anchor of the Maritime Gallery, embodying PEM's Salem seafaring identity; "
                        "irreplaceable within that section."),
  "sig_category": ("本馆唯一的大型船首像，在该类别中无竞争者。",
                   "The museum's only large figurehead; no competitor in the category."),
  "sig_cultural": ("能解释船首像的功能、美国早期海军的象征表达，"
                   "以及塞勒姆港与国家海权的关系。",
                   "Explains the function of figureheads, the symbolic language of the early US Navy, and Salem's "
                   "relationship to national sea power."),
  "sig_provenance": ("归属拉什的依据未见说明，需核实是否有档案或款识佐证。",
                     "The basis for the attribution to Rush is not documented; archival or inscriptional evidence "
                     "requires verification."),
  "sig_visual": ("纪念碑尺度木雕，仰视观看，是海事馆一进门的视觉焦点。",
                 "A monumental carving viewed from below, forming the visual focus on entering the Maritime Gallery."),
  "sig_relations": ("原为船体构件，现脱离母体单独展陈，与原船的关系仅存于文献。",
                    "Originally part of a ship's structure, now displayed detached; its relationship to the vessel "
                    "survives only in documentation."),
 },
 "conf": {"hs": "high", "iu": "high", "vi": "high", "va": "high",
          "ce": "medium", "cr": "high", "er": None},
 "missing": ["缺具体舰名与下水年份（源数据只写 USS Frigate）",
             "拉什的归属证据待核实——同期费城另有多位船首像雕刻者",
             "Wikidata 另有 PEM 的 Female figurehead M27185（Simeon Skillin Jr., 1805），需确认非同一件",
             "缺尺寸与木材"],
 "source_tier": 4,
},

8: {  # 中国外销纹章大潘趣碗
 "sig": {
  "sig_historical": ("东印度海洋学会创始船长旧藏。该学会 1799 年成立，其收藏即 PEM 的起点，"
                     "本件因此是博物馆自身来历的实物凭证。",
                     "Owned by founding captains of the East India Marine Society. Founded in 1799, the Society's "
                     "collection is the origin of PEM itself, making this bowl material proof of the museum's own beginnings."),
  "sig_art_historical": ("广彩大型潘趣碗是清代外销瓷中规格最高的器类之一，"
                         "纹章定制反映西方客户的身份表达需求。",
                         "Large Canton famille-rose punch bowls are among the most ambitious forms of Qing export "
                         "porcelain; armorial commissions reflect Western patrons' assertion of status."),
  "sig_rarity": ("外销瓷本身量大，但**来源可考证到具体船长与学会**的极少；"
                 "本件的稀缺性来自来源链而非器物本身。",
                 "Export porcelain survives in quantity, but pieces traceable to named captains and to the Society "
                 "itself are very rare; the rarity here lies in the provenance rather than the object."),
  "sig_institutional": ("建馆信物。若失去，PEM 失去的不是一件藏品，而是自身来历的物证，"
                        "IU 在全部外销瓷中最高。",
                        "The museum's founding relic. Its loss would remove not an object but the physical evidence of "
                        "PEM's own origin; the highest institutional significance among all the export porcelain."),
  "sig_category": ("中国外销瓷组四件之首，与量产广彩盘、茶杯组拉开本质差距。",
                   "First among the four Chinese export porcelains, categorically apart from the mass-produced "
                   "Canton plate and teacup group."),
  "sig_cultural": ("能同时解释广州外销贸易、纹章定制习俗，以及美国早期博物馆"
                   "由船长收藏起家的形成过程。",
                   "Explains Canton's export trade, the custom of armorial commissioning, and how early American "
                   "museums grew out of sea-captains' collections."),
  "sig_provenance": ("递藏链是本件价值的核心：由学会创始船长携回并入藏，"
                     "构成 PEM 藏品序列的起点之一。具体船长姓名待查。",
                     "The chain of ownership is the core of its value: brought back and deposited by founding captains "
                     "of the Society, forming one of the starting points of PEM's holdings. The captains' names require verification."),
  "sig_visual": ("大尺寸瓷碗，粉彩纹饰繁密，但器物本身高度有限，"
                 "现场冲击力不及大型雕塑或建筑。",
                 "A large bowl with dense famille-rose decoration, though limited in height; less commanding on site "
                 "than large sculpture or architecture."),
  "sig_relations": ("独立器物，与展厅空间无固有关系；"
                    "但与馆内其他东印度海洋学会旧藏构成来源上的成组关系。",
                    "A free-standing object with no inherent spatial relationship, though it forms a provenance group "
                    "with other East India Marine Society holdings."),
 },
 "conf": {"hs": "high", "iu": "high", "vi": "medium", "va": "medium",
          "ce": "high", "cr": "high", "er": None},
 "missing": ["缺创始船长的具体姓名与入藏年份",
             "缺纹章所属家族的辨识",
             "缺尺寸与确切年代", "缺 PEM 官方藏品编号"],
 "source_tier": 4,
},

12: {  # 朝鲜平壤道牧使欢迎宴会屏风
 "sig": {
  "sig_historical": ("描绘朝鲜王朝地方长官到任的欢迎宴会，是研究朝鲜官僚制度、"
                     "地方礼仪与宴飨规格的图像史料。",
                     "Depicts the welcoming banquet for a newly arrived provincial governor of the Joseon dynasty; "
                     "pictorial evidence for Joseon bureaucratic institutions, provincial ritual and banquet protocol."),
  "sig_art_historical": ("朝鲜宫廷与官署纪事屏风（記錄畫）是独立画科，"
                         "以俯瞰式构图铺陈人物与建筑，本件属该画科的大幅例证。",
                         "Joseon documentary screens are a distinct genre, laying out figures and architecture in "
                         "elevated perspective; this is a large-format example of the type."),
  "sig_rarity": ("此类大幅纪事屏风多藏于韩国，"
                 "美国收藏中规格与保存状况俱佳者屈指可数。",
                 "Large documentary screens of this kind are mostly held in Korea; few in American collections match "
                 "this scale and condition."),
  "sig_institutional": ("韩国艺术是 PEM 的明确强项，本件为该板块的代表作；"
                        "失去则韩国收藏的代表性显著受损。",
                        "Korean art is a declared strength of PEM and this screen represents it; its loss would "
                        "markedly weaken the section's standing."),
  "sig_category": ("朝鲜屏风绘画组两件之首，信息量与工坊等级均高于同组的山水屏风。",
                   "First of the two Joseon screens, exceeding the landscape screen in both information content and "
                   "workshop rank."),
  "sig_cultural": ("能解释朝鲜的官阶制度、地方治理与宴飨礼仪，"
                   "叙事密度在全馆东亚藏品中居前。",
                   "Explains Joseon rank structure, provincial governance and banquet ritual; among the most narratively "
                   "dense East Asian holdings in the museum."),
  "sig_provenance": ("入藏途径未见记载，需查证是否与 PEM 早期东亚收藏同源。",
                     "The acquisition route is undocumented; verification is needed as to whether it shares an origin "
                     "with PEM's early East Asian holdings."),
  "sig_visual": ("大幅多曲屏风，人物众多、场面铺陈，"
                 "现场可读性强，但需要一定时间辨认细节。",
                 "A large multi-panel screen crowded with figures and incident; highly legible on site, though it "
                 "rewards time spent picking out detail."),
  "sig_relations": ("独立可移动器物；多曲连屏内部构成横向展开的叙事序列。",
                    "A free-standing movable object whose multiple panels form a laterally unfolding narrative sequence."),
 },
 "conf": {"hs": "high", "iu": "high", "vi": "high", "va": "medium",
          "ce": "high", "cr": "high", "er": None},
 "missing": ["缺确切年代（朝鲜王朝跨度五百余年）",
             "缺被描绘的具体牧使姓名与事件年份",
             "缺尺寸、材质（绢本？纸本？）与曲数",
             "缺入藏记录"],
 "source_tier": 4,
},

13: {  # 毛利玉质战争权杖
 "sig": {
  "sig_historical": ("前接触期毛利高阶权杖（mere pounamu），"
                     "是酋长身份与战争权威的象征物，属毛利社会等级制度的核心器物。",
                     "A pre-contact Māori chiefly club (mere pounamu), emblem of rank and martial authority and a "
                     "core object of Māori social hierarchy."),
  "sig_art_historical": ("软玉（pounamu）加工需长时间研磨，器形对称、刃缘薄利，"
                         "是毛利石作工艺的最高体现。",
                         "Working nephrite (pounamu) required prolonged grinding; the symmetrical form and finely "
                         "tapered edge represent the summit of Māori lapidary craft."),
  "sig_rarity": ("前接触期且有明确早期采集来源的 mere pounamu 存世稀少；"
                 "多数流散品已失去采集脉络。",
                 "Pre-contact mere pounamu with a documented early collection history are scarce; most dispersed "
                 "examples have lost their collecting context."),
  "sig_institutional": ("来源为新英格兰早期航海者，与 PEM 大洋洲收藏的形成史直接相关；"
                        "是毛利一支的代表，与夏威夷库神像分属不同文化支脉、互不替代。",
                        "Collected by early New England voyagers, tying directly to the formation of PEM's Oceanic "
                        "holdings; it represents the Māori strand, distinct from and not interchangeable with the Hawaiian Kū figure."),
  "sig_category": ("大洋洲武器组两件之首，材质等级与来源可考性均高于塔希提战棒。",
                   "First of the two Oceanic weapons, exceeding the Tahitian club in both material rank and "
                   "documented provenance."),
  "sig_cultural": ("能解释毛利的 mana（威权）观念、玉料的圣性，"
                   "以及传家宝（taonga）在世代间的传递制度。",
                   "Explains the Māori concept of mana, the sacredness of pounamu, and the transmission of taonga "
                   "across generations."),
  "sig_provenance": ("「exceptional provenance from early New England voyagers」为源数据表述，"
                     "但未给出航次、采集者与年份，是本件最需要补的一环。",
                     "The source data claims 'exceptional provenance from early New England voyagers' but names no "
                     "voyage, collector or date; this is the single most important gap for this object."),
  "sig_visual": ("手持尺度的扁平玉器，温润有光泽，"
                 "但体量小，需近距离观看，现场冲击力有限。",
                 "A hand-sized flat nephrite implement, lustrous to the eye, but small in scale and requiring close "
                 "viewing; limited visual impact on site."),
  "sig_relations": ("独立器物，与展厅空间无固有关系。",
                    "A free-standing object with no inherent relationship to the gallery space."),
 },
 "conf": {"hs": "high", "iu": "high", "vi": "medium", "va": "medium",
          "ce": "high", "cr": "high", "er": None},
 "missing": ["缺采集航次、采集者与年份——源数据称来源卓越却无细节，是最大缺口",
             "缺是否有毛利方面的归还诉求或协商记录（此类圣物常涉及）",
             "缺尺寸与玉料产地（南岛何处）",
             "缺 PEM 官方藏品编号"],
 "source_tier": 4,
},

5: {"sig": {
  "sig_historical": ("莱恩 1849 年作，描绘缅因州肯尼贝克河下游的运木帆船，"
                     "是研究 19 世纪中叶新英格兰木材水运的图像材料。",
                     "Painted by Lane in 1849, showing lumber brigs on the lower Kennebec River in Maine; "
                     "visual material for the study of mid-19th-century New England timber shipping."),
  "sig_art_historical": ("光亮主义（Luminism）代表画家的成熟期作品，"
                         "以静谧水面与低平光线著称，被视为其艺术视野的重要表达之一。",
                         "A mature work by a leading Luminist, marked by still water and low raking light; "
                         "regarded as one of the premier expressions of his artistic vision."),
  "sig_rarity": ("莱恩传世作品数量可观，本件并非孤品；"
                 "稀缺性在于它是 PEM 藏莱恩作品中质量最高者。",
                 "Lane's surviving output is substantial and this is not unique; its rarity lies in being the finest "
                 "Lane in PEM's holdings."),
  "sig_institutional": ("美国绘画板块的最佳单件，但 PEM 的身份并不建立在美国绘画上；"
                        "莱恩精品在 Cape Ann 与波士顿另有分布。",
                        "The finest single American painting here, though PEM's identity does not rest on American "
                        "painting; major Lanes are also held at Cape Ann and in Boston."),
  "sig_category": ("美国光亮主义海景组两件之首，与同组的莱恩小稿差距显著。",
                   "First of the two American Luminist marines, clearly ahead of the small Lane sketch in the same group."),
  "sig_cultural": ("能解释光亮主义的美学取向与新英格兰海运经济，但叙事面较窄。",
                   "Explains Luminist aesthetics and the New England shipping economy, though on a relatively narrow front."),
  "sig_provenance": ("2014 年 Serena M. Hatch 为纪念 Francis W. Hatch 捐赠。"
                     "这是本馆少数有明确捐赠记录的作品之一。",
                     "Gift of Serena M. Hatch in honour of Francis W. Hatch, 2014 — one of the few works here with a "
                     "documented credit line."),
  "sig_visual": ("中等尺幅油画，暮色调性统一，现场观感安静而非震撼。",
                 "A medium-format oil of unified twilight tonality; quiet rather than arresting on site."),
  "sig_relations": ("独立画作，与展厅空间无固有关系。",
                    "A free-standing painting with no inherent relationship to the gallery space."),
 }, "conf": {"hs":"high","iu":"medium","vi":"medium","va":"medium","ce":"medium","cr":"high","er":None},
 "missing": ["缺尺寸与是否原框", "缺 PEM 官方藏品编号",
             "本件在莱恩作品目录（Fitz Henry Lane Online, inv. 258）中已有著录，可升级为 Tier 2 来源"],
 "source_tier": 3},

6: {"sig": {
  "sig_historical": ("科普利殖民地时期肖像，被绘者为波士顿名门沃尔多家族女性，"
                     "反映独立战争前新英格兰上层的社会形象建构。",
                     "A colonial-period Copley portrait of a woman of the prominent Boston Waldo family, reflecting how "
                     "New England's upper class constructed its image before the Revolution."),
  "sig_art_historical": ("科普利是北美殖民地时期最重要的肖像画家，"
                         "本件的织物质感处理是其技法标志。",
                         "Copley is the foremost portraitist of colonial North America; the handling of fabric here is "
                         "characteristic of his technique."),
  "sig_rarity": ("科普利传世肖像数量较多，本件非孤品。",
                 "Copley portraits survive in some number; this is not a unique work."),
  "sig_institutional": ("质量高，但科普利在邻近的波士顿 MFA 藏量与等级更强；"
                        "PEM 的身份并不依赖它。",
                        "A fine work, but Copley is held in greater number and quality at the nearby Boston MFA; "
                        "PEM's identity does not depend on it."),
  "sig_category": ("美国殖民地肖像画组四件之首。",
                   "First among the four American colonial portraits."),
  "sig_cultural": ("能解释殖民地精英的身份表达与服饰礼仪。",
                   "Explains elite self-presentation and dress convention in the colonies."),
  "sig_provenance": ("递藏与入藏记录缺失。", "Chain of ownership and acquisition record are missing."),
  "sig_visual": ("接近真人尺度的半身像，织物描绘精致，但构图与色调保守。",
                 "A near-life-size half-length with finely rendered fabric, though conservative in composition and tone."),
  "sig_relations": ("独立画作。", "A free-standing painting."),
 }, "conf": {"hs":"high","iu":"medium","vi":"medium","va":"medium","ce":"medium","cr":"high","er":None},
 "missing": ["缺创作年份", "缺被绘者的确切身份与生卒", "缺尺寸与入藏记录",
             "需查是否见于科普利作品目录"],
 "source_tier": 4},

9: {"sig": {
  "sig_historical": ("1279 年镰仓时期地藏菩萨像，带纪年，"
                     "是日本镰仓佛教造像在美国的重要遗存。",
                     "A dated Jizō Bosatsu of 1279, Kamakura period; a significant survival of Japanese Kamakura "
                     "Buddhist sculpture in the United States."),
  "sig_art_historical": ("镰仓造像以写实倾向与庆派技法著称，"
                         "本件保留原装金漆，可见当时的表面工艺。",
                         "Kamakura sculpture is known for its realist tendency and Kei-school technique; the original "
                         "gilt lacquer surviving here shows the period's surface treatment."),
  "sig_rarity": ("美国境内保存完好的日本纪念碑式佛教木雕数量有限，"
                 "带确切纪年者更少。",
                 "Well-preserved monumental Japanese Buddhist wood sculpture is limited in the United States, and "
                 "dated examples rarer still."),
  "sig_institutional": ("日本佛教雕塑在本馆仅此一件，但 PEM 的核心身份是贸易与航海，"
                        "宗教造像不属支柱板块。",
                        "The museum's only Japanese Buddhist sculpture, though PEM's core identity is trade and "
                        "seafaring; religious sculpture is not a pillar."),
  "sig_category": ("本馆唯一的日本佛教雕塑，类别内无竞争者。",
                   "The museum's only Japanese Buddhist sculpture; no competitor in the category."),
  "sig_cultural": ("能解释地藏信仰、镰仓佛教的世俗化，以及日本木雕的髹漆工艺。",
                   "Explains the Jizō cult, the popularisation of Kamakura Buddhism, and Japanese lacquered "
                   "wood-sculpture technique."),
  "sig_provenance": ("原属寺院与流出经过未见记载——此类造像的来源问题近年受关注，需查证。",
                     "The originating temple and the circumstances of its removal are undocumented; provenance for such "
                     "figures has drawn scrutiny in recent years and requires verification."),
  "sig_visual": ("纪念碑尺度立像，金漆表面在展陈灯光下有明显效果。",
                 "A monumental standing figure whose gilt surface reads strongly under gallery lighting."),
  "sig_relations": ("原为寺院供奉的一组之一，现单独展陈，与原语境脱离。",
                    "Originally one of a temple ensemble, now displayed alone and severed from its context."),
 }, "conf": {"hs":"high","iu":"medium","vi":"high","va":"medium","ce":"high","cr":"high","er":None},
 "missing": ["缺原属寺院与流出经过（来源合法性问题）", "缺尺寸与造像铭文内容",
             "1279 年纪年的依据（胎内铭？墨书？）未见说明"],
 "source_tier": 4},

10: {"sig": {
  "sig_historical": ("麦金太尔为加德纳-平格里宅所作的木雕构件，"
                     "该宅 1804–05 年建成，是塞勒姆联邦时期建筑的代表。",
                     "Carvings by McIntire for the Gardner-Pingree House, built 1804–05 and a leading example of "
                     "Salem's Federal-period architecture."),
  "sig_art_historical": ("塞缪尔·麦金太尔是美国联邦风格最负盛名的建筑师兼木雕师，"
                         "其雕饰母题（麦穗、瓮、花篮）已成为该风格的标识。",
                         "Samuel McIntire is the best-known architect-carver of the American Federal style; his motifs "
                         "— wheat sheaves, urns, baskets — have become emblems of it."),
  "sig_rarity": ("麦金太尔作品多存于塞勒姆各宅，本件非孤例；"
                 "但原位成组保存者较少。",
                 "McIntire's work survives in a number of Salem houses; this is not unique, though in-situ groups are "
                 "less common."),
  "sig_institutional": ("麦金太尔属塞勒姆本地身份，与 PEM 的城市根基直接相关；"
                        "且该宅由 PEM 管理，构成馆藏与historic house 的连接。",
                        "McIntire belongs to Salem's own identity, tied directly to PEM's civic roots; the house is "
                        "administered by PEM, linking collection and historic house."),
  "sig_category": ("麦金太尔建筑木雕组五件之首，是唯一的原位成组构件。",
                   "First of the five McIntire carvings and the only in-situ group."),
  "sig_cultural": ("能解释联邦风格的古典母题来源与塞勒姆商人阶层的居住品味。",
                   "Explains the classical sources of the Federal style and the domestic taste of Salem's merchant class."),
  "sig_provenance": ("原位保存，来源明确，无流转问题。",
                     "Preserved in situ with clear provenance and no transfer issues."),
  "sig_visual": ("建筑构件，需在宅内语境中观看；单看木雕本身尺度有限。",
                 "Architectural elements that must be seen in the context of the house; the carvings alone are modest in scale."),
  "sig_relations": ("**原位构件**，与加德纳-平格里宅的空间、门窗、壁炉位置构成整体关系，"
                    "是全馆少数 ER 真正适用的对象之一。",
                    "In-situ elements integral to the spaces, openings and chimney-pieces of the Gardner-Pingree House; "
                    "one of the few objects here to which ER genuinely applies."),
 }, "conf": {"hs":"high","iu":"high","vi":"medium","va":"medium","ce":"high","cr":"high","er":"high"},
 "missing": ["缺构件的具体部位清单（门罩？檐口？壁炉？）", "缺是否有麦金太尔工作室的档案佐证",
             "宅邸本身是否应作为独立的 node 级评级对象，尚未决定"],
 "source_tier": 4},

11: {"sig": {
  "sig_historical": ("辛普森为当代在世玻璃艺术家，作品属 20 世纪末以来的工作室玻璃运动，"
                     "历史纵深有限。",
                     "Simpson is a living contemporary glass artist; the work belongs to the studio glass movement of "
                     "the late 20th century onward and has limited historical depth."),
  "sig_art_historical": ("星球系列是其个人标志母题，在美国工作室玻璃中知名度较高，"
                         "但未构成艺术史上的转折。",
                         "The planet series is his signature motif and well known within American studio glass, though "
                         "it marks no turning point in art history."),
  "sig_rarity": ("艺术家仍在创作，同母题作品持续产出；"
                 "本件的稀缺性来自尺寸而非母题。",
                 "The artist continues to work and the motif is produced on an ongoing basis; the rarity here is one of "
                 "scale, not of subject."),
  "sig_institutional": ("PEM 当代板块的标志物，宣传中常用；"
                        "但与本馆的历史身份（贸易、航海、亚洲）无关联。",
                        "A signature piece of PEM's contemporary section and often used in publicity, but unconnected to "
                        "the museum's historical identity of trade, seafaring and Asia."),
  "sig_category": ("美国艺术玻璃组四件之首，体量与知名度居先。",
                   "First of the four American art glasses, leading in both scale and recognition."),
  "sig_cultural": ("教育与叙事承载力弱，难以借它解释某个时代或制度。",
                   "Weak in educational and narrative capacity; it cannot readily be used to explain a period or institution."),
  "sig_provenance": ("入藏方式与年份未见记载。", "Acquisition method and date are undocumented."),
  "sig_visual": ("大型玻璃球，内部气泡与色彩层次在灯光下效果突出，"
                 "对普通观众的即时吸引力是全馆最强之一。",
                 "A large glass sphere whose internal bubbles and colour layers read powerfully under light; among the "
                 "museum's strongest immediate draws for a general visitor."),
  "sig_relations": ("独立器物。", "A free-standing object."),
 }, "conf": {"hs":"high","iu":"medium","vi":"high","va":"high","ce":"high","cr":"high","er":None},
 "missing": ["缺创作年份与尺寸", "缺入藏方式（购藏？艺术家捐赠？）"],
 "source_tier": 4},

}
