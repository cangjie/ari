"""增补照片的可重放检索下载工具；保留原响应和逐张采纳记录，不自动配图。"""
import concurrent.futures
import hashlib
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

from bs4 import BeautifulSoup
from tls import ssl_ctx

HERE = Path(__file__).resolve().parent
KEY = 'nanluo_shichahai'
OUT = HERE / 'exports' / f'{KEY}_photo_expand_originals'
OUT.mkdir(exist_ok=True)


def save(name, value):
    (HERE / f'{KEY}_{name}.json').write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def extract(source):
    soup = BeautifulSoup(source.get('html', ''), 'html.parser')
    for script in soup.find_all('script'):
        match = re.search(r'var cs_article\s*=\s*("(?:\\.|[^"\\])*")', script.text)
        if match:
            article = json.loads(json.loads(match.group(1)))
            soup = BeautifulSoup(article.get('content', ''), 'html.parser')
            break
    found = []
    for i, img in enumerate(soup.find_all('img')):
        src = img.get('src') or img.get('data-src')
        if not src or src.startswith('data:'):
            continue
        url = urllib.parse.urljoin(source['url'], src)
        # 保存图片附近的真实文本，前后文共同判断；不据最近一个段落自动配图。
        parent = img.parent
        before = [s.get_text(' ', strip=True) for s in parent.find_previous_siblings(limit=3)]
        after = [s.get_text(' ', strip=True) for s in parent.find_next_siblings(limit=3)]
        found.append(dict(source_id=source['id'], source_url=source['url'], title=source.get('title'),
                          index=i, url=url, alt=img.get('alt', ''), before=before[::-1], after=after))
    return found


def download(entry):
    entry = dict(entry)
    name = f"{entry['source_id']}_{entry['index']}"
    path = OUT / (name + '.original')
    try:
        if path.exists():
            data = path.read_bytes()
        else:
            url = urllib.parse.quote(entry['url'], safe=':/?&=%')
            req = urllib.request.Request(url, headers={'User-Agent': entry.get('user_agent', 'Mozilla/5.0'), 'Referer': entry['source_url']})
            with urllib.request.urlopen(req, context=ssl_ctx(), timeout=22) as response:
                data = response.read(15_000_000)
            from PIL import Image
            import io
            Image.open(io.BytesIO(data)).verify()
            path.write_bytes(data)
        entry.update(status='ok', original=str(path.relative_to(HERE)), bytes=len(data),
                     sha256=hashlib.sha256(data).hexdigest())
    except Exception as error:
        entry.update(status='error', error=str(error))
    print(name, entry['status'], entry.get('bytes', entry.get('error')), flush=True)
    return entry


def main():
    capture = json.loads((HERE / f'{KEY}_source_capture.json').read_text())['sources']
    wanted = {'juer', 'guanghua', 'guangfu', 'huoshen', 'taobeile', 'sh_temple_renewal', 'guoshoujing_new'}
    candidates = []
    for source in capture:
        if source['id'] not in wanted and not source['url'].startswith('https://www.pgm.org.cn/pgm/wfjd/20'):
            continue
        for entry in extract(source):
            url = entry['url']
            if source['id'] in wanted:
                if not ('/file/' in url or '/W020' in url):
                    continue
            elif '/images/' not in url or any(t in url for t in ['logo', 'ewm', 'xuanfu']):
                continue
            candidates.append(entry)
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(download, candidates))
    save('photo_expand_downloads', results)
    print('ok', sum(r['status'] == 'ok' for r in results), '/', len(results), flush=True)


if __name__ == '__main__':
    main()
