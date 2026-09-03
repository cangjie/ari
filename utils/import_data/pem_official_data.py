#!/usr/bin/env python3
"""PEM 官网 18 个藏品栏目页抓回的逐件编目数据（2026-08-31）。

来源：https://www.pem.org/the-pem-collection/<栏目>
提案第 4 节 **Tier 1**：馆方自己发布的编目数据，不是宣传文案 —— 每件都带
馆藏号、材质、年代与「Gift of …, <年>」。

【为什么把抓回的原文逐字存在这里】
库里原有的 `source_key='pem_official'` 61 条是当初在会话里逐件核实后直接入库的，
**仓库里没有任何脚本能重新生成它们**（2026-08-31 实测）。结果是这两张表不敢
DROP 重建，改结构只能 ALTER。本文件就是为了不再犯同一个错：抓取结果落进仓库，
谁都能重跑 meta_fill_official_pem.py 得到同样的行。

【为什么存原始文本块而不是 Python 字面量】
逐条转写成 dict 要人手搬运两百多行，抄错一个馆藏号不会有任何报错 —— 而这批数据
的全部价值就在于它是**可核对的外部事实**。存原文，解析交给代码，改动只可能是
整块替换，不可能是某一格被悄悄改掉。要核对就打开上面的 URL 逐行比。

字段次序（抓取时即按此固定）：
    TITLE ~ ARTIST ~ DATE ~ MATERIAL ~ ACCESSION ~ ACQUISITION ~ CULTURE ~ ONVIEW
`n/a` 表示页面上没有这一项，不是「不知道」。
"""
from __future__ import annotations

import re

BASE = "https://www.pem.org/the-pem-collection/"

