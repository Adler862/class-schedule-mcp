#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Web API 层：纯函数，不碰 socket。

`handle()` 接收解析好的 HTTP 要素，返回 (status, content_type, bytes)。
好处是全部接口都能在单元测试里直接调，不需要起服务、不需要端口。
真正的 HTTP 适配在 `server.py`。
"""
import os
import re
import json
import datetime
import urllib.parse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(BASE_DIR)
if BASE_DIR not in os.sys.path:
    os.sys.path.insert(0, BASE_DIR)

import semester  # noqa: E402

DAY_CHARS = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '日': 7, '天': 7,
             '1': 1, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7}

HELP_TEXT = (
    '可以这样问我：\n'
    '· 今天有什么课 / 今天几节课\n'
    '· 明天课表 / 后天有课吗 / 周三有课吗\n'
    '· 本周课表\n'
    '· 下一节是什么课\n'
    '· 哪天空\n'
    '· 数据结构什么时候上'
)


def _json(payload, status=200):
    return status, 'application/json; charset=utf-8', json.dumps(
        payload, ensure_ascii=False).encode('utf-8')


def _text(payload, status=200, ctype='text/plain; charset=utf-8'):
    return status, ctype, payload.encode('utf-8')


def _first(query, key, default=None):
    if not query:
        return default
    vals = query.get(key)
    if not vals:
        return default
    return vals[0]


# ---------- 路由 ----------

def handle(method, path, query=None, body=None, root=None, today=None):
    """分派请求。today 可注入，便于测试固定日期。"""
    root = root or REPO_ROOT
    today = today or datetime.date.today()
    path = urllib.parse.unquote(path or '/')

    if method == 'POST':
        if path == '/api/overrides':
            return _post_overrides(body)
        return _json({'error': 'method not allowed'}, 405)

    if method not in ('GET', 'HEAD'):
        return _json({'error': 'method not allowed'}, 405)

    if path == '/healthz':
        return _text('ok')

    if path in ('/', '/index.html'):
        return _serve_file(root, 'web/index.html', 'text/html; charset=utf-8')

    if path == '/api/meta':
        return _json(semester.meta())

    if path == '/api/week':
        raw = _first(query, 'week')
        if raw is None or raw == '':
            week = semester.current_week(today)
        else:
            try:
                week = int(raw)
            except (TypeError, ValueError):
                return _json({'error': 'week 必须是整数'}, 400)
        return _json({'week': week, 'days': semester.week_grid(week)})

    if path == '/api/today':
        raw = _first(query, 'date') or today.isoformat()
        try:
            day = datetime.date.fromisoformat(raw)
        except ValueError:
            return _json({'error': 'date 需为 YYYY-MM-DD'}, 400)
        return _json(_day_payload(day, today))

    if path == '/api/overrides':
        return _json({'overrides': semester.load_overrides()})

    if path == '/api/ask':
        q = _first(query, 'q', '') or ''
        return _json(ask(q, today))

    if path == '/api/export.ics':
        return build_ics()

    return _json({'error': 'not found'}, 404)


def _serve_file(root, rel, ctype):
    full = os.path.normpath(os.path.join(root, rel))
    if not full.startswith(os.path.normpath(root)) or not os.path.isfile(full):
        return _json({'error': 'not found'}, 404)
    with open(full, 'rb') as f:
        return 200, ctype, f.read()


def _day_payload(day, today=None):
    today = today or datetime.date.today()
    courses = semester.courses_of(day)
    return {
        'date': day.isoformat(),
        'week': semester.current_week(day),
        'weekday': semester.DAY_NAMES[day.isoweekday()],
        'courses': courses,
        'next': _next_course(day, courses, today),
    }


# ---------- 下一节课 ----------

def _next_course(day, courses, today, now=None):
    """最近的一节课及其倒计时；当天已上完则往后找 6 天。"""
    now = now or datetime.datetime.now()
    for offset in range(0, 7):
        d = day + datetime.timedelta(days=offset)
        cs = courses if offset == 0 else semester.courses_of(d)
        for c in cs:
            if not c.get('start'):
                continue
            hh, mm = map(int, c['start'].split(':'))
            start_dt = datetime.datetime.combine(d, datetime.time(hh, mm))
            if start_dt <= now:
                continue
            delta = start_dt - now
            hours, rem = divmod(int(delta.total_seconds()), 3600)
            return {
                'name': c['name'],
                'location': c['location'],
                'start': c['start'],
                'end': c['end'],
                'date': d.isoformat(),
                'weekday': semester.DAY_NAMES[d.isoweekday()],
                'countdown': f'{hours}小时{rem // 60}分' if hours else f'{rem // 60}分',
                'startTs': start_dt.isoformat(timespec='minutes'),
            }
    return None


# ---------- 自然语言问答 ----------

def ask(q, today=None):
    """规则版意图解析。返回 {intent, text, data}。

    不做语义模型：这个场景的句式高度集中，规则命中率够用且零依赖、零延迟。
    """
    today = today or datetime.date.today()
    q = (q or '').strip()

    if not q:
        return {'intent': 'help', 'text': HELP_TEXT, 'data': None}

    if re.search(r'帮助|怎么用|用法|菜单|指令|help', q, re.I):
        return {'intent': 'help', 'text': HELP_TEXT, 'data': None}

    if re.search(r'天气|气温|下雨|降温|冷不冷|热不热|带伞', q):
        return {'intent': 'unknown', 'text': '天气还不支持哦，先问我课表吧。\n\n' + HELP_TEXT,
                'data': None}

    if re.search(r'本周|这周|整周|周表|一周', q):
        week = semester.current_week(today)
        grid = semester.week_grid(week)
        total = sum(len(d['courses']) for d in grid)
        return {'intent': 'week',
                'text': f'本周是第 {week} 周，共 {total} 节课。',
                'data': {'week': week, 'days': grid}}

    if re.search(r'下一节|下节|接下来|还有多久|最近.*课', q):
        today_courses = semester.courses_of(today)
        nxt = _next_course(today, today_courses, today)
        if not nxt:
            return {'intent': 'next', 'text': '接下来 7 天没有课。', 'data': None}
        when = '今天' if nxt['date'] == today.isoformat() else nxt['weekday']
        return {'intent': 'next',
                'text': f'{when} {nxt["start"]} 上 {nxt["name"]}，'
                        f'还有 {nxt["countdown"]}（{nxt["location"]}）。',
                'data': nxt}

    if re.search(r'哪天空|哪天没课|有空|空课|没课', q):
        free = []
        for offset in range(1, 8):
            d = today + datetime.timedelta(days=offset)
            if not semester.courses_of(d):
                free.append({'date': d.isoformat(), 'weekday': semester.DAY_NAMES[d.isoweekday()]})
        if not free:
            return {'intent': 'free', 'text': '接下来一周每天都有课，辛苦了。', 'data': []}
        names = '、'.join(f['weekday'] for f in free)
        return {'intent': 'free', 'text': f'接下来一周 {names} 没课。', 'data': free}

    hit = _match_course(q)
    if hit:
        return {'intent': 'course', 'text': _course_text(hit), 'data': hit}

    m = re.search(r'周([一二三四五六日天1-7])', q)
    if m:
        target = DAY_CHARS[m.group(1)]
        delta = target - today.isoweekday()
        return {'intent': 'day', 'text': '', 'data': _day_payload(
            today + datetime.timedelta(days=delta), today)}

    for word, offset in (('前天', -2), ('昨天', -1), ('明天', 1), ('后天', 2)):
        if word in q:
            d = today + datetime.timedelta(days=offset)
            payload = _day_payload(d, today)
            payload['label'] = word
            return {'intent': 'day', 'text': f'{word}（{payload["weekday"]}）共 {len(payload["courses"])} 节课。',
                    'data': payload}

    if re.search(r'今天|今日', q):
        payload = _day_payload(today, today)
        return {'intent': 'today',
                'text': f'今天（{payload["weekday"]}）共 {len(payload["courses"])} 节课。',
                'data': payload}

    return {'intent': 'unknown', 'text': f'没太懂「{q}」。\n\n' + HELP_TEXT, 'data': None}


_NOISE = re.compile(r'(在哪儿上|在哪上|在哪|什么时候上|什么时候|几节课|几节|上什么|有课吗|上课|在哪呢|呢|吗|的|课)')


def _post_overrides(body):
    """增删一处调课。

    请求体是 JSON：
      {"action":"move",  "name","fromDate","fromPeriod","span","toDate","toPeriod",
                         "teacher","location","room"}
      {"action":"cancel", ...同上但没有 to*}
      {"action":"undo",  "name","fromDate","fromPeriod"}
      {"action":"clear"}
    返回操作后的完整例外列表，前端直接拿它重绘。
    """
    try:
        req = json.loads((body or b'').decode('utf-8') or '{}')
    except (ValueError, UnicodeDecodeError):
        return _json({'error': '请求体不是合法 JSON'}, 400)
    if not isinstance(req, dict):
        return _json({'error': '请求体必须是对象'}, 400)

    action = req.get('action')
    items = semester.load_overrides()

    if action == 'clear':
        semester.save_overrides([])
        return _json({'overrides': []})

    if action == 'undo':
        missing = [k for k in ('name', 'fromDate', 'fromPeriod') if not req.get(k)]
        if missing:
            return _json({'error': '缺少字段：' + '、'.join(missing)}, 400)
        kept = [o for o in items
                if not (o['name'] == req['name'] and o['fromDate'] == req['fromDate']
                        and int(o['fromPeriod']) == int(req['fromPeriod']))]
        semester.save_overrides(kept)
        return _json({'overrides': kept})

    if action not in ('move', 'cancel'):
        return _json({'error': "action 只能是 move / cancel / undo / clear"}, 400)

    missing = [k for k in ('name', 'fromDate', 'fromPeriod') if not req.get(k)]
    if action == 'move':
        missing += [k for k in ('toDate', 'toPeriod') if not req.get(k)]
    if missing:
        return _json({'error': '缺少字段：' + '、'.join(missing)}, 400)

    try:
        datetime.date.fromisoformat(req['fromDate'])
        if action == 'move':
            datetime.date.fromisoformat(req['toDate'])
        entry = {
            'name': req['name'],
            'fromDate': req['fromDate'],
            'fromPeriod': int(req['fromPeriod']),
            'span': int(req.get('span') or 2),
            'type': action,
            'teacher': req.get('teacher', ''),
            'location': req.get('location', ''),
            'room': req.get('room', ''),
        }
        if action == 'move':
            entry['toDate'] = req['toDate']
            entry['toPeriod'] = int(req['toPeriod'])
        if entry['fromDate'] == entry.get('toDate') and \
                entry['fromPeriod'] == entry.get('toPeriod'):
            return _json({'error': '原时间和目标时间相同'}, 400)
    except (TypeError, ValueError):
        return _json({'error': '日期或节次格式不对'}, 400)

    kept = [o for o in items
            if not (o['name'] == entry['name'] and o['fromDate'] == entry['fromDate']
                    and int(o['fromPeriod']) == int(entry['fromPeriod']))]
    kept.append(entry)
    semester.save_overrides(kept)
    return _json({'overrides': kept})


def _match_course(q):
    """按课名匹配，允许只说前缀。

    用户问「算法设计在哪上」很少把「算法设计与分析」说全，所以先把疑问词剥掉
    得到 core，再看 core 与课名是否互相包含。多个命中取名字最长的，
    避免「计算机组成原理」被「计算机」抢走。
    """
    data = semester.load()
    core = _NOISE.sub('', re.sub(r'[?？。，,、\s]', '', q))
    best = None
    for c in data.get('courses', []):
        name = c.get('name') or ''
        if len(name) < 2:
            continue
        hit = name in q or (len(core) >= 2 and (core in name or name in core))
        if hit and (best is None or len(name) > len(best.get('name') or '')):
            best = c
    if not best:
        return None

    name = best.get('name')
    slots = [_slot(c) for c in data.get('courses', []) if c.get('name') == name]
    slots.sort(key=lambda s: (s['day'], s['startPeriod']))
    out = dict(slots[0])
    out['slots'] = slots          # 一门课一周可能有多个时段，前端可以整体展示
    return out


def _slot(c):
    weeks = [w for w in range(1, 31) if semester.course_active(c, w)]
    return {
        'name': c.get('name'),
        'teacher': c.get('teacher'),
        'location': c.get('location'),
        'room': semester.short_room(c.get('location')),
        'day': c.get('day'),
        'weekday': semester.DAY_NAMES.get(c.get('day'), ''),
        'startPeriod': c.get('startPeriod'),
        'endPeriod': c.get('endPeriod'),
        'start': semester.period_start(c.get('startPeriod')),
        'end': semester.period_end(c.get('endPeriod')),
        'weeks': weeks,
        'weekType': c.get('weekType', 'all'),
    }


def _week_ranges(weeks):
    """[2,4,6,8] → 2-8 双周；[1,2,3,5] → 1-3、5 周。"""
    if len(weeks) >= 4:
        step = weeks[1] - weeks[0]
        if step == 2 and all(weeks[i] - weeks[i - 1] == 2 for i in range(1, len(weeks))):
            tail = '单周' if weeks[0] == 1 else ('双周' if weeks[0] == 2 else '隔周')
            return f'{weeks[0]}-{weeks[-1]} {tail}'
    out, i = [], 0
    while i < len(weeks):
        j = i
        while j + 1 < len(weeks) and weeks[j + 1] == weeks[j] + 1:
            j += 1
        out.append(str(weeks[i]) if j == i else f'{weeks[i]}-{weeks[j]}')
        i = j + 1
    return '、'.join(out) + ' 周'


def _course_text(c):
    head = c['name'] + (f'（{c["teacher"]}）' if c.get('teacher') else '')
    lines = [f'{s["weekday"]} 第 {s["startPeriod"]}-{s["endPeriod"]} 节 · '
             f'{s.get("room") or s.get("location") or ""} · {_week_ranges(s["weeks"])}'
             for s in c.get('slots') or [c]]
    return head + '\n' + '\n'.join(lines)


# ---------- 日历导出 ----------

def _ics_escape(s):
    return (s or '').replace('\\', '\\\\').replace(';', r'\;').replace(',', r'\,').replace('\n', r'\n')


def _first_active_week(course):
    start = course.get('startWeek', 1)
    total = course.get('totalWeeks', 16)
    for w in range(start, start + total):
        if semester.course_active(course, w):
            return w
    return None


def build_ics(today=None):
    """把整学期课程导成 iCalendar，手机日历可直接订阅/导入。

    一门课一个 VEVENT，用 RRULE 表达每周/单双周重复，而不是逐周展开——
    前者在日历里是 8 条，后者是上百条，手机上会很难看。
    """
    data = semester.load()
    start = semester.resolve_start(data)
    lines = [
        'BEGIN:VCALENDAR',
        'VERSION:2.0',
        'PRODID:-//class-schedule-web//CN',
        'CALSCALE:GREGORIAN',
        'METHOD:PUBLISH',
        'X-WR-CALNAME:我的课表',
    ]
    stamp = datetime.datetime.now().strftime('%Y%m%dT%H%M%SZ')

    for idx, c in enumerate(data.get('courses', [])):
        week = _first_active_week(c)
        if week is None:
            continue
        day = c.get('day')
        if not day:
            continue
        d = start + datetime.timedelta(days=(week - 1) * 7 + (day - 1))
        st = semester.period_start(c.get('startPeriod'))
        et = semester.period_end(c.get('endPeriod'))
        if not st or not et:
            continue
        interval = 2 if c.get('weekType') in ('odd', 'even') else 1
        count = max(1, (c.get('totalWeeks', 16) + interval - 1) // interval)

        summary = c.get('name', '')
        if c.get('location'):
            summary = f'{summary} @ {c["location"]}'

        lines += [
            'BEGIN:VEVENT',
            f'UID:course-{idx}-{d.strftime("%Y%m%d")}@class-schedule-web',
            f'DTSTAMP:{stamp}',
            f'DTSTART:{d.strftime("%Y%m%d")}T{st.replace(":", "")}00',
            f'DTEND:{d.strftime("%Y%m%d")}T{et.replace(":", "")}00',
            f'RRULE:FREQ=WEEKLY;INTERVAL={interval};COUNT={count}',
            f'SUMMARY:{_ics_escape(summary)}',
            f'LOCATION:{_ics_escape(c.get("location", ""))}',
            f'DESCRIPTION:{_ics_escape(c.get("teacher", ""))}',
            'END:VEVENT',
        ]

    lines.append('END:VCALENDAR')
    payload = '\r\n'.join(lines) + '\r\n'
    return 200, 'text/calendar; charset=utf-8', payload.encode('utf-8')
