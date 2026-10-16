"""按图片清单从本机留存原件重建手机用图；不联网、不覆盖原图。

需Pillow；可使用Codex工作区提供的Python。默认只检查，--write重建缺失的发布图。
输入、输出都必须符合已登记哈希；更换图片或编码参数要明确更新清单并重新复核。
"""
import argparse
import hashlib
import io
import json
from pathlib import Path

from PIL import Image, ImageOps

HERE = Path(__file__).resolve().parent
TOUR = HERE.parents[1] / 'web_api/tour'


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--manifest', required=True, help='本目录内的图片清单文件名')
    ap.add_argument('--write', action='store_true', help='校验原件后写入发布用图')
    args = ap.parse_args()
    manifest = json.loads((HERE / args.manifest).read_text('utf-8'))
    settings = manifest['jpeg']
    for photo in manifest['photos']:
        original = (HERE / photo['original']['path']).read_bytes()
        assert hashlib.sha256(original).hexdigest() == photo['original']['sha256'], photo['seq']
        image = Image.open(io.BytesIO(original))
        image.verify()
        image = ImageOps.exif_transpose(Image.open(io.BytesIO(original))).convert('RGB')
        image.thumbnail((settings['max_edge'], settings['max_edge']))
        encoded = io.BytesIO()
        image.save(encoded, format='JPEG', quality=settings['quality'],
                   optimize=settings['optimize'], progressive=settings['progressive'])
        body = encoded.getvalue()
        assert hashlib.sha256(body).hexdigest() == photo['sha256'], f"seq{photo['seq']}：编码与清单不符"
        target = TOUR / photo['path']
        if args.write:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
        assert target.read_bytes() == body, photo['path']
    print(f"{len(manifest['photos'])}张：原件完整、发布编码及哈希一致")


if __name__ == '__main__':
    main()
