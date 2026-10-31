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
import json
import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(BASE_DIR)

DEFAULT_SEMESTER_START = datetime.date(2026, 8, 31)

COURSES_JSON = os.environ.get('SCHEDULE_COURSES') or os.path.join(
    REPO_ROOT, 'config', 'courses.json')

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

def _entry(course, table=None):
    return {
        'name': course.get('name', ''),
        'teacher': course.get('teacher', ''),
        'location': course.get('location', ''),
        'day': course.get('day'),
        'startPeriod': course.get('startPeriod'),
        'endPeriod': course.get('endPeriod'),
        'start': period_start(course.get('startPeriod'), table),
        'end': period_end(course.get('endPeriod'), table),
        'note': course.get('note', ''),
    }


def courses_of(day, data=None, table=None):
    """某一天要上的课，按开始节次排序。"""
    data = data if data is not None else load()
    table = table or period_times()
    week = current_week(day, resolve_start(data))
    picked = [
        c for c in data.get('courses', [])
        if c.get('day') == day.isoweekday() and course_active(c, week)
    ]
    picked.sort(key=lambda c: c.get('startPeriod') or 0)
    return [_entry(c, table) for c in picked]


def week_grid(week, data=None, table=None):
    """整周网格：7 天，每天带日期与课程。"""
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
    return out


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
    }


def _parse_class_name(semester_text):
    """从『学年学期：… 班级：X 专业：…』里抠出班级。"""
    import re
    m = re.search(r'班级：\s*([^\s]+)', semester_text or '')
    return m.group(1) if m else ''
