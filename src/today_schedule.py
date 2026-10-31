#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
今日课表生成器（Markdown 文本）—— MCP 侧的门面。

业务规则已收进 `semester.py`，本文件只负责把结果排成给大模型看的 Markdown。
公开函数名与输出格式保持不变，回归测试见 tests/unit/test_today_schedule_compat.py。

用法:
  python today_schedule.py            # 输出今天的课表
  python today_schedule.py 2026-10-09 # 输出指定日期的课表
"""
import sys
import os
import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import semester  # noqa: E402

# 兼容旧引用：这些名字曾在本模块定义
COURSES_JSON = semester.COURSES_JSON
PERIOD_TIMES = semester.DEFAULT_PERIOD_TIMES
DAY_NAMES = semester.DAY_NAMES
SEMESTER_START = semester.DEFAULT_SEMESTER_START

current_week = semester.current_week
course_active = semester.course_active
period_time = semester.period_time


def generate(today=None):
    """把某天的课表排成 Markdown。"""
    if today is None:
        today = datetime.date.today()
    if isinstance(today, str):
        today = datetime.date.fromisoformat(today)

    week = semester.current_week(today)
    day = today.isoweekday()
    courses = semester.courses_of(today)

    lines = [f'## 今日课表 · {today.strftime("%Y-%m-%d")} {DAY_NAMES[day]}（第 {week} 周）', '']
    if not courses:
        lines.append('今天没有课，好好休息或自习吧。')
    else:
        for c in courses:
            t = semester.period_time(c['startPeriod'], c['endPeriod'])
            note = f"（{c['note']}）" if c.get('note') else ''
            lines.append(
                f"- **{c['startPeriod']:02d}-{c['endPeriod']:02d}节** {t} | "
                f"{c['name']}{note} | {c.get('teacher', '')} | {c.get('location', '')}"
            )
        lines.append('')
        first = courses[0]
        lines.append(f'第一节课 {first["start"]} '
                     f'{first["name"]} @ {first.get("location", "")}，别迟到。')
    return '\n'.join(lines)


if __name__ == '__main__':
    d = None
    if len(sys.argv) > 1:
        d = datetime.date.fromisoformat(sys.argv[1])
    print(generate(d))
