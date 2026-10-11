#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
今日课表生成器
读取 courses.json（由 WXClassTable 项目的 convert_xls.py 生成），
根据学期起始日期计算当前周次，输出当天课程安排（Markdown 文本）。

用法:
  python today_schedule.py            # 输出今天的课表
  python today_schedule.py 2026-10-09 # 输出指定日期的课表
"""
import sys, os, json, datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COURSES_JSON = os.environ.get('SCHEDULE_COURSES') or os.path.join(
    os.path.dirname(BASE_DIR), 'config', 'courses.json')

# 2026-2027-1 学期第一周周一（用户确认）
SEMESTER_START = datetime.date(2026, 8, 31)

# 节次 → 上课时间（示例大学作息：每小节 45 分钟，大节内课间 10 分钟，大节之间 20 分钟）
PERIOD_TIMES = {
    1: '08:30', 2: '09:25',
    3: '10:30', 4: '11:25',
    5: '14:30', 6: '15:25',
    7: '16:30', 7.5: '', 8: '17:25',
    9: '19:00', 10: '19:55',
    11: '21:00', 12: '21:55',
}

DAY_NAMES = {1: '周一', 2: '周二', 3: '周三', 4: '周四', 5: '周五', 6: '周六', 7: '周日'}


def current_week(today):
    diff = (today - SEMESTER_START).days
    return diff // 7 + 1


def course_active(course, week):
    weeks = course.get('weeks') or []
    if weeks:
        return week in weeks
    start = course.get('startWeek', 1)
    total = course.get('totalWeeks', 16)
    if not (start <= week <= start + total - 1):
        return False
    rel = week - start + 1
    wt = course.get('weekType', 'all')
    if wt == 'odd' and rel % 2 == 0:
        return False
    if wt == 'even' and rel % 2 == 1:
        return False
    return True


def period_time(sp, ep):
    st = PERIOD_TIMES.get(sp, '')
    et = PERIOD_TIMES.get(ep + 0.5 if ep in (7,) else ep, '')
    # 结束时间 = 最后一小节的下课时间，这里用该小节的上课时间+45min 估算
    if ep in PERIOD_TIMES and PERIOD_TIMES[ep]:
        h, m = map(int, PERIOD_TIMES[ep].split(':'))
        end = f'{h:02d}:{m + 45:02d}' if m + 45 < 60 else f'{h + 1:02d}:{m + 45 - 60:02d}'
    else:
        end = ''
    return f'{st}–{end}' if st else ''


def generate(today=None):
    if today is None:
        today = datetime.date.today()
    week = current_week(today)
    day = today.isoweekday()

    with open(COURSES_JSON, 'r', encoding='utf-8') as f:
        data = json.load(f)

    courses = [c for c in data['courses']
               if c.get('day') == day and course_active(c, week)]
    courses.sort(key=lambda c: c.get('startPeriod', 0))

    lines = []
    lines.append(f'## 今日课表 · {today.strftime("%Y-%m-%d")} {DAY_NAMES[day]}（第 {week} 周）')
    lines.append('')
    if not courses:
        lines.append('今天没有课，好好休息或自习吧。')
    else:
        for c in courses:
            t = period_time(c['startPeriod'], c['endPeriod'])
            note = f"（{c['note']}）" if c.get('note') else ''
            lines.append(
                f"- **{c['startPeriod']:02d}-{c['endPeriod']:02d}节** {t} | "
                f"{c['name']}{note} | {c.get('teacher', '')} | {c.get('location', '')}"
            )
        lines.append('')
        first = courses[0]
        lines.append(f'第一节课 {PERIOD_TIMES.get(first["startPeriod"], "")} '
                     f'{first["name"]} @ {first.get("location", "")}，别迟到。')
    return '\n'.join(lines)


if __name__ == '__main__':
    d = None
    if len(sys.argv) > 1:
        d = datetime.date.fromisoformat(sys.argv[1])
    print(generate(d))
