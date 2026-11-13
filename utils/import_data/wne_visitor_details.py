#!/usr/bin/env python3
"""Apply sourced visitor parking and indoor details to the existing WNE route.

The route geometry remains the existing OSM estimate, with its start at the Welcome
Center building, not a verified parking-space coordinate. Run after wne_route_build.py,
or independently to update an already generated route without the unavailable snapshot.
"""
import json
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / 'web_api/tour/data/wne_campus.json'
MAP = 'https://wne.edu/become-a-student/visit/campus-map.cfm'
ACCESS = 'https://wne.edu/become-a-student/visit/doc/Accessibility-map.pdf'
DETAILS = {
    'wne_welcome_center': (
        '驾车可导航至 1215 Wilbraham Road，停在访客中心停车场后步行至访客中心。车位和许可证请按标识并向学校确认；地图起点是访客中心，并非停车位的实测位置。',
        'Navigate to 1215 Wilbraham Road and walk from the Welcome Center parking lot to the Welcome Center. Check parking signs and permit requirements with the university. The map starts at the building, not a surveyed parking space.',
        [('驾车指引', 'https://wne.edu/become-a-student/visit/directions-to-campus.cfm'), ('停车规定', 'https://wne.edu/public-safety/parking-and-traffic.cfm')]),
    'wne_deliso_hall': ('行政、财务及市场与对外事务办公室；性别包容卫生间：一楼 102D、二楼 219。部分卫生间位于办公室内，开放时间可能不同。', 'Administrative, controller, marketing and external affairs offices. Gender-inclusive restrooms: first floor room 102D and second floor room 219. Some restrooms are inside offices and may close earlier.', [('无障碍地图及卫生间', ACCESS)]),
    'wne_emerson_hall': ('校园早期教学楼，设文理学院教室及教师办公室；具体教室请看楼内标识。', 'An early campus academic building with Arts and Sciences classrooms and faculty offices; consult indoor signs for individual rooms.', [('校园介绍', 'https://wne.edu/become-a-student/why-wne/campus.cfm')]),
    'wne_herman_hall': ('文理学院、数学中心、写作中心、艺术工作室和教室所在；学校政策列学生无障碍服务办公室在 105 室。', 'College of Arts and Sciences, Math and Writing Centers, art studio and classrooms. University policy lists Student Accessibility Services in room 105.', [('校园介绍', 'https://wne.edu/become-a-student/why-wne/campus.cfm'), ('无障碍服务政策', 'https://wne.edu/human-resources/policies/americans-with-disabilities-act.cfm')]),
    'wne_csp': ('药学、科学和心理学教室及实验室；二楼 235 室为健康与福祉中心，服务对象以学校规定为准。性别包容卫生间在二楼健康服务区 230A、230B，可能受办公室开放时间限制。', 'Pharmacy, science and psychology classrooms and labs. The Center for Health and Well-Being is on the second floor in room 235; eligibility is set by the university. Gender-inclusive restrooms are in Health Services rooms 230A and 230B, subject to office access.', [('校园地图', MAP), ('健康中心', 'https://wne.edu/center-for-health-and-wellness/medical/index.cfm'), ('无障碍地图及卫生间', ACCESS)]),
    'wne_damour_library': ('图书馆 G 层 G-9 是教育技术办公室，旁边是电视演播室，对面 G-26 是计算机教室；学校 2025 年报道 XR Lab 位于 219 室。教室及实验室是否开放请现场确认。', 'On the ground floor, Educational Technology is in G-9 beside the TV studio and opposite computer classroom G-26. A 2025 university report places the XR Lab in room 219. Check access on site.', [('教育技术办公室', 'https://wne.edu/information-technology/teaching-learning/contact-educational-technology.cfm'), ('XR Lab 报道', 'https://wne.edu/news/2025/01/xr-lab-grand-opening')]),
    'wne_churchill_hall': ('商学院教室、Cohen Trading Room 和技术中心；学校研究生资料称主计算机实验室位于三楼，具体房号与开放情况请确认。', 'College of Business classrooms, Cohen Trading Room and technology center. University graduate resources place the main computer lab on the third floor; confirm its room and access.', [('研究生资源', 'https://wne.edu/admissions/graduate/student-resources'), ('校园介绍', 'https://wne.edu/become-a-student/why-wne/campus.cfm')]),
    'wne_art_gallery': ('St. Germain 校园中心内有艺术画廊、书店和学生服务；性别包容卫生间在一楼，房号未列出。', 'St. Germain Campus Center has an art gallery, bookstore and student services. A gender-inclusive restroom is on the first floor; no room number is listed.', [('校园地图', MAP), ('无障碍地图及卫生间', ACCESS)]),
    'wne_university_commons': ('餐饮、便利店和会议室；学校无障碍地图列每层有性别包容卫生间。营业和访客用餐安排以学校为准。', 'Dining, convenience store and meeting rooms. The accessibility map lists a gender-inclusive restroom on each floor. Check dining hours and visitor access with the university.', [('校园地图', MAP), ('无障碍地图及卫生间', ACCESS)]),
    'wne_sleith_hall': ('工程学院有生理学湿实验室、仪器实验室和模拟病房；学校未在介绍页列出这些实验室房号。ATRANS 交通研究中心位于 212 室，进入实验室须经学校安排。', 'Engineering facilities include physiology, instrumentation and hospital simulation labs; their room numbers are not listed on the department page. The ATRANS transport research center is in room 212. Laboratory access requires university arrangements.', [('生物医学工程实验室', 'https://wne.edu/engineering/departments/biomedical-engineering/labs-and-facilities.cfm'), ('ATRANS 研究中心', 'https://wne.edu/engineering/departments/industrial-engineering-and-engineering-management/atrans.cfm')]),
    'wne_rivers_memorial_hall': ('校园广播、学生出版物及戏剧音乐项目所在；性别包容卫生间在一楼 112、113、114、123、124、125 室。', 'Home to campus radio, student publications and theatre/music programs. Gender-inclusive restrooms: first-floor rooms 112, 113, 114, 123, 124 and 125.', [('校园地图', MAP), ('无障碍地图及卫生间', ACCESS)]),
    'wne_blake_law_center': ('法学院、法律图书馆、法律诊所、模拟法庭和职业治疗系；性别包容卫生间位于一楼院长办公室套间、二楼 220 室及三楼休息区，办公室内卫生间可能提前关闭。', 'School of Law, law library and clinics, moot courtroom and Occupational Therapy department. Gender-inclusive restrooms are in the first-floor Dean’s Suite, room 220 on the second floor and the third-floor lounge. Office restrooms may close early.', [('校园地图', MAP), ('无障碍地图及卫生间', ACCESS)]),
    'wne_golden_bear_stadium': ('户外体育场；比赛和设施开放时间请以学校安排为准。', 'Outdoor stadium; check the university’s event and facility access arrangements.', [('学校体育设施', 'https://wnegoldenbears.com/facilities')]),
    'wne_ahlc': ('体育设施用于篮球、排球及摔跤等；性别包容卫生间位于二楼 Downes Hall of Fame，开放以学校安排为准。', 'Athletics facility used for basketball, volleyball and wrestling. Gender-inclusive restrooms are on the second floor in the Downes Hall of Fame; access is subject to university arrangements.', [('学校体育设施', 'https://wnegoldenbears.com/facilities'), ('无障碍地图及卫生间', ACCESS)]),
}


