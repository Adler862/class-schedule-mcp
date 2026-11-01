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
  python tools/build_single.py                                  # 输出 dist/课表助手.html
  python tools/build_single.py --courses 我的课表.json --out dist/我的课表.html
  python tools/build_single.py --date 2026-11-02                # 假装今天是这天（截图/演示用）

为什么 --courses 要在 import semester 之前塞进环境变量：
  semester.COURSES_JSON 是模块导入时求值的常量，导入后再改环境变量没用。
  所以先解析参数、再 import，是这里唯一正确的顺序。
"""
import os
import sys
import json
import argparse
import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(BASE_DIR)
sys.path.insert(0, os.path.join(REPO_ROOT, 'src'))

MAX_WEEK = 24


def parse_args(argv=None):
    p = argparse.ArgumentParser(description='把课表打包成单文件 HTML')
    p.add_argument('--courses', help='课表 JSON 路径（默认 config/courses.json）')
    p.add_argument('--out', help='输出文件路径（默认 dist/课表助手.html）')
    p.add_argument('--date', help='把哪天当作今天，YYYY-MM-DD（默认系统日期）')
    return p.parse_args(argv)


# 被测试 import 时不要去解析真实的 sys.argv（否则 pytest 的参数会被当成课表路径）
_cli = parse_args() if __name__ == '__main__' else parse_args([])
if _cli.courses:
    # 必须在 import semester 之前生效
    os.environ['SCHEDULE_COURSES'] = os.path.abspath(_cli.courses)

import semester  # noqa: E402


def needed_weeks(data):
    """课表实际需要几周。固定 24 周会让学期结束后拖一串空周，按数据算更准。"""
    last = 0
    for c in data.get('courses', []):
        wk = c.get('weeks') or []
        if wk:
            last = max(last, max(wk))
        else:
            last = max(last, c.get('startWeek', 1) + c.get('totalWeeks', 16) - 1)
    return max(16, min(last, 30))


def build_palette(data):
    """课程名 → 颜色序号。按首次出现顺序发号，同一门课整学期同色。"""
    order = {}
    for c in data.get('courses', []):
        name = c.get('name', '')
        if name and name not in order:
            order[name] = len(order)
    return order


def build_data(today=None, demo=False):
    data = semester.load()
    start = semester.resolve_start(data)
    max_week = needed_weeks(data)

    weeks = {}
    for w in range(1, max_week + 1):
        weeks[str(w)] = semester.week_grid(w, data=data)

    now = today or datetime.date.today()

    return {
        'meta': semester.meta(data),
        'start': start.isoformat(),
        # 只有 --date 显式指定才写死日期；否则前端跟着系统时间走
        'today': now.isoformat() if demo else None,
        # 不写 currentWeek：前端自己按系统时间算，写进来只会让产物每天变一次，
        # 导致「同一个数据两次构建结果不同」，也就没法把构建产物提交进仓库当演示页。
        'maxWeek': max_week,
        'palette': build_palette(data),
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
    demo = bool(_cli.date)
    today = datetime.date.fromisoformat(_cli.date) if demo else None

    payload = build_data(today=today, demo=demo)
    html = render(payload)

    out = _cli.out or os.path.join(REPO_ROOT, 'dist', '课表助手.html')
    out = out if os.path.isabs(out) else os.path.join(os.getcwd(), out)
    os.makedirs(os.path.dirname(out) or '.', exist_ok=True)
    with open(out, 'w', encoding='utf-8') as f:
        f.write(html)
    size = os.path.getsize(out) / 1024
    week = semester.current_week(today or datetime.date.today(), semester.resolve_start())
    print(f'已生成 {out}')
    names = {c['name'] for c in payload['courses']}
    print(f'  {size:.0f} KB · {len(names)} 门课 / {len(payload["courses"])} 个时段 · '
          f'{payload["maxWeek"]} 周 · 当前第 {week} 周')
    print('  双击打开即可，不需要联网、不需要装任何东西。')


if __name__ == '__main__':
    main()