# architecture 栏目页只有概述，没有逐件编目数据，故不在此列（抓取返回 NONE）。
RAW: dict[str, str] = {

"african-art": """
Ceremonial axe ~ Artist (possibly Makonde) near Lake Malawi ~ mid-19th century ~ Wood, iron, and glass beads ~ E6765 ~ Gift of Edward D. Ropes, 1859 ~ Malawi, Mozambique, or Tanzania ~ n/a
Mask ~ Grebo or Kru artist near Cape Palmas, Liberia ~ 1830s or earlier ~ Wood, ceramic, iron nails, and pigment ~ E6764 ~ Gift of Dr. George A. Perkins, about 1859 ~ Liberia ~ n/a
Drum ~ Ga artist in Ghana ~ late 19th century ~ Wood, fiber, animal hide, and pigment ~ E6756 ~ Gift of T. C. W. Nash, 1890 ~ Ghana ~ n/a
Barkcloth ~ Baganda artist in Uganda ~ late 19th-early 20th century ~ Fig tree bark and pigment ~ E23804 ~ Gift of the estate of Mary Brooks, 1941 ~ Uganda ~ n/a
Headrest ~ Zulu artist in South Africa ~ mid-19th century ~ Wood ~ E53566 ~ Transferred to Peabody Essex Museum by the Andover Newton Theological School, 2017 ~ South Africa ~ n/a
West African Outlook ~ Charles Sekano (born 1943, South Africa) ~ about 2000 ~ Oil pastel on paper ~ E301988 ~ Museum Purchase, 2002 ~ South Africa ~ n/a
Figure group ~ Kongo artist in Loango region ~ early to mid 19th century ~ Ivory ~ E16924 ~ Museum purchase, 1917 ~ Democratic Republic of the Congo or Republic of the Congo ~ n/a
Sensul (Folding icons) in original embossed leather case ~ Artist in Ethiopia ~ 15th-early 16th century ~ Parchment, pigments, and leather ~ E67892 ~ Gift of Charles R. and Elizabeth C. Langmuir, 1979 ~ Ethiopia ~ n/a
Mwaash aMbooy mask ~ Kuba artist in Democratic Republic of the Congo ~ 19th century ~ Raffia, leopard cloth, leopard fur, cowrie shells, and glass beads ~ E14376 ~ Gift of Dr. Charles Goddard Weld, 1910 ~ Democratic Republic of the Congo ~ n/a
Sowo-wui mask ~ Mende artist in Sierra Leone ~ late 19th-early 20th century ~ Bombax wood ~ E28249 ~ Gift of the estate of Isabel Anderson, 1949 ~ Sierra Leone ~ ON VIEW
Kiti cha enzi (chair of power) ~ Swahili artists in Zanzibar ~ early 19th century ~ Wood, bone, and plant fiber ~ E33723 ~ Gift of Elizabeth Williams, Mary Ropes Trumbull, and Ruth Ropes, 1940 ~ Zanzibar ~ ON VIEW
Finger piano ~ Artist in South Africa ~ 19th century ~ Wood, iron, and brass ~ E62935 ~ Museum purchase, made possible by the Anna Pingree Phillips Fund and the Edward Daland Lovejoy Fund, 1979 ~ South Africa ~ n/a
""",

"american-art": """
Weight ~ Alison Saar ~ 2012 ~ Fiberglass coated with coal dust-infused resin, found metal and wood objects, and rope ~ 2018.35.1A-E ~ Museum purchase, made possible by the Willoughby Stuart Memorial Fund ~ United States ~ On view in On This Ground: Being and Belonging in America
Salem Common on Training Day ~ George Ropes Jr. ~ 1808 ~ Oil on canvas ~ 107924 ~ Museum purchase, 1919 ~ United States ~ On view in On This Ground: Being and Belonging in America
Portrait of Ahmad bin Na'aman ~ Edward Ludlow Mooney ~ 1840 ~ Oil on canvas ~ M4473 ~ Gift of Mrs. William P. McMullan, 1918 ~ United States ~ n/a
Webster House, Provincetown ~ E. Ambrose Webster ~ 1931 ~ Oil on canvas ~ 2015.44.66 ~ The Sheila W. and Samuel M. Robbins Collection ~ United States ~ On view in the American Art Gallery
Untitled ~ Felrath Hines ~ 1967-73 ~ Oil on canvas ~ 2014.59.2 ~ Gift of Dorothy Fisher, widow of the artist ~ United States ~ n/a
East Headland, Appledore, Isles of Shoals ~ Childe Hassam ~ 1911 ~ Oil on canvas ~ 2018.72.1 ~ Gift of Peter S. Lynch in memory of Carolyn A. Lynch ~ United States ~ n/a
Twilight on the Kennebec ~ Fitz Henry Lane ~ 1849 ~ Oil on canvas ~ M22672 ~ Gift of Serena M. Hatch in honor of Francis W. Hatch, 2014 ~ United States ~ On view in On This Ground: Being and Belonging in America
Portrait of Judge Richard Saltonstall ~ Robert Feke ~ ca. 1750 ~ Oil on canvas ~ 100183 ~ n/a ~ United States ~ On view in On This Ground: Being and Belonging in America
Pastures by the Sea ~ Fidelia Bridges ~ 1880-89 ~ Oil on canvas ~ 106746 ~ Gift of the artist, 1918 ~ United States ~ On view in On This Ground: Being and Belonging in America
Portrait of Sarah Erving Waldo ~ John Singleton Copley ~ 1764-1765 ~ Oil on canvas ~ M12561 ~ Gift of Mr. and Mrs. Charles Edward Cotting, 1976 ~ United States ~ On view in On This Ground: Being and Belonging in America
Rich Black Specimen #460 ~ Hank Willis Thomas ~ 2017 ~ Aluminum with powder coat and automotive paint ~ 2019.23.1ab ~ Museum Purchase, made possible by the Elizabeth Rogers Acquisition Fund ~ United States ~ On view in On This Ground: Being and Belonging in America
La belle epoque ~ Grace Hartigan ~ 1995 ~ Oil on canvas ~ 138704 ~ Gift of Fay Chandler, 2008 ~ United States ~ On view in On This Ground: Being and Belonging in America
""",

"american-decorative-art": """
Talavera Poblana Basin ~ Artists in Mexico ~ 1700-1730 ~ Tin-glazed earthenware ~ 2019.9.1 ~ Museum purchase, in honor of Dr. H. A. Crosby Forbes ~ n/a ~ n/a
Cabinet ~ Artist in Virginia and Mary Scheier (1908-2007, United States) ~ constructed 1874, altered 1937 ~ Walnut ~ 2023.46.1 ~ Museum purchase ~ n/a ~ n/a
Brooch ~ Tiffany & Company (1837-present, United States) ~ 1910 ~ Gold, chrysoprase ~ 2023.31.2 ~ Gift of Jody Sataloff in memory of Dr. and Mrs. Joseph Sataloff ~ n/a ~ n/a
Sampler ~ Artist in Mexico ~ late 1700s ~ Cotton and silk ~ E22846 ~ Gift of Dr. E. D. Lovejoy, 1937 ~ n/a ~ n/a
Dwarf Clock ~ Samuel Mulliken (1761-1847, United States) ~ 1790 ~ Mahogany and pine, brass movement ~ 137713 ~ Museum purchase, 1994 ~ n/a ~ n/a
Valuables cabinet owned by Joseph and Bathsheba Pope ~ James Symonds (b. 1633, modern-day United States) ~ 1679 ~ Oak, maple, iron, and paint ~ 138011 ~ Museum purchase, made possible by anonymous donors, 2000 ~ n/a ~ n/a
Pictorial Sampler ~ Mary Richardson (1772-1824, United States) ~ 1783 ~ Silk, linen ~ 123559 ~ Gift of Lucy L. Caller, 1938 ~ n/a ~ n/a
Chimneypiece from the Simon Forrester house ~ Artists from the North Shore, Massachusetts ~ 1791 ~ Carved and painted pine ~ 117596 ~ Gift of Francis Shaw, 1924 ~ n/a ~ ON VIEW
Velocipede ~ Artists in the United States ~ 1855-1865 ~ Wood, paint, metal ~ 101303 ~ Gift of Frank D. Hutchinson, 1908 ~ n/a ~ ON VIEW
Pear ~ Samuel McIntire (1757-1811, United States), and Michele Felice Corne (1752-1845, United States) ~ 1807 ~ Painted pine, iron ~ 106944 ~ Gift of J. Tucker and T. Pickering, 1821 ~ n/a ~ ON VIEW
Side chair ~ Nathaniel Gould (1734-1781, United States) ~ 1763-68 ~ Mahogany and reproduction upholstery ~ 130002 ~ Gift of John H. Ricketson, 1961 ~ n/a ~ ON VIEW
Dressing chest ~ Thomas Seymour (1771-1848, United States), Carving attributed to Thomas Wightman (1759-1827) ~ about 1810 ~ Mahogany, bird's-eye maple, satinwood veneer, brass, and glass ~ 122350 ~ Gift of Miriam and Francis Shaw Jr., 1935 ~ n/a ~ ON VIEW
Great chair ~ Thomas Dennis (1638-1706, modern-day United States) ~ about 1670 ~ Oak ~ 108886 ~ Gift of Robert Brookhouse, 1821 ~ n/a ~ ON VIEW
Jug ~ Thomas W. Commeraw (1771-1819, United States) ~ 1800-1819 ~ Salt-glazed stoneware and cobalt ~ 103074 ~ Museum purchase, 1911 ~ n/a ~ ON VIEW
Isabella ~ Toots Zynsky (b. 1951, United States) ~ 2003 ~ Filet de verre ~ 2022.6.230 ~ Gift of Carl and Betty Pforzheimer ~ n/a ~ ON VIEW
Teapot in Hand ~ Michelle Erickson (b. 1960, United States) ~ 2003 ~ Porcelain, stoneware, tin-glazed earthenware, and gold leaf ~ 138410.AB ~ Museum purchase, 2003 ~ n/a ~ ON VIEW
Coffee service ~ Michael Banner (b. 1939, United States) and Maureen Banner (b. 1946, United States) ~ 1998 ~ Silver ~ 137986.1-3AB, 4 ~ Museum purchase in honor of the Museum's Bicentennial Year, 1999 ~ n/a ~ ON VIEW
""",

"asian-export-art": """
Charger with the Okeover family coat of arms ~ Artists in Jingdezhen, China ~ 1740 or 1743 ~ Porcelain ~ E82042 ~ Museum purchase, made possible by an anonymous donor, 1987 ~ n/a ~ ON VIEW
A complete set of Chinese wallpaper ~ Artists in Guangzhou, China ~ about 1800 ~ Opaque watercolor on mulberry paper ~ AE86556.A-S ~ Museum purchase in honor of William R. Sargent, 2006 ~ n/a ~ ON VIEW
Chair ~ Artists in Visakhapatnam, India ~ 1760-70 ~ Ebony, inlaid ivory, cane, and lac ~ AE85784 ~ Museum purchase, made possible by an anonymous donor, 2001 ~ n/a ~ ON VIEW
Tea Production in China ~ Artists in Guangzhou, China ~ about 1800 ~ Oil on canvas ~ M25794 ~ Museum purchase, made possible by an anonymous donor, 1993 ~ n/a ~ ON VIEW
Tea packer and tea porter ~ Artists in Guangzhou, China ~ about 1803 ~ Unfired clay, paint, wood, and human hair ~ E7100 and E7101 ~ Gift of Captain Richard Wheatland, 1803 ~ n/a ~ ON VIEW
Teapot ~ Artists in southern China ~ about 1680 ~ Silver ~ E82766.AB ~ Museum purchase, made possible by an anonymous donor, 1989 ~ n/a ~ ON VIEW
Shuja-ud-Daula and His Sons ~ Artists in Guangzhou, China ~ after 1797 ~ Reverse painting on glass ~ AE85329 ~ Museum purchase, and gift of Jeremy Ltd., London, 1996 ~ n/a ~ ON VIEW
Portable shrine ~ Attributed to the School of Giovanni Niccolo and the Jesuit Seminary workshop, Kyushu, Japan ~ about 1597 ~ Oil on wood panel, in a lacquered wood case with mother-of-pearl inlay ~ AE85752 ~ Museum purchase, made possible by an anonymous donor, 2000 ~ n/a ~ ON VIEW
Christ child ~ Artists in Goa, India, or Sri Lanka ~ 1550-1650 ~ Rock crystal with gold, rubies, and sapphires ~ E85219 ~ Museum purchase, made possible by an anonymous donor, 1996 ~ n/a ~ ON VIEW
Mounted crow cup ~ Artists in Jingdezhen, China, and Peter Wiber (active 1603-1641, Germany) ~ about 1610 ~ Porcelain with gilded-silver mounts ~ AE85461 ~ Anonymous gift, 2001 ~ n/a ~ ON VIEW
Figure of a bijin (beautiful woman) ~ Artists in Arita, Japan ~ 1690-1710 ~ Porcelain ~ AE85873 ~ Gift, the Copeland Collection, 2001 ~ n/a ~ ON VIEW
Ewer ~ Artists in Gujarat, India ~ 1570-1620 ~ Wood, mother-of-pearl, and brass ~ AE85718 ~ Museum purchase, made possible by an anonymous donor, 2000 ~ n/a ~ ON VIEW
Dressing table ~ Artists in Nagasaki, Japan ~ about 1878 ~ Lacquer, mother of pearl, glass, and copper ~ 2013.59.1A-D ~ Given in memory of Katherine Tiffany Abbott ~ n/a ~ n/a
Child's jacket ~ Artists on the Coromandel Coast, India ~ 1700s ~ Cotton, linen, and silk, assembled in the Netherlands ~ 2012.22.35 ~ Museum purchase, the Veldman-Eecen Collection ~ n/a ~ n/a
""",

"chinese-art": """
Empress Xiaoxian ~ Ignatius Sichelbarth (Ai Qimeng, 1708-1780, Bohemia), Yi Lantai (active about 1748-86, China), and possibly Wang Ruxue (active 18th century, China) ~ 1777 ~ Hanging scroll; ink and color on silk ~ E33619 ~ Gift of Elizabeth Sturgis Hinds, 1956 ~ n/a ~ n/a
Pair of tribute bearers ~ Artists in Beijing, China ~ late 18th century ~ Wood, ivory, mother of pearl, and cloisonne ~ E301906.1-2 ~ Museum purchase, made possible by an anonymous donor, 2001 ~ n/a ~ n/a
Desk and dressing table on stand ~ Artists in Guangzhou, China ~ mid-18th century ~ Ivory, zitan (red sandalwood), and metal ~ E74137 ~ Museum purchase, made possible by an anonymous donor, 1985 ~ n/a ~ n/a
Second-degree Daoist priest's robe ~ Artists in China ~ 18th century ~ Silk, embroidered silk, and gold-wrapped thread ~ E302178 ~ Museum purchase, made possible by an anonymous donor, 2003 ~ n/a ~ n/a
Six-panel wall hanging ~ Imperial Silk Manufactory, Suzhou, China ~ 1736-1795 ~ Embroidered and appliqued silk ~ E21773.A-F ~ Gift of the estate of William F. Spinney, 1933 ~ n/a ~ n/a
Headdress ~ Artists in China ~ about 1800 ~ Kingfisher feathers, imitation pearls, coral, semiprecious stones, copper alloy with gilding, and silk threads ~ E75225.A ~ Gift in honor of Mr. and Mrs. Austin Cheney by their daughters, 1991 ~ n/a ~ n/a
Augustus the Strong's covered vase ~ Artists in Jingdezhen, China ~ 1710-15 ~ Porcelain ~ AE85782.AB ~ Museum purchase, made possible by an anonymous donor, 2001 ~ n/a ~ On view in the Sean M. Healey Family Gallery of Asian Export Art
Jesus, Mary, and Joseph ~ Lu Hongnian (John Lu, 1914-1989, China) ~ early to mid-20th century ~ Ink and color on paper ~ E302067 ~ Museum purchase, made possible by the Asian Art Visiting Committee, 2003 ~ n/a ~ n/a
Stool ~ Shi Jianmin (born 1962, China) ~ 2006 ~ Stainless steel ~ E303674 ~ Gift of the artist, 2008 ~ n/a ~ On view on the Ground Level of the New Wing stairwell
Snuff bottle ~ Imperial Studios, Beijing ~ 1750-95 ~ Enamel on copper with ivory stand ~ E82696.A-C ~ Museum purchase, made possible by an anonymous donor, 1988 ~ n/a ~ n/a
Lidded ritual grain container with lozenges and scrolls ~ Artists in China ~ 6th-5th century B.C.E. ~ Cast bronze ~ E46998 ~ Gift of Francis Lee Higginson Jr., 1971 ~ n/a ~ On view in Double Happiness: Celebration in Chinese Art
Bed cover ~ Junxiu (life dates unknown, China) ~ mid to late 20th century ~ Hand-pieced and quilted fabric scraps ~ E303846 ~ Museum purchase, 2008 ~ n/a ~ n/a
""",

"contemporary-art": """
Immanence ~ Yoan Capote ~ 2015 ~ Door hinges, wood doors, and metal armature ~ 2017.36.1 ~ Museum purchase ~ n/a ~ n/a
Mr. and Mrs. Paul Mellon Staircase and Galleries ~ Michael Lin ~ 2011-12 ~ Acrylic paint ~ 2016.76.1-3 ~ Commission, 2012. Museum purchase, by exchange ~ n/a ~ On view in the stairway of the new wing
Pretty Pretty 10 ~ Gio Swaby ~ 2021 ~ Thread, machine-stitched on reverse of canvas with fabric applique ~ 2022.26.1 ~ Museum purchase, by exchange ~ n/a ~ n/a
Alchemy of the Soul, Elixir of the Spirits ~ Maria Magdalena Campos-Pons ~ 2015 ~ Blown glass, cast glass, steel, cast resin, silicone, acrylic, polyvinyl chloride tubing, and water and rum essence, with multichannel sound installation ~ 2015.46.3 ~ Commission, 2015. Museum purchase ~ n/a ~ On view in the American Art Gallery
Figurehead 2.0 ~ Charles Sandison ~ 2019 ~ Computer-generated data projection ~ 2011.23.1 ~ Commissioned by the Peabody Essex Museum in 2010 and reiterated in 2019 ~ n/a ~ n/a
""",

"european-art": """
Prayer bead with the God in Glory and the Last Judgment ~ Adam Dirckz (around 1500, Netherlands) and workshop ~ 1500-1530 ~ Carved boxwood ~ M557.A ~ Gift of Elias Hasket Derby Jr., 1806 ~ n/a ~ n/a
Armor, helmet and cuirass, used for the gioco del ponte (contest on the bridge) in Pisa ~ Artists in Italy ~ before 1807 ~ Painted iron ~ E304084.1-2 ~ Gift of Captain Samuel Dudley Tucker, 1807 ~ n/a ~ n/a
Chandelier for East India Marine Hall ~ Artists in England ~ mid-1700s ~ Cut glass ~ M81 ~ Gift of Captain Benjamin Carpenter, 1804 ~ n/a ~ On view in East India Marine Hall
Pair of vases, USS Demologos and USS Constitution vs. HMS Guerriere ~ Pierre Louis Dagoty (1771-1840, France) ~ about 1817 ~ Porcelain and marble ~ M27413.1-2 ~ Museum purchase, made possible by an anonymous donor, 1998 ~ n/a ~ On view in the Byrne Family Gallery of Maritime Art
Launching of an Armed Merchantman in Calcutta Harbor ~ Frans Balthazar Solvyns (1760-1824, Belgium) ~ 1791-96 ~ Oil on panel ~ M26444 ~ Museum purchase, made possible by an anonymous donor, 1994 ~ n/a ~ On view in the Sean M. Healey Family Gallery of Asian Export Art
Dr. Thomas Richardson Colledge and His Assistant Afun in Their Ophthalmic Hospital, Macau ~ George Chinnery (1774-1852, United Kingdom) ~ 1833 ~ Oil on canvas ~ M23017 ~ Gift of Cecilia Colledge, 2003 ~ n/a ~ On view in the Sean M. Healey Family Gallery of Asian Export Art
Homeland, Blue and White ~ Bouke de Vries (b. 1960, The Netherlands) ~ 2015 ~ 17th-century Chinese and Japanese porcelain and Dutch delftware fragments ~ 2016.2.1A-F ~ Museum purchase ~ n/a ~ n/a
Stamp Act Repeal'd teapot ~ Cockhill Pit Factory ~ 1766 ~ Glazed earthenware ~ 121493.AB ~ Gift of Professor Richard C. Manning, 1933 ~ n/a ~ On view in On this Ground: Being and Belonging in America
Two English Boys in Asian Clothing ~ Tilly Kettle (1734-1786, United Kingdom) ~ about 1780 ~ Oil on canvas ~ 2011.40.1 ~ Museum purchase, made possible by an anonymous donor ~ n/a ~ On view in the Sean M. Healey Family Gallery of Asian Export Art
Potpourri vase ~ Artists in Paris ~ about 1740 ~ Chinese, Japanese, and French porcelain and French gilded bronze ~ E84084.AB ~ Museum purchase, made possible by an anonymous donor, 1994 ~ n/a ~ On view in the Sean M. Healey Gallery of Asian Export Art
Side chair from the grand salon on the ocean liner Normandie ~ Jean-Maurice Rothschild (1902-1998, France), Baptistin Spade (1891-1969, France), Emile Gaudissart (1872-1956, France), and Aubusson Manufacturers ~ 1934 ~ Gilded wood, metal, and wool and silk tapestry ~ 2015.10.1 ~ Museum purchase ~ n/a ~ n/a
""",

"fashion-textiles": """
Cape ~ Unangax (Aleut) artist, name once known ~ about 1820 ~ Mammal intestine, esophagus, hair, and dye ~ E3662.A ~ Gift of Thomas Meek, before 1821 ~ Unangax (Aleut) ~ n/a
Dress ~ Jeanne Adele Bernard Sacerdote (1868-1962, France) for Jenny, Paris ~ 1927 ~ Glass, silk, lame, metal ~ 132306 ~ Gift of Mrs. Edward Gates, 1970 ~ n/a ~ n/a
Evening tuxedo jumpsuit ~ Geoffrey Beene (1927-2004, United States) ~ late 1990s-early 2000s ~ Wool and silk crepe ~ 2013.61.37 ~ Gift of Iris Barrel Apfel, in memory of Syd and Sam Barrel ~ n/a ~ n/a
Kiss Me Dolores ~ Charlotte Olympia, United Kingdom ~ 2010s ~ Rhinestones, leather and silk satin ~ 2018.34.8AB ~ Gift of Susan Esco Chandler ~ n/a ~ ON VIEW
Wedding dress ~ Artist in Salem, United States ~ 1872 ~ Silk and cotton ~ 129156.1A-D ~ Gift of Annie L. Cutts, 1958 ~ n/a ~ n/a
Salem Light Infantry uniform ~ Artists in the United States ~ about 1812 ~ Broadcloth with gilt braid, buckskin, and wool felt ~ 100044, 100045, and 100046 ~ Gift of Mrs. John C. Dow, 1902 ~ n/a ~ n/a
Banyan (dressing gown) ~ Artists in the United Kingdom and the United States ~ mid-1700s ~ Silk damask and linen ~ 133574 ~ Gift of the heirs of Andrew Nichols, 1975 ~ n/a ~ n/a
Dress ~ Claire McCardell, for Townley Frocks Inc. ~ 1940s ~ n/a ~ 2018.29.3 ~ The Albert Szabo and Brenda Dyer Szabo Collection ~ n/a ~ n/a
Ensemble, from the collection Fashion as Resistance ~ Carla Fernandez (Mexican, b. 1973) ~ Fall/Winter 2018 ~ Rayon, acrylic paint ~ 2020.7.1AB ~ Museum purchase, made possible by the Willoughby Stuart Memorial Fund ~ n/a ~ n/a
Corset ~ Les Grands Magasins du Louvre, Paris ~ 1893-95 ~ Satin brocade, lace, metal, and ribbon ~ 116364 ~ Anonymous gift, 1922 ~ n/a ~ n/a
Palampore (bed cover) ~ Artists in India ~ 1710-50 ~ Cotton embroidered with silk and metal ~ 2012.22.82 ~ Museum purchase, the Veldman-Eecen Collection ~ n/a ~ n/a
Applique Rising-Sun Quilt ~ Artist in Massachusetts ~ about 1845 ~ Cotton ~ 131932 ~ Gift of Miss Bessom S. Harris, 1969 ~ n/a ~ n/a
Bracelet ~ Cody Sanderson (Dine (Navajo) and Hopi, b. 1964) ~ early 21st century ~ Silver ~ 2014.21.2 ~ Gift of Charles Franklin Sayre ~ n/a ~ n/a
""",

"japanese-art": """
Pumpkin (Akoda) ~ Katsumata Chieko (b. 1950, Japan) ~ 2008 ~ Stoneware with matte glazes ~ 2015.42.5 ~ Gift of Carol and Jeffrey Horvitz ~ n/a ~ n/a
Helmet (kabuto) with design of a dragonfly ~ Terada Tadatoyo ~ late 18th to early 19th century ~ Lacquer and shell inlay ~ E7559 ~ Gift of Dr. Charles Goddard Weld, 1904 ~ n/a ~ Japanese Art Gallery
The Bodhisattva Jizo ~ Artists in Japan ~ 1279 ~ Lacquered wood, gold leaf, pigments, copper alloy, and crystal ~ E12068.1AB-.4AB ~ Gift of Dr. Charles Goddard Weld, 1909 ~ n/a ~ Powerful Figures
Shop sign (kanban) advertising medicine for stomach pain ~ Artists in Japan ~ 19th century ~ Wood, lacquer, pigments, gold, and metal ~ E15898 ~ Museum purchase, made possible by the R. C. Billings Fund, 1914 ~ n/a ~ n/a
Surcoat (jinbaori) ~ Artists in Japan ~ 18th century ~ Dutch gilt leather and wool, European-printed cotton lining, and silk trim ~ E303608 ~ Museum purchase, made possible by an anonymous donor, 2007 ~ n/a ~ Sean M. Healey Family Gallery of Asian Export Art
Noblewoman's palanquin (onna norimono) ~ Artists in Japan ~ 19th century ~ Wood, lacquer, gilded brass, silk, paper, pigments, gold leaf, and bamboo ~ E37812 ~ Museum collection ~ n/a ~ Japanese Art Gallery
Rabbit netsuke ~ Naito Toyomasa (1773-1856, Japan) ~ late 18th-early 19th century ~ Ivory ~ E26721 ~ Gift of Ernest Goodrich Stillman, 1947 ~ n/a ~ Japanese Art Gallery
Six-panel screen depicting the arrival of a Portuguese ship for trade (nanban byobu) ~ Artists in Japan ~ early 17th century ~ Ink, color and gold leaf on paper ~ E200727 ~ Museum purchase, made possible by an anonymous donor, 1994 ~ n/a ~ n/a
Doll of a woman and child (iki ningyo) ~ Artists in Japan ~ 1883 ~ Gesso over paper, wood, and vegetable fiber ~ E16310.B ~ Commissioned by Edward Sylvester Morse for PEM, 1883 ~ n/a ~ n/a
Kabuki robe (uchikake) with design of tortoise, crane, and pines ~ Artists in Japan ~ 1850-68 ~ Wool, silk, cotton, gold-wrapped thread, and metals ~ E17983 ~ Gift of Dr. William Sturgis Bigelow, 1921 ~ n/a ~ n/a
Teacup and saucer ~ Artists in Japan ~ about 1801 ~ Stoneware and lacquered wood ~ E30279 and E30280 ~ Gift of Captain Samuel G. Derby, 1803 ~ n/a ~ n/a
Brazier in the form of a rabbit ~ Artists in Japan ~ 18th or 19th century ~ Stoneware ~ E5798 ~ Gift of Edward Sylvester Morse, 1900 ~ n/a ~ Salem Stories
Portrait of Edward Sylvester Morse ~ Frank Weston Benson (American, 1862-1951) ~ 1913 ~ Oil on canvas ~ M4311 ~ Gift of Edith Owen Robb, 1914 ~ n/a ~ Salem Stories
Dejima, the Dutch Trading Station at Nagasaki handscroll ~ Artists in Nagasaki, Japan ~ about 1800 ~ Paint and ink on silk ~ E300414.B ~ Museum purchase, made possible by an anonymous donor, 1999 ~ n/a ~ n/a
""",

"korean-art": """
Portrait of Yu Giljun ~ A. B. Cross Photography Studio, Salem, Massachusetts ~ 19th century ~ Photographic print ~ E2, box 88 3 Japan, ETH000031 ~ n/a ~ n/a ~ On view in Salem Stories
Fan (taegeukseon) ~ Artist in Korea ~ 19th century ~ Paper, lacquer, and wood ~ E9812 ~ Gift of Dr. Charles Goddard Weld, 1899 ~ n/a ~ On view in Salem Stories
Hwarot (bridal robe) ~ Artists in Korea ~ late 18th century ~ Silk, paper, cotton, wool, and metallic thread ~ E20190.F ~ Museum purchase from Yamanaka and Company, 1927 ~ n/a ~ n/a
Village guardian posts (jangseung) ~ Artists in Korea ~ late 19th century ~ Wood, pigment ~ E20809, E20810 ~ Gift of Yamanaka and Company, in memory of Professor Edward S. Morse, 1930 ~ n/a ~ On view in the Garden Atrium
Nectar Ritual (gamnotaeng) hanging scroll ~ Artists in Korea ~ 1744 ~ Ink and pigment on silk ~ E302324 ~ Museum purchase, made possible by an anonymous donor, 2004 ~ n/a ~ n/a
Hat (gat) ~ Artist in Korea ~ before 1883 ~ Hair, lacquer, and bamboo ~ E1573 ~ Gift of Yu Giljun, 1883 ~ n/a ~ On view in Salem Stories
Noblewoman's bridal fan (jinjuseon) ~ Artist in Korea ~ 18th century ~ Embroidered silk and metal fittings ~ E20165 ~ Museum purchase, 1927 ~ n/a ~ n/a
Screen ~ Korean artist ~ late 18th century ~ n/a ~ 134187 ~ Gift of Mr. and Mrs. Thomas P. Beal ~ n/a ~ n/a
Wrapping cloth (bojagi) ~ Artist in Korea ~ 20th century ~ Ramie ~ E301728 ~ Museum purchase, made possible by the Toplitz Hilborn Memorial Fund, 2001 ~ n/a ~ n/a
Rank badge with two cranes and clouds for a civil official ~ Artist in Korea ~ 19th century ~ Embroidered silk threads on silk damask ~ E9785 ~ Gift of Gustavus Goward, 1899 ~ n/a ~ n/a
Free reed wind instrument (saenghwang) ~ Artist in Korea ~ 19th century ~ Bamboo, rattan, wood, and bone ~ E9796 ~ Museum purchase from the World's Columbian Exhibition, Chicago, 1893 ~ n/a ~ On view in Salem Stories
Dragon jar ~ Artists in Korea ~ late 19th century ~ Porcelain ~ E302330 ~ Gift of Kang Collection, Korean Art, New York, 2004 ~ n/a ~ n/a
Ten-panel screen (Banquet of Guo Ziyi) ~ Artist in Korea ~ late 19th-early 20th century ~ Silk, paint and ink ~ 2023.29.1 ~ Gift of Cynthia M. Nadai, in memory and honor of Edwin Morgan ~ n/a ~ n/a
Lute (biwa) ~ Artist in Korea ~ 19th century ~ Wood, composite, and cotton ~ E9801 ~ Museum purchase from the World's Columbian Exhibition, Chicago, 1893 ~ n/a ~ n/a
Soban (small individual table) ~ Artist in Korea ~ late 1800s ~ Wood, lacquer, and mother-of-pearl ~ E1459 ~ Museum purchase, 1884 ~ n/a ~ n/a
Bowler hat ~ Artist in Korea ~ around 1883 ~ Horsehair, bamboo, and paper ~ E50273 ~ Gift of Mrs. R. Keith Kane, 1974 ~ n/a ~ n/a
Sword and sheath ~ Artist in Korea ~ before 1899 ~ Wood, lacquer, iron, and silk ~ E9739 ~ Gift of Dr. Charles Goddard Weld, 1889 ~ n/a ~ n/a
Cotton armor with talismans ~ Artist in Korea ~ 1800s ~ Cotton, hemp, copper alloy, and iron ~ E18987 ~ Gift of the United States Naval Academy, 1923 ~ n/a ~ n/a
Inkwell inscribed, Madam Pauling, Joseon Ministry of Internal Affairs ~ Artist in Korea ~ about 1895-97 ~ Silver and brass ~ E76054.AB ~ Museum purchase, 1986 ~ n/a ~ n/a
Box ~ Artist in Korea ~ 1500s-1600s ~ Wood, lacquer, and mother-of-pearl ~ E300228.A-D ~ Museum purchase, made possible by an anonymous donor, 1998 ~ n/a ~ n/a
""",

"maritime-art-and-history": """
Two-headed equestrian figurehead ~ Artist in the United Kingdom ~ about 1750 ~ White pine ~ 2018.12.1 ~ Museum purchase, made possible by Ulf B. and Elizabeth C. Heide ~ n/a ~ ON VIEW
Ship Southern Cross in Boston Harbor ~ Fitz Henry Lane (1804-1865, United States) ~ 1851 ~ Oil on canvas ~ M18639 ~ Gift of the estate of Stephen Wheatland, 1987 ~ n/a ~ ON VIEW
Royal presentation octant dedicated to King Louis XVI ~ Jean Baptiste Magnie (mid-18th century, France) ~ about 1786 ~ Brass, mahogany, and glass ~ M10975 ~ Gift of Strafford Morss, 1966 ~ n/a ~ ON VIEW
Model of the ship Queen Elizabeth ~ Bassett-Lowke Ltd (Northampton, United Kingdom) ~ 1947-48 ~ White mahogany, gunmetal and brass ~ M14220 ~ Gift of Cunard Line Ltd., 1970 ~ n/a ~ ON VIEW
They Took Their Wives with Them on Their Cruises ~ N. C. Wyeth (1882-1945, United States) ~ about 1938 ~ Oil on board ~ M27834 ~ Museum purchase, made possible by Nancy and George Putnam, 2007 ~ n/a ~ ON VIEW
Scrimshaw of the ship Susan ~ Frederick Myrick (1808-1862, United States) ~ 1829 ~ Whale tooth ~ M13 ~ Gift of George Peirce, 1830 ~ n/a ~ ON VIEW
Model of the ship Friendship ~ Thomas Russell and Mr. Odell (active 19th century, United States) ~ about 1804 ~ Wood, cordage and bronze ~ M48 ~ Gift of Captain William Story, about 1804 ~ n/a ~ ON VIEW
Captain Cook Cast a Way on Cape Cod ~ Michele Felice Corne (1752-1845, Italian, American) ~ 1802 ~ Gouache on paper ~ M5923 ~ Gift of Augustus Peabody Loring Jr., 1946 ~ n/a ~ n/a
Ship Alfred of Salem Cap Joseph Felt ~ Nicolas Cammillieri (1773-1860, France) ~ 1806 ~ Watercolor on paper ~ M8900 ~ Gift of Marion H. Lieb, Elizabeth M. Ringquist, and Grace F. Agge, 1956 ~ n/a ~ n/a
Figurehead ~ Attributed to William Rush (1756-1833, United States) ~ about 1805 ~ Pine and paint ~ M27741 ~ Museum purchase, made possible by the Maritime Visiting Committee ~ n/a ~ ON VIEW
Icebound Ship ~ William Bradford (1823-1892, United States) ~ about 1880 ~ Oil on canvas ~ M27190 ~ Museum purchase with funds donated anonymously, 1996 ~ n/a ~ n/a
Portrait of Nathaniel Bowditch ~ Charles Osgood (1809-1890, United States) ~ 1835 ~ Oil on canvas ~ M370 ~ Commissioned by the East India Marine Society, 1835 ~ n/a ~ ON VIEW
Launching of the Ship Fame ~ George Ropes (1788-1819, United States) ~ 1802 ~ Oil on canvas ~ 108332 ~ Gift of Nathaniel Silsbee, 1862 ~ n/a ~ n/a
The Stranding of Corvettes in the Mauvais Canal, Strait of Torres ~ Louis Le Breton (1818-1886, France) ~ 1843 ~ Oil on canvas ~ M10920 ~ Museum purchase, made possible by the Fellows and Friends Fund, 1961 ~ n/a ~ ON VIEW
""",

"native-american-art": """
Sculpture ~ Likely Pawtucket band of Massachusett artist, name once known ~ 1500s ~ Basalt ~ E50296 ~ Gift of Miss Bessie Eaton, 1898 ~ Massachusett ~ On This Ground: Being and Belonging in America
Basket ~ Chumash artist, name once known ~ about 1825 ~ Juncus rush and dye ~ E28771 ~ Gift of Alvin P. Johnson, 1950 ~ Chumash ~ On This Ground: Being and Belonging in America
Bibi k'inpi (cradleboard) ~ Dakota artist, name once known ~ about 1840 ~ Porcupine quill, metal, glass beads, leather, and wood ~ E27984 ~ Museum purchase, made possible by an anonymous donor, 2002 ~ Dakota ~ On This Ground: Being and Belonging in America
Drum ~ Yup'ik artist, name once known ~ late 1800s ~ Wood, bladder, and paint ~ E13084 ~ Gift of Israel Albert Lee, 1910 ~ Yup'ik ~ On This Ground: Being and Belonging in America
Sash ~ Chahta (Choctaw) artist, name once known ~ mid-1800s ~ Wool, silk, and glass beads ~ E25963 ~ Gift of Dr. Charles Heald, 1955 ~ Chahta (Choctaw) ~ On This Ground: Being and Belonging in America
Doll ~ Lakota (Teton/Western Sioux) artist ~ late 1800s ~ Leather, velvet, glass, cotton, metal, and ink ~ E8157 ~ Gift of Dr. Charles Goddard Weld, 1905 ~ Lakota (Teton/Western Sioux) ~ On This Ground: Being and Belonging in America
Mask ~ Heiltsuk or Coast Tsimshian artist, name once known ~ 1840-60 ~ Wood and paint ~ E28573 ~ Gift of Edward S. Moseley, 1979 ~ Heiltsuk or Coast Tsimshian ~ On This Ground: Being and Belonging in America
Pipe ~ Haida artist, name once known ~ about 1825 ~ Argillite ~ E3496 ~ Gift of Captain John Bradshaw, 1832 ~ Haida ~ On This Ground: Being and Belonging in America
David Weeden (Mashpee Wampanoag), from the ongoing Critical Indigenous Photographic Exchange series ~ Will Wilson (Dine, Navajo, b. 1969) ~ 2019 ~ Archival pigment print from wet plate collodion scan, printed 2021 ~ 2021.26 ~ Museum purchase, made possible by the Ellen and Stephen Hoffman Fund for Native American Art Acquisitions ~ Dine, Navajo ~ On This Ground: Being and Belonging in America
The Seine of Journeys ~ Truman Lowe (Ho-Chunk, 1944-2019) ~ 2003 ~ Willow, monofilament, and metal ~ E302691 ~ Museum commission, 2005 ~ Ho-Chunk ~ On This Ground: Being and Belonging in America
Hovenweep #331 ~ Kay WalkingStick (Cherokee Nation, b. 1935) ~ 1987 ~ Acrylic, oil, and saponified wax on canvas ~ 2011.29.72.1-2 ~ Gift of Katrina M. Carye ~ Cherokee Nation ~ On This Ground: Being and Belonging in America
Hanodaga:yas (Town Destroyer) ~ Alan Michelson (Mohawk member of the Six Nations of the Grand River, b. 1953) ~ 2018 ~ High-definition video, bonded stone replica of Jean-Antoine Houdon's late 1700s bust of George Washington, antique surveyor's tripod, and artificial turf ~ 2019.38.1AB ~ Museum purchase, by exchange ~ Mohawk, Six Nations of the Grand River ~ On This Ground: Being and Belonging in America
Indian with Beaded Headdress ~ T.C. Cannon (Kiowa and Caddo, 1946-1978) ~ 1978 ~ Oil on canvas ~ 2015.35.1 ~ Museum purchase ~ Kiowa and Caddo ~ On This Ground: Being and Belonging in America
Boots ~ Jamie Okuma (Luiseno and Shoshone-Bannock, born 1977) ~ 2014 ~ Glass beads on boots designed by Christian Louboutin ~ 2014.44.1AB ~ Museum commission ~ Luiseno and Shoshone-Bannock ~ On This Ground: Being and Belonging in America
Tsu Heidei Shugaxtutaan (We Will Again Open This Container of Wisdom That Has Been Left in Our Care), Parts I and II ~ Nicholas Galanin, Yeil Ya-Tseen (Tlingit and Unangax, b. 1979) ~ 2006 ~ Digital video, looped, edition 2/5 ~ 2012.25.1 ~ Museum purchase, made possible by the Willoughby Stuart Memorial Fund and the Native American Artist Fund ~ Tlingit and Unangax ~ On This Ground: Being and Belonging in America
Companion Species: Cosmos, Sunrise, Flint ~ Marie Watt (Seneca, born 1967) ~ 2019-21 ~ Reclaimed wool blankets and embroidery thread ~ 2021.4.1 ~ Museum purchase by exchange ~ Seneca ~ On This Ground: Being and Belonging in America
""",

"natural-history": """
King penguin (Aptenodytes patagonicus) ~ n/a ~ about 1820 ~ n/a ~ EIMS1219.1 ~ Gift of Captain George Hodges, 1821 ~ n/a ~ Salem Stories
Red Malay rooster (Gallus gallus domesticus) ~ n/a ~ about 1846 ~ n/a ~ NB852 ~ Gift of George Wheatland, 1846 ~ n/a ~ n/a
Leatherback turtle (Dermochelys coriacea) ~ n/a ~ 1885 ~ n/a ~ FIC2021.929.1 ~ Gift of Mr. Parsons, 1885 ~ n/a ~ Salem Stories
American bison, bull ~ n/a ~ 1886 ~ n/a ~ NM294 ~ Gift of William Crowninshield Endicott, 1887 ~ n/a ~ n/a
Zoological illustration of a newly discovered species of toad ~ Augustus Fowler ~ 1858 ~ Watercolor on paper ~ NH130 ~ after 1858 ~ n/a ~ n/a
Marginal wood fern (Dryopteris marginalis) ~ John Robinson ~ 1865 ~ n/a ~ NHH1.410 ~ Gift of John Robinson, after 1865 ~ n/a ~ n/a
Insect teaching chart for the Peabody Academy of Science's Summer School of Biology, Salem ~ James Henry Emerton ~ about 1876 ~ Paint on canvas ~ NH310 ~ Gift of Dr. Ralph W. Dexter, 1981 ~ n/a ~ n/a
Pintail decoy ~ Joseph W. Lincoln ~ about 1920 ~ Wood, paint, metal, and glass ~ NHDP1 ~ Museum purchase, made possible by the Special Fund for Natural History, 1992 ~ n/a ~ The Pod
Decorative carving of a semipalmated sandpiper ~ A. Elmer Crowell ~ about 1915 ~ Wood, paint, glass, oyster shell, and metal ~ NHDSB24 ~ Gift of Arthur C. Phillips, 1978 ~ n/a ~ The Pod
Ostrich (Struthio camelus) egg ~ n/a ~ before 1800 ~ n/a ~ EIMS502 ~ Gift of Captain Benjamin Carpenter, 1800-1802 ~ n/a ~ Salem Stories
Coco de mer (Lodoicea maldivica) nut ~ n/a ~ about 1800 ~ n/a ~ EIMS482 ~ Probably gift of Captain Samuel Lambert, 1800-1802 ~ n/a ~ Salem Stories
""",

"oceanic-art": """
Tapa ~ Artist not identified ~ early-mid 19th century ~ Tapa (processed inner tree bark), pigments ~ E3172 ~ Received before 1867 ~ Austral Islands ~ n/a
Bure kalou (spirit house) ~ Fijian artist ~ early 19th century ~ Coconut fiber, wood, shell ~ E5037 ~ Gift of Joseph Winn Jr., 1835 ~ Fiji ~ n/a
Fan ~ Marquesan artist ~ n/a ~ Wood, pandanus, coconut fiber ~ E5351 ~ Gift of Clifford Crowninshield and Matthew Folger, 1802 ~ Marquesas Islands ~ n/a
Kava - We, the two of us ~ Bernice Akimine (Native Hawaiian, b. 1949) ~ 2000 ~ Glass, glass powder, dye, and sand ~ E301984.AB ~ Museum purchase, made possible by the Piilani Cook Whittier Fund, 2002 ~ Native Hawaiian ~ n/a
Ku ~ Kanaka Maoli (Native Hawaiian) artist ~ early 19th century ~ 'Ulu (breadfruit) wood ~ E12071 ~ Gift of John T. Prince, 1846 ~ Native Hawaiian ~ ON VIEW
Kupe'e hoaka (boar tusk bracelet) ~ Kanaka Maoli (Native Hawaiian) artist ~ late 18th century ~ Wild boar tusks and fiber ~ E5299 ~ Gift of Nathaniel Silsbee, 1800 ~ Native Hawaiian ~ ON VIEW
Headdress ~ Marquesan artist ~ n/a ~ Sennit, feather ~ E17750 ~ Gift of Stephen W. Phillips, 1919 ~ Marquesas Islands ~ n/a
Peue ei (women's head ornament) ~ Marquesan artist ~ mid-19th century ~ Coconut fiber, porpoise teeth, beads ~ E35650 ~ Gift of F. Walter Bergmann, 1958 ~ Marquesas Islands ~ n/a
Pipe ~ Patoromu Tamatea (19th century) ~ 1880s-1890s ~ Wood, paua shell ~ E23544 ~ Museum purchase, 1939 ~ Maori ~ n/a
""",

"phillips-library-collection": """
Account of Lafayette Dinner, August 30, 1824 ~ John Remond (about 1788-1874) ~ August 30, 1824 ~ Ink on paper ~ MSS 271, box 2, folder 3 ~ Gift of Miss Cecilia R. Babcock, June 22, 1915 ~ n/a ~ n/a
Map of Nagasaki, Hizen Province, Japan (Hizen Nagasaki zu) ~ Kumamoto Ensai ~ 1696 ~ Ink and color on paper ~ G7964.N26 E573 ~ Gift of Mr. Philip Hofer and Mr. Francis B. Lothrop, 1972 ~ n/a ~ n/a
Shina Pekinjo Kenchiku (plate 18) ~ Ito Chuta ~ 1925 ~ n/a ~ NA1547.P3 I89 1925 + ~ Gift of Scott Offen, Herbert Offen Research Collection, 2004 ~ n/a ~ n/a
Scrapbook containing ancestor portraits of Chinese men and women ~ Artist in China ~ about 1880-1911 ~ Watercolor and ink on paper ~ 750 S433 ++ ~ Gift of Thomas Franklin Hunt, before 1898; or purchase, Ward Memorial Fund, after 1900 ~ n/a ~ n/a
Cleopatra's Barge (Yacht) journal ~ George Crowninshield Jr. ~ 1817 ~ Ink, watercolor, and pencil on paper ~ MSS 15, Box 21 ~ Purchase, Elizabeth Rogers Fund, 2022 ~ n/a ~ n/a
The New Testament of our Lord and Saviour Jesus Christ ~ n/a ~ 1862 ~ Book with leather cover and encased bullet ~ Fam. Mss. 611, box 1 ~ n/a ~ n/a ~ n/a
Study for the front elevation of Derby Mansion ~ Samuel McIntire ~ 1795-98 ~ Pen and ink on paper ~ MSS 264, box 3, folder 3 #21 ~ Gift of Richard H. Derby, before 1900 ~ n/a ~ n/a
Illustrated note ~ Sayed Haider (S.H.) Raza ~ 1984 ~ Ink on paper ~ MSS 871, box 6, folder 3, item 24 ~ Gift of Chester and Davida Herwitz, 2002 ~ n/a ~ n/a
Commonplace book ~ Henry Tiffin ~ 1748-76 ~ Book; watercolor and ink on paper ~ MSS 322 ~ Gift of Mrs. Anna Glen Butler Vietor, 1982 ~ n/a ~ n/a
America: A Hymnal ~ Bethany Collins ~ 2017 ~ Book with 100 laser-cut leaves ~ N7433.4 .C639 A58 2017 + ~ Purchase, 2018 ~ n/a ~ ON VIEW
Designs for fur coats ~ Frank G. Speck ~ 1927 ~ Ink on paper ~ E44, box 1, folder 13 ~ Gift of Dr. Frank G. Speck ~ n/a ~ n/a
Massachusetts Colony five-shilling note ~ Massachusetts General Court ~ 1690 ~ Ink on paper ~ MSS 831 ~ n/a ~ n/a ~ n/a
Petition of Mary Esty, September 15, 1692 ~ n/a ~ September 15, 1692 ~ Ink on paper ~ n/a ~ n/a ~ n/a ~ n/a
""",

"photography": """
Pont Neuf, Paris ~ Attributed to Vincent Chevalier (1771-1841, France) ~ about 1839 ~ Daguerreotype, half plate ~ 1231 ~ Gift of John Burley, 1858 ~ n/a ~ n/a
A Royal Family ~ Lala Deen Dayal (1844-1905, India) ~ late 19th century ~ Gelatin silver print ~ PH81.110 ~ Museum purchase, made possible by an anonymous donor, 2000 ~ n/a ~ n/a
Khamba Jong, Tibet, from the album Tibet and Lhasa ~ John Claude White (1853-1918, United Kingdom) ~ 1907-08 ~ Carbon print ~ PH80.6 ~ Anonymous donor, 2000 ~ n/a ~ n/a
Portrait of a Woman (Possibly Empress Myeongseong) ~ Artist in Korea ~ 1887-1892 ~ Albumen print ~ PH78.33 ~ Museum purchase, made possible by John O. and Olivia Hood Parker, 2001 ~ n/a ~ n/a
Portrait of William Lloyd Garrison, George Thompson, and Wendell Phillips ~ Albert Sands Southworth (1811-1894, United States) and Josiah Johnson Hawes (1808-1901, United States) ~ about 1850 ~ Daguerreotype, whole plate ~ 112333.DUP ~ Museum purchase, 1921 ~ n/a ~ n/a
Whalers Rousseau and Desdemona ~ Edwin Hale Lincoln (1848-1938, United States) ~ 1889 ~ Platinum print ~ PH285.351 ~ Museum purchase, 1972 ~ n/a ~ n/a
Cinquefoil, from the Ephemera portfolio ~ Olivia Parker (b. 1941, United States) ~ 1975, printed 1977 ~ Gelatin silver print ~ 2014.28.11.2 ~ Gift of the artist ~ n/a ~ n/a
The Island Pagoda, from the album Foochow and the River Min ~ John Thomson (1837-1921, Scotland) ~ 1873 ~ Carbon print ~ PH26.19 ~ Gift of the Estate of Mrs. Anthony Rives, 1973 ~ n/a ~ n/a
Japanese Woman at Her Toilette ~ Kusakabe Kimbei (1841-1934, Japan) ~ about 1880 ~ Albumen print with hand coloring ~ FIC2016.10.1 ~ Edward Sylvester Morse Collection ~ n/a ~ n/a
Treasury Street, Canton ~ Felice Beato (1832-1909, United Kingdom, born in Italy) ~ 1860 ~ Albumen print ~ PH2.83 ~ Gift of Howard Corning, Albert Farley Heard Collection, before 1956 ~ n/a ~ n/a
Scrimshaw Carver ~ Artist in the United States ~ about 1890 ~ Cyanotype print ~ 2014.43.1 ~ Museum purchase ~ n/a ~ n/a
View of the Beach, The Mangrove Coast, Florida ~ Walker Evans (1903-1975, United States) ~ 1941 ~ Gelatin silver print ~ PH188 ~ Gift of Joan and Clark Worswick, 1999 ~ n/a ~ On This Ground: Being and Belonging in America
Canyonlands, Utah ~ Michael A. Smith (1942-2018, United States) ~ 1993 ~ Gelatin silver print ~ 2016.70.19 ~ Gift of Garrett Gunderson ~ n/a ~ On This Ground: Being and Belonging in America
Wounded Soldiers Being Tended in the Field after the Battle of Chancellorsville near Fredericksburg, VA ~ Studio of Mathew B. Brady ~ 1863 ~ Albumen print ~ PH104.17 ~ Gift of Mrs. William C. Endicott, in honor of William C. Endicott, 1911 ~ n/a ~ On This Ground: Being and Belonging in America
""",

"south-asian-art": """
Woman '95 ~ G. Ravinder Reddy ~ 1995 ~ Fiberglass and gilding ~ E300456 ~ Gift of the Chester and Davida Herwitz Collection, 1999 ~ n/a ~ ON VIEW
August '81 ~ Biren De ~ 1981 ~ Oil on canvas ~ E301030 ~ Gift of the Chester and Davida Herwitz Collection, 2001 ~ n/a ~ ON VIEW
Man ~ Maqbool Fida (M.F.) Husain ~ 1951 ~ Oil on fiberboard ~ E301146 ~ Gift of the Chester and Davida Herwitz Collection, 2001 ~ n/a ~ ON VIEW
Hanuman Revealing Rama and Sita in his Heart ~ Artists in Kolkata, India ~ 19th century ~ Watercolor and tin on paper ~ E302104 ~ Museum purchase, made possible by an anonymous donor, 2003 ~ n/a ~ n/a
Bindu La Terre ~ Sayed Haider (S.H.) Raza ~ 1983 ~ Oil on canvas ~ E301248 ~ Gift of the Chester and Davida Herwitz Collection, 2003 ~ n/a ~ n/a
Untitled ~ Tyeb Mehta ~ 1973 ~ Acrylic on canvas ~ E301099 ~ Gift of the Chester and Davida Herwitz Collection, 2001 ~ n/a ~ ON VIEW
2nd October ~ Atul Dodiya ~ 1993 ~ Acrylic and oil on canvas ~ E301092 ~ Gift of the Chester and Davida Herwitz Collection, 2001 ~ n/a ~ ON VIEW
Old Arguments on Indigenism ~ Nalini Malani ~ 1989 ~ Acrylic and oil on canvas ~ E301088 ~ Gift of the Chester and Davida Herwitz Collection, 2001 ~ n/a ~ ON VIEW
Protector Goddess ~ Artists in Kerala, India ~ mid-19th century ~ Wood and pigment ~ E18001 ~ Gift of Robert P. Gay, 1921 ~ n/a ~ ON VIEW
Devotee of Krishna ~ Kashinath Pal in Krishnanagar ~ about 1823 ~ Unfired clay, paint, textile ~ E9923 ~ Gift of Captain James Buffington Briggs/Capt. Benjamin Vanderford, 1823 ~ n/a ~ ON VIEW
Two Men with Hand Cart ~ Gieve Patel ~ 1979 ~ Oil on canvas ~ E301289 ~ Gift of the Chester and Davida Herwitz Collection, 2003 ~ n/a ~ ON VIEW
Girl Eating Rasagolla ~ K.G. Subramanyan ~ 1980 ~ Reverse painting on acrylic ~ E301396 ~ Gift of the Chester and Davida Herwitz Collection, 2001 ~ n/a ~ ON VIEW
""",
}

