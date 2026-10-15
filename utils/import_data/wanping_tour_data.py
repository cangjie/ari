"""宛平城导览画布配置。包围框仅为导览定位范围，不是法定景区边界。"""
ORIGIN = (39.8495, 116.218)
ROTATE_DEG = 0
PX_PER_M = 1.0
AREA_BUFFER_M = 15
CANVAS_MARGIN_PX = 40
AREA_BBOX = (39.8468, 116.2110, 39.8524, 116.2246)
BOUNDARY = 'editorial-tour-envelope'
NAME = ('宛平城及周边', 'Wanping City and Surroundings')
CARD = {
    'city': ('北京', 'Beijing'), 'district': ('丰台区', 'Fengtai'),
    'type': ('古城 · 抗战遗址', 'Historic city and memorials'),
    'short': ('宛平城', 'Wanping City'),
    'desc': ('从宛平城的城门、弹痕到抗战馆、卢沟桥与雕塑园，在“馆桥城园”之间读懂这片土地的历史。',
             'Explore Wanping City, its shell scars, the memorial, Lugou Bridge and the sculpture park.'),
    'hours': '城内公共区域全天开放',
    'hours_note': ('场馆、登城与卢沟桥各有开放时间', 'The memorial, wall-top and bridge have separate hours'),
}
LANDMARKS = []
DEFAULT_ROUTE = 'free'
