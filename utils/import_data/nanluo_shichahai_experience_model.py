"""原型号补充游览体验信息；不修改介绍、V3或原审计，失败不自动重试。"""
import json
from pathlib import Path
import codex_cli
import llm_cache
import nanluo_shichahai_pipeline as pipeline

HERE = Path(__file__).resolve().parent
KEY = 'nanluo_shichahai'


def main():
    pipeline.setup()
    package = json.loads((HERE / f'{KEY}_final.json').read_text())
    tour = json.loads((HERE.parents[1] / 'web_api/tour/data' / f'{KEY}.json').read_text())
    rows = [dict(seq=r['source_seq'], name=r['name'], kind=r['shop_kind'],
                 description=r['description'], specialty=r['specialty'],
                 platform=tour['stops'][str(r['source_seq'])]['platform']['zh'],
                 sources=[dict(id=e['source_id'], url=e['url'], quote=e['quote']) for e in r['evidence']])
            for r in package['rows'] if r.get('entry_kind') == '特色商铺']
    system = ('你是街区导览编辑，只用给定已保存资料为16家具体商铺补消费分类与风格标签。'
              '不调用工具，不重新评分，不混分店，不把中戏周边所有店都说成学生食堂或便宜。'
              'category六选一：餐馆、小吃甜品店、咖啡馆、旅游艺术纪念品店、创意食品伴手礼店、邮政文创体验店。'
              '每店选1—3个简短中文标签，解释依据。文艺是基于设计、手作、纸品、空间特色的编辑标签，不能仅凭靠近中戏就贴。'
              '经济实惠只允许有输入价格快照且人均不超过35元的小吃或简餐店；不能把咖啡、伴手礼跨品类比较。'
              '“经济实惠”理由必须写出快照金额并注明非实时价格。没有价格支持时不要贴这个标签。'
              '中戏第二食堂只用于原文明确称呼的店，不保证明星到场。不要推断当前营业、菜单或课程。'
              '输出每店seq/category/tags/reason，不含原资料没有的事实。')
    user = json.dumps(rows, ensure_ascii=False)
    string = dict(type='string')
    item = dict(type='object', properties=dict(seq=dict(type='integer'), category=string,
                tags=dict(type='array', items=string), reason=string),
                required=['seq','category','tags','reason'], additionalProperties=False)
    schema = dict(type='object', properties=dict(items=dict(type='array', items=item)),
                  required=['items'], additionalProperties=False)
    request = dict(system=system, user=user, schema=schema)
    (HERE / f'{KEY}_shop_labels_request.json').write_text(json.dumps(request,ensure_ascii=False,indent=2)+'\n')
    def call():
        result, usage = codex_cli.ask(system, user, schema, 'gpt-5.6-luna', 'medium')
        return result, codex_cli.Usage(usage)
    def validate(value):
        return sorted(r['seq'] for r in value['items']) == list(range(85,101)) and all(1<=len(r['tags'])<=3 for r in value['items'])
    result=llm_cache.call(call, provider='openai_codex', model='gpt-5.6-luna', effort='medium',
                          stage='source_shop_labels', museum_key=KEY, system=system, user=user,
                          schema=schema, scope='16 specific branches; editorial shopping labels; V3 unchanged',
                          retries=0, validate=validate)
    (HERE / f'{KEY}_shop_labels_model.json').write_text(json.dumps(dict(model='gpt-5.6-luna',effort='medium',result=result),ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False),flush=True)


if __name__ == '__main__':main()