FIELDS = ("title", "artist", "date", "material",
          "accession", "acquisition", "culture", "onview")

# ---------------------------------------------------------------------------
# 已人工核实的 source_seq -> 馆藏号
#
# 这 14 件是 2026-08-30 在会话里逐页比对后确认的，当时直接入了库、没落进仓库
# —— 于是这批「最硬的证据」变成了脚本复现不出来的孤儿数据。固化在这里，
# 是为了让 meta_fill_official_pem.py 重跑能得到同样的结果。
#
# 它同时是**匹配器的非循环校验集**：自动匹配独立跑出来的结果拿这张表去对，
# 2026-08-31 实测自动命中其中 12 件、馆藏号 12/12 一致、0 冲突。
# 剩下 2 件（seq 3 的 Kū、seq 9 的 Jizō）自动匹配够不着 —— 变音符加短词，
# 分词后几乎没有可比对的信息。它们靠本表兜住，而不是靠放宽匹配阈值：
# 放宽阈值换来的是假阳性，meta_scrape.py 的文件头记着上次的教训
# （28 条候选人工核对后只有 1 条是真的）。
# ---------------------------------------------------------------------------
VERIFIED = {
    2: "E200727",           # Nanban Byobu, Portuguese Trade Arrival Screen
    3: "E12071",            # Hawaiian Kū War God Figure
    5: "M22672",            # Fitz Henry Lane, Twilight on the Kennebec
    6: "M12561",            # John Singleton Copley, Portrait of Sarah Erving Waldo
    7: "M27741",            # Rush Figurehead, USS Frigate
    9: "E12068.1AB-.4AB",   # Edo Jizō Bosatsu Wood Sculpture, 1279
    15: "100183",           # Robert Feke, Portrait of Judge Richard Saltonstall
    16: "106746",           # Fidelia Bridges, Pastures by the Sea
    22: "E26721",           # Japanese netsuke rabbit by Naito Toyomasa
    23: "E15898",           # Edo period medicine-shop kanban signboard
    24: "2015.42.5",        # Katsumata Chieko, Pumpkin ceramic sculpture
    26: "2019.23.1ab",      # Hank Willis Thomas, Rich Black Specimen #460
    39: "E37812",           # Edo period noblewoman palanquin (onna norimono)
    40: "E7559",            # 18-century Japanese dragonfly-design kabuto helmet
}