def apply(data):
    stops = {s['place']: s for s in data['stops'].values()}
    steps = data['itineraries'][0]['steps']
    assert all(step['place'] in stops and step['place'] in DETAILS for step in steps)
    for step in steps:
        pid = step['place']
        stop = stops[pid]
        zh, en, sources = DETAILS[pid]
        step['seq'] = stop['seq']  # app.js uses seq to look up the corresponding stop
        step['note'] = zh
        previous = stop.pop('visitor_detail', None)
        if previous:
            stop['intro'] = [x for x in stop['intro'] if x != previous['zh']]
            stop['intro_en'] = stop['intro_en'].removesuffix(' ' + previous['en'])
        stop['intro'].append(zh)
        stop['intro_en'] += ' ' + en
        stop['visitor_detail'] = {'zh': zh, 'en': en}
        seen = {s['url'] for s in stop['sources']}
        for title, url in sources:
            if url not in seen:
                stop['sources'].append({'title': 'Western New England University · ' + title, 'url': url})
                seen.add(url)
    theme = data['itineraries'][0]
    theme['name'] = '停车场出发：校园建筑参观路线'
    theme['description'] = '停在访客中心停车场，步行至访客中心后依次参观教学楼、图书馆、工程楼和体育设施，最后返回。地图上的起终点是访客中心，停车场至中心的距离未计入。'
    theme['access'] = '步行及停留时间为估计，未实地核对入口和道路。教室、办公室及实验室开放以学校安排为准；卫生间可能在办公区内。'
    for title, url in [('驾车指引', 'https://wne.edu/become-a-student/visit/directions-to-campus.cfm'), ('停车规定', 'https://wne.edu/public-safety/parking-and-traffic.cfm'), ('无障碍地图及卫生间', ACCESS)]:
        if url not in {s['url'] for s in theme['sources']}:
            theme['sources'].append({'title': 'Western New England University · ' + title, 'url': url})
    data['itinerary_stations'][0]['name'] = '访客中心（停车场附近；地图起点）'
    data['itinerary_policy'] = '停在访客中心停车场后步行到访客中心，依地图依次前往各楼，最后返回。地图起点为建筑中心，不是停车位或入口；停车场至中心一段未计距离。路线依据 OSM 步道估算，未经现场验证。'
    data['itinerary_exit_note'] = '步行和停留为估计，不含停车场至访客中心、排队及用餐；室内开放以学校安排为准。'
    return data


def main():
    data = json.loads(DATA.read_text('utf-8'))
    DATA.write_text(json.dumps(apply(data), ensure_ascii=False, indent=2) + '\n', 'utf-8')
    print(DATA)


if __name__ == '__main__':
    main()
