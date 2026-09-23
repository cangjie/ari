#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PEM 展览页点名的展厅。**由 pem_site_scrape.py --exhibitions 生成，勿手工编辑。**

19 个被藏品页引用到的目标，其中 3 个唯一点名了 26 个实体展厅之一。

**Tier 1 证据**：馆方自己在展览页上写的「Located in the X.」。
比「按栏目推断」硬得多 —— 后者说的是这件东西属于哪个门类，不是它在哪个房间。

`galleries` 有两个或更多时**一个都不要用**：*On This Ground* 横跨两个普特南展厅，
那是馆方的说法，挑一个写进去就是编。
"""

EXHIBITIONS: dict[str, dict] = {
    'American Art Gallery': dict(url=None,
        galleries=[],
        note='展览 sitemap 里找不到同名页面'),
    'Byrne Family Gallery of Maritime Art': dict(url=None,
        galleries=[],
        note='展览 sitemap 里找不到同名页面'),
    'Carl and Iris Barrel Apfel Gallery of Fashion and Design': dict(url=None,
        galleries=[],
        note='展览 sitemap 里找不到同名页面'),
    'Double Happiness: Celebration in Chinese Art': dict(url='https://www.pem.org/exhibitions/double-happiness-celebration-in-chinese-art',
        galleries=['Yin Yu Tang Interpretive Gallery'],
        note='唯一'),
    'East India Marine Hall': dict(url='https://www.pem.org/exhibitions/east-india-marine-hall',
        galleries=['East India Marine Hall'],
        note='唯一'),
    'Garden Atrium': dict(url=None,
        galleries=[],
        note='展览 sitemap 里找不到同名页面'),
    'Japanese Art Gallery': dict(url=None,
        galleries=[],
        note='展览 sitemap 里找不到同名页面'),
    'On This Ground: Being and Belonging in America': dict(url='https://www.pem.org/exhibitions/on-this-ground-being-and-belonging-in-america',
        galleries=['Barbara Weld Putnam Gallery', 'Nancy and George Putnam Gallery'],
        note='2 个展厅，歧义，不采用'),
    'On this Ground: Being and Belonging in America': dict(url='https://www.pem.org/exhibitions/on-this-ground-being-and-belonging-in-america',
        galleries=['Barbara Weld Putnam Gallery', 'Nancy and George Putnam Gallery'],
        note='2 个展厅，歧义，不采用'),
    'On view on Level 2 of the new wing at the top of the stairs': dict(url=None,
        galleries=[],
        note='展览 sitemap 里找不到同名页面'),
    'On view on the Ground Level of the New Wing stairwell': dict(url=None,
        galleries=[],
        note='展览 sitemap 里找不到同名页面'),
    'Pod': dict(url='https://www.pem.org/exhibitions/the-pod',
        galleries=[],
        note='页面未点名展厅'),
    'Powerful Figures': dict(url='https://www.pem.org/exhibitions/powerful-figures',
        galleries=['Louise Du Pont Crowninshield Gallery'],
        note='唯一'),
    'Salem Stories': dict(url='https://www.pem.org/exhibitions/salem-stories',
        galleries=[],
        note='页面未点名展厅'),
    'Sean M. Healey Family Gallery of Asian Export Art': dict(url=None,
        galleries=[],
        note='展览 sitemap 里找不到同名页面'),
    'Sean M. Healey Gallery of Asian Export Art': dict(url=None,
        galleries=[],
        note='展览 sitemap 里找不到同名页面'),
    'South Asian Art Gallery': dict(url=None,
        galleries=[],
        note='展览 sitemap 里找不到同名页面'),
    'our special exhibitions gallery': dict(url=None,
        galleries=[],
        note='展览 sitemap 里找不到同名页面'),
    'stairway of the new wing': dict(url=None,
        galleries=[],
        note='展览 sitemap 里找不到同名页面'),
}


def gallery_of(target: str) -> str | None:
    """在展原句里的目标 -> 唯一的实体展厅；歧义、没点名、没登记都返回 None。"""
    v = EXHIBITIONS.get(target)
    if not v:
        return None
    g = v["galleries"]
    return g[0] if len(g) == 1 else None
