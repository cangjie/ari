"""Links to WNE pages with identifiable building or facility photos.

The linked photos illustrate the building or facility, not the numbered rooms.
The selected, locally hosted images and authorization record are tracked separately.
"""
PHOTO_PAGES = {
    'wne_welcome_center': [('访客中心外观（2021）', 'https://wne.edu/news/2021/02/ug-open-house-03-06.cfm')],
    'wne_herman_hall': [('Herman Hall 入口（2024）', 'https://wne.edu/news/2024/04/arts-and-sciences-senior-awards-2024.cfm')],
    'wne_csp': [('科学与药学中心外观及药学设施', 'https://wne.edu/pharmacy-and-health-sciences/become-a-student/index.cfm')],
    'wne_damour_library': [('图书馆照片及介绍', 'https://wne.edu/libraries/index.cfm')],
    'wne_blake_law_center': [('法学图书馆照片及介绍', 'https://wne.edu/libraries/index.cfm')],
    'wne_art_gallery': [('校园艺术画廊照片及介绍', 'https://wne.edu/art-gallery/index.cfm')],
    'wne_university_commons': [('校园餐饮区照片及介绍', 'https://wne.edu/become-a-student/why-wne/campus.cfm')],
    'wne_sleith_hall': [('Sleith Hall 外观（2020）', 'https://wne.edu/news/2020/10/coe-senior-awards.cfm'), ('生物医学工程实验设施', 'https://wne.edu/engineering/departments/biomedical-engineering/labs-and-facilities.cfm')],
}


def apply_photo_refs(data):
    stops = {s['place']: s for s in data['stops'].values()}
    for place, refs in PHOTO_PAGES.items():
        stops[place]['official_photo_pages'] = [{'title': title, 'url': url} for title, url in refs]
    return data
