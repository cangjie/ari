"""Sourced WNE room descriptions. Historical events do not establish permanent use.

Room records are attached to existing buildings; they are not independent GPS points.
Each text states the source's date or historical status when the evidence is old.
"""
REG = ('学校 2023 年院系表格', 'https://wne.edu/enrollment-services/registrar/doc/Request-for-Reactivation-Form%209-23.pdf')
ADA = ('学校无障碍服务政策', 'https://wne.edu/human-resources/policies/americans-with-disabilities-act.cfm')
ACCESS = ('校园无障碍地图', 'https://wne.edu/become-a-student/visit/doc/Accessibility-map.pdf')
HEALTH = ('健康与福祉中心', 'https://wne.edu/center-for-health-and-wellness/medical/index.cfm')
HANDBOOK = ('药学院 2024–2025 学生手册', 'https://wne.edu/pharmacy-and-health-sciences/current/2024-2025-WNE-COPHS-Student-Handbook-10-25-24.pdf')
OLD_MANUAL = ('药学系旧部门手册', 'https://wne.edu/pharmacy-and-health-sciences/faculty-staff/doc/bernier_docs/pharmadminsci_policy_and_procedure_manual.pdf')
ART = ('2026 年艺术社活动记录', 'https://events.wne.edu/events/X5VobC8RvzpC1wnKKz0P/KAbQmIIHfgJOYDVMwDLH7')
STUDY = ('2026 年球队学习活动记录', 'https://events.wne.edu/events/moswkb9BlJVStGx9s4bS/m7Bza42ol3pIa01IxNns3')
FOOTBALL = ('2026 年球队会议记录', 'https://events.wne.edu/events/eujlvEGPF36N8KrKILPv/PJLPA0IRHLNwyMGYJdRP11')
FOOTBALL_209 = ('2026 年球队会议记录（209 室）', 'https://events.wne.edu/events/UUFV50QgxaVwE5zGbRCT/ZUGy8uPDPRFatEqwVGAS6')
ORIENT = ('2021 年迎新活动资料', 'https://wne.edu/student-involvement-and-leadership/first-year/doc/Opening-Day-flyer-8.21.pdf')
EVENT_108 = ('2024 年学校活动报道', 'https://wne.edu/news/2024/02/cob-future-of-work-week-johnson')
ED_OLD = ('2018 年教育专业手册', 'https://wne.edu/arts-and-sciences/departments/education/doc/elementaryhandbook-oct2018--dp-final.pdf')
MATH_OLD = ('2021 年信息技术手册', 'https://wne.edu/information-technology/doc/OIT_Handbook.pdf')
XR = ('2025 年 XR 实验室报道', 'https://wne.edu/news/2025/01/xr-lab-grand-opening')
EDTECH = ('教育技术办公室', 'https://wne.edu/information-technology/teaching-learning/contact-educational-technology.cfm')
ATRANS = ('ATRANS 研究中心', 'https://wne.edu/engineering/departments/industrial-engineering-and-engineering-management/atrans.cfm')


def room(number, zh, en, source):
    return {'room': number, 'description': {'zh': zh, 'en': en}, 'source': {'title': source[0], 'url': source[1]}}