def records() -> list[dict]:
    """解析成 [{section, url, title, artist, ...}]。`n/a` 一律归 None。"""
    out = []
    for section, block in RAW.items():
        for line in block.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            parts = [p.strip() for p in line.split("~")]
            if len(parts) != len(FIELDS):
                raise ValueError(
                    f"{section} 有一行字段数不是 {len(FIELDS)}（得到 {len(parts)}）：{line}")
            rec = {k: (None if v.lower() in ("n/a", "") else v)
                   for k, v in zip(FIELDS, parts)}
            if not rec["title"]:
                raise ValueError(f"{section} 有一行没有标题：{line}")
            rec["section"] = section
            rec["url"] = BASE + section
            out.append(rec)
    return out


# 馆藏号可能形如 "E7100 and E7101" 或 "100044, 100045, and 100046"，
# 一件对象对应多个号。拆开是为了让「按馆藏号核对」能命中其中任意一个。
def accessions(rec: dict) -> list[str]:
    if not rec["accession"]:
        return []
    parts = (p.strip() for p in re.split(r",|\band\b", rec["accession"]))
    return [p for p in parts if p]


if __name__ == "__main__":
    rs = records()
    import collections
    c = collections.Counter(r["section"] for r in rs)
    print(f"共 {len(rs)} 条，来自 {len(c)} 个栏目页：")
    for s, n in sorted(c.items()):
        print(f"  {s:32} {n:3d}")
    print(f"有馆藏号 {sum(1 for r in rs if r['accession'])} 条，"
          f"有捐赠/购藏信息 {sum(1 for r in rs if r['acquisition'])} 条")
