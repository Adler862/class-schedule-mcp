#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把课表打包成一个自包含的 HTML：双击即用，不需要服务器、不需要 Python、不联网。

为什么要这个东西：
  src/server.py 那套要用户先跑 `python src/server.py`，对不会命令行的人来说等于不可用。
  单文件版本把所有东西塞进一个 .html：数据、渲染、问答、日历导出全在里面，
  发微信/发 U 盘/放桌面双击都能用。

做法：
  周次、单双周、节次这些**容易算错**的逻辑仍然只在 Python（semester.py）里实现一次，
  构建时把所有周的网格预先算好内联进去。前端只做查表渲染，不重复实现业务规则。

用法：
  python tools/build_single.py                       # 输出 dist/课表助手.html
  SCHEDULE_COURSES=... python tools/build_single.py  # 用别的课表数据
"""
import os
import sys
import json
import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(BASE_DIR)
sys.path.insert(0, os.path.join(REPO_ROOT, 'src'))

import semester  # noqa: E402

MAX_WEEK = 24


def build_data(today=None):
    today = today or datetime.date.today()
    data = semester.load()
    start = semester.resolve_start(data)

    weeks = {}
    for w in range(1, MAX_WEEK + 1):
        weeks[str(w)] = semester.week_grid(w, data=data)

    return {
        'meta': semester.meta(data),
        'start': start.isoformat(),
        'today': today.isoformat(),
        'currentWeek': semester.current_week(today, start),
        'maxWeek': MAX_WEEK,
        'periodTimes': {str(k): v for k, v in semester.period_times().items()},
        'periodEnd': {str(k): semester.period_end(k) for k in semester.period_times()},
        'courses': [
            {
                'name': c.get('name', ''),
                'teacher': c.get('teacher', ''),
                'location': c.get('location', ''),
                'day': c.get('day'),
                'startPeriod': c.get('startPeriod'),
                'endPeriod': c.get('endPeriod'),
                'startWeek': c.get('startWeek', 1),
                'totalWeeks': c.get('totalWeeks', 16),
                'weekType': c.get('weekType', 'all'),
                'weeks': c.get('weeks') or [],
            }
            for c in data.get('courses', [])
        ],
        'weeks': weeks,
    }


def render(payload):
    tpl_path = os.path.join(REPO_ROOT, 'tools', 'single_template.html')
    with open(tpl_path, 'r', encoding='utf-8') as f:
        tpl = f.read()
    blob = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
    return tpl.replace('/*__DATA__*/null', blob)


def main():
    payload = build_data()
    html = render(payload)
    out_dir = os.path.join(REPO_ROOT, 'dist')
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, '课表助手.html')
    with open(out, 'w', encoding='utf-8') as f:
        f.write(html)
    size = os.path.getsize(out) / 1024
    print(f'已生成 {out}')
    print(f'  {size:.0f} KB · {len(payload["courses"])} 门课 · {payload["maxWeek"]} 周 · '
          f'当前第 {payload["currentWeek"]} 周')
    print('  双击打开即可，不需要联网、不需要装任何东西。')


if __name__ == '__main__':
    main()
