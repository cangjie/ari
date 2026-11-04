"""Address material V3 audit findings using saved, source-backed facts."""
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
KEY='boston_summer_st'
CHANGES={
  2:{'zh_desc':'1634年建立的波士顿公园是美国最古老的公共公园，也是自由之路的起点。',
     'en_desc':'Established in 1634, Boston Common is America’s oldest public park and the starting point of the Freedom Trail.'},
  3:{'zh_desc':'查尔斯·布尔芬奇设计的州议会大厦于1798年启用，内部有多处历史厅室。',
     'en_desc':'Designed by Charles Bulfinch and opened in 1798, the Massachusetts State House contains historic halls and chambers.'},
  4:{'zh_desc':'建于1809年的公园街教堂，其217英尺高的尖塔曾是进入波士顿时的醒目地标。',
     'en_desc':'Founded in 1809, Park Street Church has a 217-foot steeple that once served as a landmark for travelers approaching Boston.'},
  21:{'zh':'波士顿码头公司建筑及屋顶标牌','en':'Boston Wharf Company Building & Sign',
      'note':'现址网站使用 263 Summer St.；屋顶标牌以现场状态为准。'},
  25:{'zh_desc':'位于旧消防站的消防博物馆，展品包括1792年由保罗·里维尔学徒制造的手动水泵车。',
      'en_desc':'Fire museum in a former firehouse, with exhibits including a 1792 hand pumper built by an apprentice to Paul Revere.'},
  39:{'zh_desc':'Arch Street 的智利风味三明治店，由 Juan Hurtado 从手推车经营起步。',
      'en_desc':'Chilean-style sandwich shop on Arch Street, begun by Juan Hurtado as a pushcart operation.'},
  41:{'zh_desc':'Washington Street 的精品咖啡店，店方介绍其以产地、气候和种植者工艺为特色的咖啡理念。',
      'en_desc':'Specialty coffee shop on Washington Street highlighting coffee origin, climate and growers’ craftsmanship.'},
  46:{'zh_desc':'Farnsworth Street 的 Flour 烘焙咖啡店；2007年的街区报道记载这家由 Joanne Chang 经营的门店开业。',
      'en_desc':'Flour bakery and cafe on Farnsworth Street; a 2007 neighborhood report documented the opening of this Joanne Chang-run location.'},
  49:{'zh_desc':'倾茶博物馆的茶室可不购博物馆门票进入，并介绍与倾茶事件有关的茶叶与历史展品。',
      'en_desc':'The Tea Party museum’s tea room is accessible without a museum ticket and offers tea and historical exhibits related to the Tea Party.'},
}


def main():
    data=json.loads((HERE/f'{KEY}_revision_final_draft.json').read_text('utf-8'))
    for seq,edits in CHANGES.items():data['rows'][seq-1].update(edits)
    data['previous_revision_changed_seqs']=data['changed_seqs']
    data['changed_seqs']=sorted(set(data['changed_seqs'])|set(CHANGES))
    data['v3_changed_seqs']=sorted(CHANGES)
    data['state']='draft; additional source audit required'
    (HERE/f'{KEY}_revision_v3_draft.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(f'{len(CHANGES)} additional revisions prepared')


if __name__=='__main__':main()