ROOMS = {
 'wne_herman_hall': [
  room('103', '2026 年学校活动记录显示曾用于橄榄球队学习活动；不能据此确定专属用途。', 'Used for football study sessions in a 2026 event record; permanent use is unverified.', STUDY),
  room('105', '学生无障碍服务办公室；按学校政策提供学生无障碍支持。', 'Student Accessibility Services, as listed in the university accessibility policy.', ADA),
  room('203', '2026 年艺术社曾在此开会；不代表艺术系办公室。', 'The Art Club held meetings here in 2026; this does not establish it as an art department office.', ART),
  room('205', '学校 2023 年表格列作文理学院院长办公室；现况请确认。', 'Listed as the College of Arts and Sciences Dean’s Office in a 2023 university form; confirm current use.', REG),
  room('303', '2021 年手册列为数学中心，提供数学学习辅导；房间现况待确认。', 'Listed as the Math Center, offering mathematics tutoring, in a 2021 handbook; confirm the current location.', MATH_OLD),
  *[room(n, '2026 年活动记录显示曾用于橄榄球队学习活动；不能据此确定专属用途。', 'Used for football study sessions in a 2026 event record; permanent use is unverified.', STUDY) for n in ('304','306')],
 ],
 'wne_csp': [
  *[room(n, '2024–2025 学生手册列为 80 座讲堂，可用于课程或活动；开放情况请确认。', 'Listed as an 80-seat lecture hall in the 2024–2025 student handbook; check access.', HANDBOOK) for n in ('200','300','400')],
  room('300 套间', '旧药学系手册提到该套间后部有存放办公用品的储物柜；手册年份未明，现况待确认。', 'An older pharmacy department manual mentions an office-supply closet at the back of the 300 suite; its date and current use are unverified.', OLD_MANUAL),
  room('216', '学校 2023 年表格列为药学与健康科学学院院长办公室；现况请确认。', 'Listed as the College of Pharmacy and Health Sciences Dean’s Office in a 2023 form; confirm current use.', REG),
  *[room(n, '无障碍地图列为健康服务区内的性别包容卫生间；办公室可能提前关闭。', 'Gender-inclusive restroom in Health Services on the accessibility map; office access may be restricted.', ACCESS) for n in ('230A','230B')],
  room('235', '健康与福祉中心；医疗服务面向学校社区，资格和开放安排以学校规定为准。', 'Center for Health and Well-Being; eligibility and access follow university rules.', HEALTH),
  *[room(n, '学校旧药学系手册列为会议室；文档年份未明，房间现况待确认。', 'Listed as a conference room in an older pharmacy department manual of undetermined date; confirm current use.', OLD_MANUAL) for n in ('332','408','432')],
  room('414', '2024–2025 学生手册列为药学图书室，药学学生使用门禁卡进入；访客权限请确认。', 'The 2024–2025 handbook identifies the pharmacy library here, with card access for pharmacy students; visitor access is unverified.', HANDBOOK),
 ],
 'wne_emerson_hall': [
  room('G100C', '2018 年教育专业手册列为提交项目申请的联系地点；现况待确认。', 'A 2018 education handbook identifies this as an application submission contact location; confirm current use.', ED_OLD),
  room('108A', '2024 年学校报道记录曾在此举办职业交流活动；房间固定用途未核实。', 'A 2024 university report records a career networking event here; permanent use is unverified.', EVENT_108),
  *[room(n, '2026 年学校活动记录显示曾用于橄榄球队会议；不能据此确定房间专属用途。', 'Used for football meetings in a 2026 university event record; permanent use is unverified.', FOOTBALL) for n in ('201','203','206','207','208')],
  room('209', '2026 年学校活动记录显示曾用于橄榄球队会议；不能据此确定房间专属用途。', 'Used for football meetings in a 2026 university event record; permanent use is unverified.', FOOTBALL_209),
 ],
 'wne_damour_library': [
  room('G-9', '教育技术办公室，位于 G 层、电视演播室旁。', 'Educational Technology office on the ground floor beside the TV studio.', EDTECH),
  room('G-26', 'G 层计算机教室，在教育技术办公室对面。', 'Ground-floor computer classroom across from Educational Technology.', EDTECH),
  room('219', '学校 2025 年报道列为 XR Lab，探索虚拟、增强及混合现实；访客参观需确认。', 'The university’s 2025 report identifies the XR Lab here for virtual, augmented and mixed reality; confirm visitor access.', XR),
 ],
 'wne_churchill_hall': [room('214', '学校 2023 年表格列为商学院院长办公室；现况请确认。', 'Listed as the College of Business Dean’s Office in a 2023 university form; confirm current use.', REG)],
 'wne_sleith_hall': [
  room('101', '学校 2023 年表格列为工程学院院长办公室；现况请确认。', 'Listed as the College of Engineering Dean’s Office in a 2023 form; confirm current use.', REG),
  room('212', 'ATRANS 研究中心，研究交通安全、驾驶行为及相关人因问题；入内请按学校安排。', 'ATRANS research center studies traffic safety, driving behavior and related human factors; access is subject to university arrangements.', ATRANS),
 ],
}


def apply_rooms(data):
    stops = {s['place']: s for s in data['stops'].values()}
    for place, rooms in ROOMS.items():
        stops[place]['room_details'] = sorted(rooms, key=lambda room: room['room'])
    return data
