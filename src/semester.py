#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""学期引擎：课表领域规则的唯一实现。

被三层共用：
  - MCP 层（src/today_schedule.py 薄封装）
  - Web API 层（src/webapp.py）
  - 图片渲染（src/schedule_image.py）

只依赖标准库，任何一层都不该再自己算周次或单双周。

学期起点解析优先级：
  1. 环境变量 SCHEDULE_SEMESTER_START
  2. courses.json 的 meta.semesterStart（吸附到所在周的周一）
  3. 内置默认值 DEFAULT_SEMESTER_START

为什么要吸附到周一：教务系统导出时 meta.semesterStart 常常是**打印日期**而不是学期首日
（实测某高校 2026-2027-1 导出的是 2026-09-03 周四，真实首周周一是 2026-08-31）。
学期总是从周一开始，所以按周吸附比直接信任原值更稳。
"""
import os
import re
import json
import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(BASE_DIR)

DEFAULT_SEMESTER_START = datetime.date(2026, 8, 31)

COURSES_JSON = os.environ.get('SCHEDULE_COURSES') or os.path.join(
    REPO_ROOT, 'config', 'courses.json')

# 调课例外。不存在就是「没有任何调课」，不需要预先创建文件。
OVERRIDES_JSON = os.environ.get('SCHEDULE_OVERRIDES') or os.path.join(
    REPO_ROOT, 'config', 'overrides.json')

# 节次 → 上课时刻（默认作息，可在 config/timetable.json 覆盖）
DEFAULT_PERIOD_TIMES = {
    1: '08:30', 2: '09:25',
    3: '10:30', 4: '11:25',
    5: '14:30', 6: '15:25',
    7: '16:30', 8: '17:25',
    9: '19:00', 10: '19:55',
    11: '21:00', 12: '21:55',
}

DAY_NAMES = {1: '周一', 2: '周二', 3: '周三', 4: '周四', 5: '周五', 6: '周六', 7: '周日'}

_cache = {}


# ---------- 配置读取 ----------

def load(path=None):
    """读取课表数据，按 mtime 缓存。"""
    path = path or COURSES_JSON
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        mtime = 0
    hit = _cache.get(path)
    if hit and hit[0] == mtime:
        return hit[1]
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    data.setdefault('courses', [])
    data.setdefault('meta', {})
    _cache[path] = (mtime, data)
    return data


def period_times():
    """作息表：config/timetable.json 可覆盖默认值。"""
    path = os.path.join(REPO_ROOT, 'config', 'timetable.json')
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                raw = json.load(f)
            table = {int(k): v for k, v in raw.items() if v}
            if table:
                return table
        except (OSError, ValueError):
            pass
    return dict(DEFAULT_PERIOD_TIMES)


# ---------- 学期与周次 ----------

def snap_to_monday(d):
    """把任意日期吸附到它所在周的周一。"""
    return d - datetime.timedelta(days=d.isoweekday() - 1)


def resolve_start(data=None):
    """解析学期首周周一。"""
    env = os.environ.get('SCHEDULE_SEMESTER_START')
    if env:
        try:
            return snap_to_monday(datetime.date.fromisoformat(env.strip()))
        except ValueError:
            pass

    data = data if data is not None else load()
    raw = (data.get('meta') or {}).get('semesterStart')
    if raw:
        try:
            return snap_to_monday(datetime.date.fromisoformat(str(raw)[:10]))
        except ValueError:
            pass

    return DEFAULT_SEMESTER_START


def current_week(today=None, start=None):
    """今天是第几周。学期首日所在周为第 1 周。"""
    today = today or datetime.date.today()
    start = start or resolve_start()
    return (today - start).days // 7 + 1


# ---------- 课程生效判定 ----------

def course_active(course, week):
    """这门课在第 week 周是否要上。"""
    weeks = course.get('weeks') or []
    if weeks:
        return week in weeks

    start = course.get('startWeek', 1)
    total = course.get('totalWeeks', 16)
    if not (start <= week <= start + total - 1):
        return False

    rel = week - start + 1
    week_type = course.get('weekType', 'all')
    if week_type == 'odd' and rel % 2 == 0:
        return False
    if week_type == 'even' and rel % 2 == 1:
        return False
    return True


# ---------- 时间格式 ----------

def _add_minutes(hhmm, minutes):
    """'08:30' + 45 → '09:15'，跨小时正确进位。"""
    try:
        h, m = map(int, hhmm.split(':'))
    except (AttributeError, ValueError):
        return ''
    total = h * 60 + m + minutes
    return f'{(total // 60) % 24:02d}:{total % 60:02d}'


def period_start(period, table=None):
    table = table or period_times()
    return table.get(period, '')


def period_end(period, table=None):
    table = table or period_times()
    start = table.get(period, '')
    return _add_minutes(start, 45) if start else ''


def period_time(start_period, end_period, table=None):
    """'08:30–10:10'；取不到就返回空串。"""
    st = period_start(start_period, table)
    et = period_end(end_period, table)
    return f'{st}–{et}' if st else ''


# ---------- 查询 ----------

def short_room(location):
    """从「东校区云海楼208」里抠出「208」。

    手机上一个课程格子只有 40 多像素宽，全称只能显示成「东校区…」，等于没写。
    房间号才是真正要找的信息，所以窄屏只显示它。
    """
    loc = (location or '').strip()
    if not loc:
        return ''
    m = re.search(r'([A-Za-z]?-?\d{2,4})\s*$', loc)
    return m.group(1) if m else loc


def _entry(course, table=None):
    return {
        'name': course.get('name', ''),
        'teacher': course.get('teacher', ''),
        'location': course.get('location', ''),
        'room': short_room(course.get('location', '')),
        'day': course.get('day'),
        'startPeriod': course.get('startPeriod'),
        'endPeriod': course.get('endPeriod'),
        'start': period_start(course.get('startPeriod'), table),
        'end': period_end(course.get('endPeriod'), table),
        'note': course.get('note', ''),
    }


def load_overrides(path=None):
    """读调课例外。文件不存在或坏掉都当作「没有调课」，不该因此让整页挂掉。"""
    path = path or OVERRIDES_JSON
    if not os.path.exists(path):
        return []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    items = data.get('overrides') if isinstance(data, dict) else data
    if not isinstance(items, list):
        return []
    return [o for o in items if isinstance(o, dict) and o.get('name') and o.get('fromDate')]


def save_overrides(items, path=None):
    """写调课例外：先写临时文件再替换，避免写一半断电留下坏 JSON。"""
    path = path or OVERRIDES_JSON
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump({'overrides': items}, f, ensure_ascii=False, indent=2)
        f.write('\n')
    os.replace(tmp, path)
    return items


def _ov_key(name, date, period):
    return (name, date, int(period))


def apply_overrides(days, overrides=None, table=None):
    """把「这一次」的例外叠到整周网格上。

    语义与单文件版前端的 applyOverrides 完全一致：
      - 源位置：如果这门课这一天这一节的这次被记了例外，就从原处去掉
      - 目标位置：type == 'move' 的，按 toDate/toPeriod 插到对应的天
    课表定义（courses.json）始终不变，所以前面几周的记录不会被追溯修改。
    """
    ovs = load_overrides() if overrides is None else overrides
    if not ovs:
        return days
    table = table or period_times()

    by_source = {_ov_key(o['name'], o['fromDate'], o.get('fromPeriod', 0)): o for o in ovs}
    out = []
    for d in days:
        out.append({
            'day': d['day'], 'weekday': d['weekday'], 'date': d['date'],
            'courses': [c for c in d['courses']
                        if _ov_key(c['name'], d['date'], c['startPeriod']) not in by_source],
        })

    index = {d['date']: d for d in out}
    for o in ovs:
        if o.get('type') != 'move':
            continue
        target = index.get(o.get('toDate'))
        if target is None:
            continue
        span = int(o.get('span') or 2)
        sp = int(o['toPeriod'])
        ep = sp + span - 1
        target['courses'].append({
            'name': o['name'],
            'teacher': o.get('teacher', ''),
            'location': o.get('location', ''),
            'room': o.get('room') or short_room(o.get('location', '')),
            'day': target['day'],
            'startPeriod': sp,
            'endPeriod': ep,
            'start': period_start(sp, table),
            'end': period_end(ep, table),
            'note': '',
            'moved': True,
        })

    for d in out:
        d['courses'].sort(key=lambda c: c.get('startPeriod') or 0)
    return out


def courses_of(day, data=None, table=None):
    """某一天要上的课，按开始节次排序。走 week_grid，调课例外才会生效。"""
    data = data if data is not None else load()
    week = current_week(day, resolve_start(data))
    for d in week_grid(week, data=data, table=table):
        if d['date'] == day.isoformat():
            return d['courses']
    return []


def week_grid(week, data=None, table=None, overrides=None):
    """整周网格：7 天，每天带日期与课程。overrides 省略时读 config/overrides.json。"""
    data = data if data is not None else load()
    table = table or period_times()
    start = resolve_start(data)
    monday = start + datetime.timedelta(days=(week - 1) * 7)
    out = []
    for i in range(7):
        d = monday + datetime.timedelta(days=i)
        picked = [
            c for c in data.get('courses', [])
            if c.get('day') == d.isoweekday() and course_active(c, week)
        ]
        picked.sort(key=lambda c: c.get('startPeriod') or 0)
        out.append({
            'day': d.isoweekday(),
            'weekday': DAY_NAMES[d.isoweekday()],
            'date': d.isoformat(),
            'courses': [_entry(c, table) for c in picked],
        })
    return apply_overrides(out, overrides, table)


def course_palette(data=None):
    """课程名 → 颜色序号，按首次出现顺序发号。

    前端据此着色：同一门课整学期同色，不同课尽量不同色。
    以前前端各自用「名字哈希 % 8」，15 门课必然撞色。
    """
    data = data if data is not None else load()
    order = {}
    for c in data.get('courses', []):
        name = c.get('name', '')
        if name and name not in order:
            order[name] = len(order)
    return order


def meta(data=None):
    """页面头部要展示的信息。"""
    data = data if data is not None else load()
    m = data.get('meta') or {}
    today = datetime.date.today()
    return {
        'student': m.get('student', ''),
        'className': _parse_class_name(m.get('semester', '')),
        'semesterStart': resolve_start(data).isoformat(),
        'today': today.isoformat(),
        'currentWeek': current_week(today, resolve_start(data)),
        'weekday': DAY_NAMES[today.isoweekday()],
        'totalCourses': len(data.get('courses', [])),
        'periodTimes': {str(k): v for k, v in period_times().items()},
        'periodEnd': {str(k): period_end(k) for k in period_times()},
        'palette': course_palette(data),
    }


def _parse_class_name(semester_text):
    """从『学年学期：… 班级：X 专业：…』里抠出班级。"""
    import re
    m = re.search(r'班级：\s*([^\s]+)', semester_text or '')
    return m.group(1) if m else ''
