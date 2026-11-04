"""Proposed source-informed inventory revisions; not a released rating input."""
import json
from pathlib import Path
import boston_summer_st_list as listing

HERE = Path(__file__).resolve().parent

# These descriptions are proposed wording, not an independent audit.  The prior
# workbook and its original rating inputs remain untouched.
CHANGES = {
    1: {'zh_desc':'约2.5英里的红砖历史步道，连接16处官方历史站点。',
        'en_desc':'A roughly 2.5-mile red-brick historic trail linking 16 official historic sites.'},
    2: {'zh_desc':'自由之路沿线的历史公共公园。',
        'en_desc':'Historic public park on the Freedom Trail.'},
    5: {'zh_desc':'1660年建立的历史墓地，安葬有萨缪尔·亚当斯、约翰·汉考克和保罗·里维尔等人。',
        'en_desc':'Historic burying ground established in 1660; Samuel Adams, John Hancock and Paul Revere are buried here.'},
    6: {'address':'58 Tremont St.',
        'zh_desc':'1686年创立的国王礼拜堂与相邻墓地，是波士顿早期宗教和墓葬历史地标。',
        'en_desc':'Founded in 1686, King’s Chapel and its adjacent burying ground are early Boston religious and burial landmarks.',
        'source':'https://www.thefreedomtrail.org/trail-sites/kings-chapel-kings-chapel-burying-ground'},
    7: {'zh_desc':'1635年创立的波士顿拉丁学校旧址，现以马赛克和富兰克林雕像标记。',
        'en_desc':'The site of Boston Latin School, founded in 1635, is marked by a mosaic and a Benjamin Franklin statue.',
        'source':'https://www.thefreedomtrail.org/trail-sites/boston-latin-school-sitebenjamin-franklin-statue'},
    8: {'zh_desc':'建于1718年的历史商业建筑，曾是19世纪出版商 Ticknor and Fields 的所在地。',
        'en_desc':'Historic commercial building built in 1718 and once home to nineteenth-century publisher Ticknor and Fields.',
        'source':'https://www.thefreedomtrail.org/trail-sites/old-corner-bookstore'},
    17: {'zh_desc':'位于邮政广场的公共公园，原址曾是地面停车楼。',
         'en_desc':'Public park at Post Office Square, on the site of a former above-ground parking garage.',
         'source':'https://www.bostonplans.org/news-calendar/news-updates/2014/06/11/american-planning-association-honors-norman-b-leve',
         'source_name':'Boston Planning & Development Agency'},
    18: {'zh_desc':'波士顿市中心的绿道公园；Dewey Square 公园位于南站北侧。',
         'en_desc':'Downtown Boston parkland; its Dewey Square parks lie just north of South Station.',
         'address':'Dewey Square',
         'source':'https://www.rosekennedygreenway.org/planning-for-2010-b/'},
    19: {'zh_desc':'1899年开放的历史火车站，现为铁路与公共交通枢纽。',
         'en_desc':'Historic railway station opened in 1899 and now a rail and public transit hub.',
         'address':'2 South Station, Boston, MA 02110',
         'source':'https://dl.tufts.edu/concern/images/m900p408q',
         'source_name':'Tufts Digital Library'},
    20: {'address':'Fort Point, Boston'},
    21: {'zh_desc':'Summer Street 上的堡点历史建筑，屋顶有 Boston Wharf Co. 标牌。',
         'en_desc':'Historic Fort Point building on Summer Street with a Boston Wharf Co. rooftop sign.',
         'address':'263 Summer St.',
         'note':'市历史报告使用363 Summer St./10 Melcher St.；现址网站及另一市政文件使用263 Summer St.，地址差异保留待核。'},
    22: {'zh_desc':'波士顿倾茶事件主题博物馆，茶室与商店可不购博物馆门票进入。',
         'en_desc':'Boston Tea Party museum whose tea room and gift shop may be visited without a museum ticket.'},
    24: {'zh_desc':'堡点滨水公园，纪念波士顿马拉松爆炸案中最年轻的遇难者 Martin W. Richard。',
         'en_desc':'Fort Point waterfront park honoring Martin W. Richard, the youngest victim of the Boston Marathon bombings.'},
    26: {'zh_desc':'波士顿海港沿岸的公共步道，本条关注海港区段。',
         'en_desc':'Public waterfront walk along Boston Harbor; this entry focuses on the Seaport segment.',
         'source':'https://www.bostonharbornow.org/what-we-do/explore/harborwalk/',
         'source_name':'Boston Harbor Now'},
    32: {'source':'https://www.fieldoperations.net/project/harbor-way',
         'source_name':'Field Operations'},
    40: {'zh_desc':'创立于1968年的波士顿三明治店。',
         'en_desc':'Boston sandwich shop founded in 1968.'},
    42: {'zh_desc':'West Street 的旧书与珍本书店，店方标示创立于1825年。',
         'en_desc':'West Street used and antiquarian bookshop; the shop dates its founding to 1825.',
         'source':'https://www.brattlebookshop.com/about'},
    53: {'zh_desc':'海港区海鲜餐厅，三楼屋顶露台可观赏波士顿港。',
         'en_desc':'Seaport seafood restaurant with a third-floor rooftop deck overlooking Boston Harbor.'},
}


def main():
    rows = [dict(x) for x in listing.rows]
    for seq, edits in CHANGES.items():
        rows[seq-1].update(edits)
    result = {'state':'draft; independently verify wording, addresses and source capture before rating',
              'changed_seqs':sorted(CHANGES), 'rows':rows}
    (HERE/'boston_summer_st_revision_draft.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2)+'\n', 'utf-8')
    print(f'{len(CHANGES)} proposed revisions; original inputs and ratings preserved')


if __name__ == '__main__':
    main()
