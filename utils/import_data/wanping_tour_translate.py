"""补齐发布提示英译，沿用luna medium；不改原始资料译文或重调已成功批次。"""
import hashlib
import json
from pathlib import Path

import codex_cli
import llm_cache
import translate_artwork as trans
import wanping_route_data as D
import wanping_tour_data as T

HERE = Path(__file__).resolve().parent


def texts():
    access = json.loads((HERE / D.ACCESS).read_text('utf-8'))
    values = list(D.STATUS.values()) + [D.DEFAULT_STATUS, D.ATTACHMENT_NOTE,
        access['opening']['zh'], access['planning']['zh'], T.NAME[0], D.ENTRANCE_NAME[0]]
    values += [T.CARD[k][0] for k in ['city', 'district', 'type', 'short', 'desc', 'hours_note']]
    values += [p[1] for p in D.PLACES]
    values += [r[k][0] for r in D.ROUTES for k in ['label', 'fee', 'note']]
    return list(dict.fromkeys(values))


def main():
    if llm_cache._connect() is None:
        raise RuntimeError('缓存不可用，停止调用')
    path = HERE / D.TOUR_TRANSLATIONS
    result = json.loads(path.read_text('utf-8')) if path.exists() else dict(model='gpt-5.6-luna', effort='medium', source='AI翻译', values={})
    todo = [t for t in texts() if t not in result['values']]
    if todo:
        system = trans.SYS_ZH2EN.format(what='导览路线、费用与开放提示')
        user = '逐条译成英文，保留免费、收费、外观参观、预约、闭馆与估计的区别：\n' + '\n'.join(f'[{i}] {t}' for i, t in enumerate(todo))
        schema = trans.SCHEMA_OF['zh2en']
        def call():
            data, usage = codex_cli.ask(system, user, schema, model='gpt-5.6-luna', effort='medium')
            return data, codex_cli.Usage(usage)
        data = llm_cache.call(call, provider='openai_codex', model='gpt-5.6-luna', effort='medium',
            stage='trans_tour_notes', museum_key='wanping', system=system, user=user, schema=schema, retries=0,
            validate=lambda r: len(r['items']) == len(todo) and {x['i'] for x in r['items']} == set(range(len(todo))) and all(x['en'].strip() for x in r['items']))
        for r in data['items']:
            result['values'][todo[r['i']]] = dict(en=r['en'], confidence=r['confidence'], source='AI翻译')
    result['input_sha256'] = hashlib.sha256(json.dumps(texts(), ensure_ascii=False).encode()).hexdigest()
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(f"补译{len(todo)}段；当前发布提示共{len(texts())}段，中英成对", flush=True)


if __name__ == '__main__':
    main()
