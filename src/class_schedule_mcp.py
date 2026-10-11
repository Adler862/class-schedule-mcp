#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
class-schedule-mcp v3 —— 课表 + 每日新闻 MCP 服务（Cherry Studio / iris 用）

工具：
  get_today_schedule(date?)  今日课表（节假日感知 + 上课状态 + 倒计时）
  get_next_course()          下一节课 + 倒计时
  get_week_schedule()        本周课表总览
  get_hot_news()             板块配额制多源热点新闻（科技类限量）
  get_morning_report(date?)  课表 + 新闻合并早报
  handle_command(text)       手动触发：解析微信里发来的指令（课表/明天/新闻/早报/调偏好…）
  get_news_prefs()           查看新闻偏好（板块配额、科技上限、屏蔽词、源开关）
  set_news_prefs(...)        对话中调整新闻偏好（加关键词/屏蔽词/兴趣板块/配额）

新闻板块模型（v3 起）：
  兴趣板块（默认：时政/国际、科学/健康、校园/教育、本地/生活）排在前面，
  全网热搜兜底，科技类（AI/大模型 + 科技/大厂）合计受 max_tech_items 限制（默认 3 条，约 25%）。
  板块、关键词、配额、屏蔽词、源开关全部在 news_prefs.json 里，可手动编辑或语音调整。
"""
import sys, os, re, json, time, datetime, urllib.request, urllib.parse, random
from concurrent.futures import ThreadPoolExecutor

# --- 复用课表引擎 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCHEDULE_DIR = BASE_DIR
sys.path.insert(0, SCHEDULE_DIR)
import today_schedule as ts  # noqa: E402

from mcp.server.fastmcp import FastMCP  # noqa: E402

mcp = FastMCP("class-schedule")

PREFS_PATH = os.environ.get('SCHEDULE_PREFS') or os.path.join(
    os.path.dirname(BASE_DIR), 'config', 'news_prefs.json')
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

# 科技类板块：受 max_tech_items 总条数预算约束（默认 3 条，约占全篇 25%）
TECH_SECTIONS = ('AI/大模型', '科技/大厂')

# 本地城市（用于「近期总体气候」，不做每日天气播报）
CITY_NAME = os.environ.get('SCHEDULE_CITY') or '北京'
CITY_CODE = os.environ.get('SCHEDULE_CITY_CODE') or '101010100'  # 中国天气网城市编码（北京）

# 发课表图时的随口一句（随机选用，避免每次都是同一句显得机械）
SCHEDULE_QUIPS = [
    '诺，你要的课表 👆',
    '今天几点上课瞄一眼 👀',
    '这周的课都在这儿啦 📅',
    '别踩点进教室哈',
    '来了来了👆 ',
]


def schedule_quip():
    return random.choice(SCHEDULE_QUIPS)

# 简单内存缓存 {key: (expire_at, value)}
_cache = {}


def _cached(key):
    v = _cache.get(key)
    if v and v[0] > time.time():
        return v[1]
    return None


def _set_cache(key, val, ttl):
    _cache[key] = (time.time() + ttl, val)


def _get_json(url, timeout=8, headers=None):
    req = urllib.request.Request(url, headers=headers or UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8'))


# ============================================================
# 课表部分
# ============================================================

def _period_start_dt(day, period):
    t = ts.PERIOD_TIMES.get(period, '')
    if not t:
        return None
    h, m = map(int, t.split(':'))
    return datetime.datetime.combine(day, datetime.time(h, m))


def _period_end_dt(day, period):
    st = _period_start_dt(day, period)
    return st + datetime.timedelta(minutes=45) if st else None


def _courses_of(day):
    week = ts.current_week(day)
    courses = [c for c in _load_courses()
               if c.get('day') == day.isoweekday() and ts.course_active(c, week)]
    courses.sort(key=lambda c: c.get('startPeriod', 0))
    return week, courses


def _load_courses():
    cached = _cached('courses_data')
    if cached:
        return cached
    with open(ts.COURSES_JSON, 'r', encoding='utf-8') as f:
        data = json.load(f)['courses']
    _set_cache('courses_data', data, 3600)
    return data


def _holiday_info(day):
    """查询节假日（timor.tech 开源节假日 API，GitHub: NateScarlet/holiday-cn 系）。
    返回描述字符串，无特殊信息返回 ''。"""
    key = f'holiday_{day.isoformat()}'
    cached = _cached(key)
    if cached is not None:
        return cached
    desc = ''
    try:
        d = _get_json(f'https://timor.tech/api/holiday/info/{day.isoformat()}', timeout=5)
        t = d.get('type', {})
        ttype, tname = t.get('type'), t.get('name', '')
        if ttype == 2:
            desc = f'🎉 今天是{tname}假期，不用上课'
        elif ttype == 3:
            desc = f'📌 今天是调休工作日（{tname}），按课表上课'
    except Exception:
        desc = ''
    _set_cache(key, desc, 86400)
    return desc


def _fmt_timedelta(td):
    secs = int(td.total_seconds())
    if secs < 0:
        secs = -secs
    h, m = secs // 3600, (secs % 3600) // 60
    if h and m:
        return f'{h} 小时 {m} 分'
    if h:
        return f'{h} 小时'
    return f'{m} 分钟'


def build_schedule(date_str=''):
    day = datetime.date.fromisoformat(date_str.strip()) if date_str.strip() else datetime.date.today()
    week, courses = _courses_of(day)
    now = datetime.datetime.now()
    is_today = (day == datetime.date.today())

    day_names = {1: '周一', 2: '周二', 3: '周三', 4: '周四', 5: '周五', 6: '周六', 7: '周日'}
    holiday = _holiday_info(day)

    lines = [f'## 📅 {day.strftime("%Y-%m-%d")} {day_names[day.isoweekday()]} · 第 {week} 周']
    if holiday:
        lines.append(holiday)
    lines.append('')

    if not courses:
        lines.append('📚 今天没课，自由安排。')
    else:
        next_marked = False
        for c in courses:
            sp, ep = c['startPeriod'], c['endPeriod']
            st_dt = _period_start_dt(day, sp)
            en_dt = _period_end_dt(day, ep)
            time_str = f"{ts.PERIOD_TIMES.get(sp, '')}–{en_dt.strftime('%H:%M') if en_dt else ''}"

            status = ''
            if is_today and st_dt and en_dt:
                if now > en_dt:
                    status = ' ✅'
                elif st_dt <= now <= en_dt:
                    status = ' 🔵上课中'
                elif not next_marked:
                    status = f' ⏳还有{_fmt_timedelta(st_dt - now)}'
                    next_marked = True

            note = f"（{c['note']}）" if c.get('note') else ''
            lines.append(f"**{sp:02d}-{ep:02d}节** {time_str}{status}")
            lines.append(f"　{c['name']}{note} · {c.get('teacher', '')} · 📍{c.get('location', '')}")

    # 今日课程结束后的明日预告
    if day == datetime.date.today():
        tmr = day + datetime.timedelta(days=1)
        tweek, tcourses = _courses_of(tmr)
        if tcourses:
            first = tcourses[0]
            lines.append('')
            lines.append(f"🌙 明日预告：{ts.PERIOD_TIMES.get(first['startPeriod'], '')} "
                         f"{first['name']} @ {first.get('location', '')}（共 {len(tcourses)} 节）")
    return '\n'.join(lines)


def build_next_course():
    now = datetime.datetime.now()
    today = now.date()
    for offset in (0, 1, 2):
        day = today + datetime.timedelta(days=offset)
        week, courses = _courses_of(day)
        for c in courses:
            st_dt = _period_start_dt(day, c['startPeriod'])
            en_dt = _period_end_dt(day, c['endPeriod'])
            if not st_dt:
                continue
            if st_dt <= now <= en_dt:
                return (f"🔵 正在上课：{c['name']} · 📍{c.get('location', '')}\n"
                        f"距下课还有 {_fmt_timedelta(en_dt - now)}")
            if now < st_dt:
                when = '今天' if offset == 0 else ('明天' if offset == 1 else day.strftime('%m-%d'))
                return (f"⏳ 下一节课：{c['name']}（{when} {ts.PERIOD_TIMES.get(c['startPeriod'], '')}）\n"
                        f"📍{c.get('location', '')} · {c.get('teacher', '')}\n"
                        f"距上课还有 {_fmt_timedelta(st_dt - now)}")
    return '📚 今明两天都没有课。'


def build_week_schedule():
    today = datetime.date.today()
    monday = today - datetime.timedelta(days=today.isoweekday() - 1)
    week = ts.current_week(today)
    day_names = {1: '周一', 2: '周二', 3: '周三', 4: '周四', 5: '周五', 6: '周六', 7: '周日'}
    lines = [f'## 🗓 本周课表（第 {week} 周，{monday.strftime("%m-%d")} ~ '
             f'{(monday + datetime.timedelta(days=6)).strftime("%m-%d")}）', '']
    for i in range(7):
        day = monday + datetime.timedelta(days=i)
        _, courses = _courses_of(day)
        mark = ' 👈今天' if day == today else ''
        if not courses:
            lines.append(f"**{day_names[day.isoweekday()]}** {day.strftime('%m-%d')}{mark}：无课")
        else:
            names = '、'.join(f"{c['name']}({c['startPeriod']:02d}-{c['endPeriod']:02d}节)" for c in courses)
            lines.append(f"**{day_names[day.isoweekday()]}** {day.strftime('%m-%d')}{mark}：{names}")
    return '\n'.join(lines)


# ============================================================
# 新闻部分（参考 GitHub 开源：vikiboss/60s API 聚合 + 偏好加权过滤）
# ============================================================

def _load_prefs():
    try:
        with open(PREFS_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {'sections': {}, 'blocked': [], 'sources': {}, 'extra_keywords': [], 'compact': True}


def _save_prefs(prefs):
    with open(PREFS_PATH, 'w', encoding='utf-8') as f:
        json.dump(prefs, f, ensure_ascii=False, indent=2)


BILI_HEADERS = dict(UA)
BILI_HEADERS['Referer'] = 'https://www.bilibili.com'
BILI_HEADERS['Origin'] = 'https://www.bilibili.com'


def _mk(title, source, hot=0):
    return {'title': str(title).strip(), 'source': source, 'hot': hot}


# ============================================================
# 近期气候（北京）：只看趋势，不做每日天气播报
# ============================================================

WEATHER_SLUG_CN = {
    'sunny': '晴', 'clear': '晴',
    'partly-cloudy': '多云', 'cloudy': '多云',
    'overcast': '阴', 'mist': '薄雾', 'fog': '雾',
    'patchy-rain-nearby': '零星小雨', 'patchy-rain-possible': '局部有雨',
    'light-drizzle': '小毛毛雨', 'light-rain': '小雨', 'light-rain-shower': '阵雨',
    'moderate-rain-at-times': '间断中雨', 'moderate-rain': '中雨', 'heavy-rain': '大雨',
    'torrential-rain': '暴雨', 'thundery-outbreaks-possible': '雷阵雨',
    'thundery-showers': '雷阵雨', 'light-sleet': '小雨夹雪', 'sleet': '雨夹雪',
    'light-snow': '小雪', 'snow': '雪', 'heavy-snow': '大雪', 'blizzard': '暴雪',
    'smoky-haze': '霾',
}

RAIN_SLUGS = ('rain', 'drizzle', 'shower', 'thundery', 'sleet', 'snow', 'blizzard')


def _weather_cn(slug):
    slug = (slug or '').strip().lower()
    if slug in WEATHER_SLUG_CN:
        return WEATHER_SLUG_CN[slug]
    for k, v in WEATHER_SLUG_CN.items():
        if k in slug or slug in k:
            return v
    return '多云'


def _fetch_weather_json(city='Hengyang'):
    """主源 wttr.in（纯 JSON，免 key）。"""
    d = _get_json(f'https://wttr.in/{urllib.parse.quote(city)}?format=j1', timeout=12)
    days = []
    for w in (d.get('weather') or [])[:7]:
        try:
            tmax = int(str(w.get('maxtempC', '')).strip() or 0)
            tmin = int(str(w.get('mintempC', '')).strip() or 0)
        except Exception:
            continue
        hourly = w.get('hourly') or []
        mid = hourly[len(hourly) // 2] if hourly else {}
        desc = ((mid.get('weatherDesc') or [{}])[0].get('value') or '').strip()
        slug = desc.lower().replace(' ', '-')
        days.append({'date': str(w.get('date') or ''), 'tmin': tmin, 'tmax': tmax,
                     'slug': slug, 'cn': _weather_cn(slug), 'rain': int(mid.get('chanceofrain') or 0)})
    return days


def _fetch_weather_cn7():
    """兜底源：中国天气网 7 天预报页（原生中文）。失败返回 []。"""
    url = f"https://www.weather.com.cn/weather/{CITY_CODE}.shtml"
    req = urllib.request.Request(url, headers=dict(UA))
    with urllib.request.urlopen(req, timeout=12) as r:
        html = r.read().decode('utf-8', 'ignore')
    blk = re.search(r'<ul class="t clearfix">(.*?)</ul>', html, re.S)
    if not blk:
        return []
    days = []
    for li in re.findall(r'<li.*?</li>', blk.group(1), re.S):
        m_date = re.search(r'<h1>(.*?)</h1>', li, re.S)
        temp_block = re.search(r'<p class="tem">(.*?)</p>', li, re.S)
        if not (m_date and temp_block):
            continue
        temps = [int(x) for x in re.findall(r'(\d+)\s*℃', temp_block.group(1))]
        if not temps:
            continue
        desc = ''
        m_p = re.search(r'<p[^>]*class="wea"[^>]*>(.*?)</p>', li, re.S)
        if m_p:
            desc = re.sub(r'<[^>]+>', '', m_p.group(1)).strip()
        if not desc:
            m_t = re.search(r'title="([^"]*)"', li)
            desc = m_t.group(1).strip() if m_t else '多云'
        # 两个温度值时：第一个是最高温；只有一个值时视为最低温
        tmax = temps[0] if len(temps) > 1 else None
        tmin = temps[1] if len(temps) > 1 else temps[0]
        days.append({'date': re.sub(r'<[^>]+>', '', m_date.group(1)).strip(),
                     'tmax': tmax, 'tmin': tmin, 'cn': desc or '多云',
                     'slug': '', 'rain': 60 if ('雨' in desc or '雪' in desc) else 0})
        if len(days) >= 7:
            break
    return days


def _weather_days():
    """取未来若干天的天气：中国天气网 7 天预报优先（周期长、原生中文），wttr.in 兜底。"""
    cached = _cached('weather_days')
    if cached:
        return cached
    prefs = _load_prefs()
    en = (os.environ.get('SCHEDULE_CITY_EN') or 'Hengyang').strip()
    days = []
    try:
        days = _fetch_weather_cn7()
    except Exception:
        days = []
    if len(days) < 5:
        try:
            alt = _fetch_weather_json(en)
        except Exception:
            alt = []
        if len(alt) > len(days):
            days = alt
    if days:
        _set_cache('weather_days', days, 5400)  # 1.5 小时
    return days


def _city_name():
    try:
        return str(_load_prefs().get('city') or CITY_NAME)
    except Exception:
        return CITY_NAME


def build_weather():
    """近期总体气候（不是每日播报）：一段话概括未来一周。"""
    city = _city_name() or '本地'
    days = _weather_days()
    if not days:
        return f'⚠️ 近期{city}气候暂时取不到（天气源不可用），稍后再试。'
    tmaxs = [d['tmax'] for d in days if d.get('tmax')]
    tmins = [d['tmin'] for d in days if d.get('tmin')]
    cons = []
    for d in days:
        if d.get('cn') and d['cn'] not in cons:
            cons.append(d['cn'])
    rain_days = [d for d in days if d.get('rain', 0) >= 40
                 or any(s in (d.get('slug') or '') for s in RAIN_SLUGS)
                 or '雨' in (d.get('cn') or '') or '雪' in (d.get('cn') or '')]
    lines = [f'🌤️ 近期{city}气候（未来 {len(days)} 天趋势）']
    if tmaxs and tmins:
        lines.append(f'· 气温：白天 {min(tmaxs)}~{max(tmaxs)}℃，夜间 {min(tmins)}~{max(tmins)}℃')
    elif tmins:
        lines.append(f'· 气温：最低 {min(tmins)}~{max(tmins)}℃')
    if cons:
        lines.append(f'· 天气：以{"、".join(cons[:3])}为主')
    if rain_days:
        lines.append(f'· 降水：{len(rain_days)} 天可能有雨，出门带把伞 ☔')
    else:
        lines.append(f'· 降水：这 {len(days)} 天基本无降水 💧')
    td = [d for d in days if d.get('tmax')]
    if len(td) >= 2:
        k = max(1, len(td) // 2)
        early, late = td[:k], td[k:]
        e = sum(d['tmax'] for d in early) / len(early)
        l = sum(d['tmax'] for d in late) / len(late)
        diff = l - e
        if abs(diff) >= 3:
            lines.append(f'· 趋势：后半段比前半段{"升温" if diff > 0 else "降温"}约 {abs(diff):.0f}℃，注意增减衣物')
        else:
            lines.append('· 趋势：气温平稳，波动不大')
    return '\n'.join(lines)


# ---------- 科技/通用源（60s 聚合 API） ----------

def _fetch_it_news():
    d = _get_json('https://60s.viki.moe/v2/it-news')
    return [_mk(i.get('title', ''), 'IT资讯') for i in (d.get('data') or []) if i.get('title')]


def _fetch_weibo():
    d = _get_json('https://60s.viki.moe/v2/weibo')
    return [_mk(i.get('title', ''), '微博', i.get('hot_value', 0)) for i in (d.get('data') or []) if i.get('title')]


def _fetch_zhihu():
    d = _get_json('https://60s.viki.moe/v2/zhihu')
    return [_mk(i.get('title', ''), '知乎', i.get('hot_value', 0)) for i in (d.get('data') or []) if i.get('title')]


def _fetch_toutiao():
    d = _get_json('https://60s.viki.moe/v2/toutiao')
    return [_mk(i.get('title', ''), '头条', i.get('hot_value', 0)) for i in (d.get('data') or []) if i.get('title')]


def _fetch_douyin():
    """抖音热榜：大众民生/突发新闻占比高，用来稀释科技味。"""
    d = _get_json('https://60s.viki.moe/v2/douyin')
    return [_mk(i.get('title') or i.get('word') or '', '抖音', i.get('hot_value', 0))
            for i in (d.get('data') or []) if (i.get('title') or i.get('word'))]


def _fetch_60s_general():
    d = _get_json('https://60s.viki.moe/v2/60s')
    return [_mk(n, '60s') for n in ((d.get('data') or {}).get('news') or []) if str(n).strip()]


def _fetch_bilibili_all():
    """B站全站排行（替代原科技区，减少科技占比）。接口带回 -352 风控时该源自动跳过。"""
    d = _get_json('https://api.bilibili.com/x/web-interface/ranking/v2?rid=0&type=all',
                  headers=BILI_HEADERS)
    out = []
    for v in ((d.get('data') or {}).get('list') or []):
        t = v.get('title')
        if t:
            out.append(_mk(t, 'B站全站', (v.get('stat') or {}).get('view', 0)))
    return out


# ---------- 时政/社会源（澎湃新闻，接口较稳） ----------

THEPAPER_URL = 'https://cache.thepaper.cn/contentapi/wwwIndex/rightSidebar'


def _fetch_thepaper():
    d = _get_json(THEPAPER_URL)
    data = d.get('data') or {}
    out, seen = [], set()
    groups = ('hotNews', 'morningEveningNews', 'financialInformationNews', 'expressNews', 'news')
    for g in groups:
        for it in (data.get(g) or []):
            if not isinstance(it, dict):
                continue
            t = it.get('name') or it.get('title') or ''
            t = str(t).strip()
            if t and t not in seen:
                seen.add(t)
                out.append(_mk(t, '澎湃'))
    return out


# ---------- 百度热搜（独立于 60s，自带民生/财经/国际等榜单，抗限流兜底） ----------

BAIDU_BOARDS = (
    ('realtime', '百度热搜', '百度'),
    ('livelihood', '百度·民生', '百度民生'),
    ('finance', '百度·财经', '百度财经'),
    ('internation_news', '百度·国际', '百度国际'),
)


def _fetch_baidu():
    """按榜抓取百度热搜各分区。这是非科技内容最稳的来源，60s 被限流时仍可用。"""
    out = []
    for tab, _label, source in BAIDU_BOARDS:
        try:
            d = _get_json(f'https://top.baidu.com/api/board?platform=wise&tab={tab}')
            for card in ((d.get('data') or {}).get('cards') or []):
                for grp in (card.get('content') or []):
                    for i, it in enumerate((grp.get('content') or []) if isinstance(grp, dict) else []):
                        if not isinstance(it, dict):
                            continue
                        w = str(it.get('word') or '').strip()
                        # 榜单首位常是置顶标语（如「以创新赢未来」），跳过
                        if w and i > 0:
                            # 榜单本身有序，用名次折算热度，便于板块内排序
                            out.append(_mk(w, source, 3000 - i))
        except Exception:
            continue
    return out


SOURCE_FUNCS = {
    'it_news': _fetch_it_news,
    'weibo': _fetch_weibo,
    'zhihu': _fetch_zhihu,
    'toutiao': _fetch_toutiao,
    'douyin': _fetch_douyin,
    'bilibili_all': _fetch_bilibili_all,
    'thepaper': _fetch_thepaper,
    'baidu_hot': _fetch_baidu,
    '60s_general': _fetch_60s_general,
}

# 每个板块的主源白名单：留空表示不限来源
SECTION_SOURCES = {
    '本地/生活': ('澎湃', '抖音', '微博', '百度', '百度民生'),
    '时政/国际': ('澎湃', '微博', '抖音', '头条', '知乎', '百度国际', '百度财经', '百度'),
    '科学/健康': ('澎湃', '知乎', '微博', 'IT资讯', '百度'),
    '校园/教育': ('澎湃', '微博', '知乎', '抖音', '百度'),
    'AI/大模型': ('IT资讯', '微博', '知乎', 'B站全站', '百度财经', '百度'),
    '科技/大厂': ('IT资讯', '微博', '知乎', 'B站全站', '百度财经', '百度'),
}

# 榜单栏目只是弱提示，不单独作为板块归属依据（否则「百度民生」会把玉璧鉴宝塞进本地生活）
EXTRA_SOURCES = {}

# 一级聚合源：自带分类栏目，板块取材时优先于单条热搜
HUBS = {
    '百度国际': '时政/国际',
    '百度财经': '时政/国际',
    '百度民生': '本地/生活',
    '百度热搜': '全网热搜',
    '澎湃': '时政/国际',
}


def _collect_news(prefs):
    """并发抓取各源，返回 (items, failed_sources)。
    单源失败（限流/风控/超时）只记入 failed，不影响其他板块。"""
    sources = [k for k, on in (prefs.get('sources') or {}).items() if on and k in SOURCE_FUNCS]
    items, failed = [], []
    if not sources:
        return items, failed
    with ThreadPoolExecutor(max_workers=min(8, len(sources))) as ex:
        futs = {ex.submit(SOURCE_FUNCS[s]): s for s in sources}
        for fut, s in futs.items():
            try:
                items.extend(fut.result(timeout=15) or [])
            except Exception:
                failed.append(s)
    return items, failed


def _prefs_cats(prefs):
    """返回 [(板块名, {keywords, icon, quota, ...}), ...]，顺序 = 输出顺序。"""
    cats = prefs.get('categories')
    if isinstance(cats, dict) and cats:
        out = []
        for name, cfg in cats.items():
            c = dict(cfg) if isinstance(cfg, dict) else {}
            c.setdefault('quota', 2)
            c.setdefault('keywords', [])
            out.append((name, c))
        return out
    # 兼容旧格式：sections 视为板块
    return [(n, {'keywords': k, 'icon': '', 'quota': 2})
            for n, k in (prefs.get('sections') or {}).items()]


def _classify(item, prefs):
    """返回 (板块名 | None, 排序层级)。层级：0=你的兴趣板块，1=非科技板块，2=科技板块。"""
    title = item.get('title', '')
    low = title.lower()
    src = item.get('source', '')

    for bw in (prefs.get('blocked') or []):
        if bw and bw in title:
            return None, -1

    interest = set(prefs.get('interest') or [])
    for kw in (prefs.get('extra_keywords') or []):
        if kw and kw.lower() in low:
            return (prefs.get('extra_section') or '全网热搜'), 0

    cats = _prefs_cats(prefs)

    def _tier(name):
        return 0 if name in interest else (2 if name in TECH_SECTIONS else 1)

    def _kws(name):
        for n, c in cats:
            if n == name:
                return c.get('keywords') or []
        return []

    # 全板块关键词匹配：科技优先（避免「英伟达芯片」被时政/科学板块抢走），
    # 其余按配置顺序；来源与板块不符的跳过
    for name, cfg in sorted(cats, key=lambda nc: 0 if nc[0] in TECH_SECTIONS else 1):
        if name not in TECH_SECTIONS and cfg.get('only_sources') is None \
                and SECTION_SOURCES.get(name) and src and src not in SECTION_SOURCES[name]:
            continue
        for kw in (cfg.get('keywords') or []):
            if kw and kw.lower() in low:
                return name, _tier(name)

    # 没命中关键词：按来源栏目挂靠（百度国际→时政、百度民生→本地）
    for name, srcs in EXTRA_SOURCES.items():
        if src in srcs:
            return name, _tier(name)

    return None, 1


def _cat_rank(x, name):
    """板块内排序：同栏目来源 > 其他聚合源 > 单条热搜，其次按热度。"""
    src = x.get('source') or ''
    return (HUBS.get(src) != name, HUBS.get(src) is None, -int(x.get('hot') or 0))


def _tech_budget(prefs, cats):
    """科技板块总条数预算（AI/大模型 + 科技/大厂），默认 3 条。"""
    try:
        mb = int(prefs.get('max_tech_items', 3))
    except Exception:
        mb = 3
    total_quota = sum(int(c.get('quota', 0) or 0) for n, c in cats if n in TECH_SECTIONS)
    return max(0, min(mb, total_quota))


def _dedupe(items):
    seen, out = [], []
    for it in items:
        t = re.sub(r'\s', '', it['title'])
        if any(t in s or s in t for s in seen):
            continue
        seen.append(t)
        out.append(it)
    return out


def build_news():
    cached = _cached('hot_news')
    if cached:
        return cached

    prefs = _load_prefs()
    interest = list(prefs.get('interest') or [])
    cats = _prefs_cats(prefs)
    items, failed = _collect_news(prefs)
    if not items:
        return ('⚠️ 所有新闻源暂时不可用（可能被限流）。稍后再试，或让 iris 用 Iris Scout 的 '
                'fetch_rss / 联网搜索获取今日热点作为替代。')

    quiet = set(prefs.get('quiet_sources') or [])
    pool, seen = [], set()
    for it in items:
        # 屏蔽词 / 分类（None = 进全网热搜兜底池）
        sec, tier = _classify(it, prefs)
        if tier < 0:
            continue
        it = dict(it)
        it['section'], it['tier'] = sec, tier
        key = re.sub(r'\s', '', it.get('title', ''))
        if not key or any(key in s or s in key for s in seen):
            continue
        seen.add(key)
        pool.append(it)

    if not pool:
        return ('今日抓到的条目都被屏蔽词过滤了。可以对我说「调整新闻偏好」放宽屏蔽词，'
                '或说「取消屏蔽娱乐圈」。')

    # 先按层级（兴趣 > 非科技 > 科技）再按热度排序
    pool.sort(key=lambda x: (x.get('tier', 9), -int(x.get('hot') or 0)))

    # ---------- 按板块配额逐块取材 ----------
    tech_budget = _tech_budget(prefs, cats)
    taken, sec_pick, tech_used = set(), {}, 0
    for name, cfg in cats:
        quota = int(cfg.get('quota', 2) or 0)
        if quota <= 0:
            continue
        if name in TECH_SECTIONS:
            quota = max(0, min(quota, tech_budget - tech_used))
        pool2 = [x for x in pool if x.get('section') == name]
        if pool2:
            bag = sorted(pool2, key=lambda x: _cat_rank(x, name))
        else:
            # 本板块今日无命中 → 用挂靠来源或板块归属明确的非科技内容补位
            bag = [x for x in pool if id(x) not in taken
                   and x.get('section') not in TECH_SECTIONS
                   and (x.get('section') in EXTRA_SOURCES.get(name, ('',)))]
            bag.sort(key=lambda x: (x.get('tier', 9), -int(x.get('hot') or 0)))
        picked = []
        for x in bag:
            if id(x) in taken or len(picked) >= quota:
                continue
            if x.get('section') in TECH_SECTIONS and tech_used >= tech_budget:
                continue
            taken.add(id(x))
            picked.append(x)
            if x.get('section') in TECH_SECTIONS:
                tech_used += 1
        if picked:
            sec_pick[name] = picked

    # ---------- 全网热搜兜底（只放无明确板块归属的条目，兴趣板块优先） ----------
    hot_quota = int(prefs.get('hot_items', 3) or 0)
    hot_pool = [x for x in pool if id(x) not in taken
                and x.get('section') != '全网热搜'
                and x.get('source') not in quiet
                and x.get('tier', 9) <= 1]
    hot_general = sorted(hot_pool, key=lambda x: (x.get('tier', 9) == 0,
                                                  -int(x.get('hot') or 0)))[:hot_quota]

    # ---------- 渲染 ----------
    cats_dict = dict(cats)
    def _fmt(x):
        src = x.get('source') or ''
        # 聚合型来源名（百度/60s）不加括号，免得每行都很长
        return x['title'] if src in ('', '百度', '60s') else f'{x["title"]}（{src}）'

    lines = [f'## 📰 今日热点 · {datetime.date.today().strftime("%Y-%m-%d")}', '']
    if prefs.get('show_weather', True):
        try:
            wc = build_weather()
            if wc and not wc.startswith('⚠️'):
                lines += [wc, '']
        except Exception:
            pass
    # 输出顺序：兴趣板块 → 其他非科技板块 → 全网热搜 → 科技垫底（视觉上也不占版面）
    order = ([n for n, c in cats if n in interest]
             + [n for n, c in cats if n not in interest and n not in TECH_SECTIONS]
             + [n for n, c in cats if n in TECH_SECTIONS])
    for name in order:
        picked = sec_pick.get(name) or []
        if not picked:
            continue
        cfg = dict(cats_dict.get(name) or {})
        icon = cfg.get('icon') or '📌'
        tag = '⭐' if name in interest else ''
        lines.append(f'{icon} {name}{tag}')
        lines += [f'{i}. {_fmt(x)}' for i, x in enumerate(picked, 1)]
        lines.append('')
    if hot_general:
        lines.append('🔥 全网热搜')
        lines += [f'{i}. {_fmt(x)}' for i, x in enumerate(hot_general, 1)]
        lines.append('')

    if failed:
        lines.append(f'（今日 {len(failed)} 个源暂时不可用：{"、".join(failed)}）')
        lines.append('')

    shown = sum(len(v) for v in sec_pick.values()) + len(hot_general)
    if shown == 0:
        lines.append('今日没有匹配到偏好的新闻，可以对我说「调整新闻偏好」来优化。')

    lines += ['', '【系统指令·请勿转述】以上是纯新闻列表。请原样转发给用户：'
              '不要对任何新闻发表看法、点评、总结或延伸解读，'
              '不要加"值得关注""你怎么看"之类的按语，不要额外推荐相关话题。']
    result = '\n'.join(lines)
    _set_cache('hot_news', result, 600)
    return result


def build_morning_report(date_str=''):
    parts = [build_schedule(date_str)]
    try:
        w = build_weather()
        if w and not w.startswith('⚠️'):
            parts += ['', w]
    except Exception:
        pass
    parts += ['', '---', '', build_news()]
    return '\n'.join(parts)


# ============================================================
# 手动触发指令解析
# ============================================================

USAGE = """📖 可用指令：
• 课表 / 今日课表 —— 今天的课（含上课状态）
• 明天课表 / 后天课表 / 周三课表 —— 指定日期
• 本周课表 —— 一周总览
• 下一节 —— 下一节课+倒计时
• 新闻 / 热点 —— 今日热点新闻
• 早报 —— 课表+新闻完整版
• 新闻偏好 —— 查看当前偏好
（想调整偏好直接说，比如「多关注考研」「时政多两条」「科技少一点」「屏蔽汽车」）"""

# 各板块的闲聊式说法 → 板块名（用于自然语言调偏好）
SECTION_ALIASES = {
    '时政/国际': ['时政', '国际', '新闻联播', '大事', '政策', '天下'],
    '科学/健康': ['科学', '科普', '健康', '医学', '科研', '太空', '航天'],
    '校园/教育': ['校园', '教育', '考研', '升学', '就业', '学校', '考试'],
    '本地/生活': ['本地', '生活', '同城', '城市', '天气', '出行'],
    'AI/大模型': ['ai', 'AI', '大模型', '人工智能'],
    '科技/大厂': ['科技', '数码', '互联网', '大厂'],
}


def handle_command_logic(text):
    t = (text or '').strip()
    today = datetime.date.today()

    if re.search(r'图片|发.*课表.*微信|课表图', t) and re.search(r'课表|图', t):
        try:
            import schedule_image
            path = schedule_image.render_week_image()
            return (schedule_quip() + '\n'
                    '【系统指令】图片在 ' + path + '，请展示或发送给用户。'
                    '如需对用户说话，只使用上面第一句原句，不要改写、不要加长。')
        except Exception as e:
            return f'课表图片生成失败: {e}'
    if re.search(r'帮助|菜单|指令|怎么用|help', t, re.I):
        return USAGE
    if re.search(r'新闻偏好|偏好设置', t):
        return show_news_prefs()
    # 娱乐圈屏蔽开关
    if re.search(r'取消屏蔽|不屏蔽|别屏蔽|放开屏蔽', t) and re.search(r'娱乐|明星|八卦', t):
        prefs = _load_prefs()
        prefs['blocked'] = []
        _save_prefs(prefs)
        _cache.pop('hot_news', None)
        return '✅ 已取消娱乐圈屏蔽（热搜里出现什么就推什么）\n\n' + show_news_prefs()
    if re.search(r'(?<!取消)(?<!不)(?<!别)屏蔽娱乐|不要娱乐|别推娱乐', t):
        prefs = _load_prefs()
        from_blocked = ['出轨', '塌房', '绯闻', '恋情', '八卦', '狗仔', '偷拍', '耍大牌']
        bl = prefs.setdefault('blocked', [])
        for w in from_blocked:
            if w not in bl:
                bl.append(w)
        _save_prefs(prefs)
        _cache.pop('hot_news', None)
        return '✅ 已恢复屏蔽娱乐圈八卦（保留影视/音乐作品类新闻）\n\n' + show_news_prefs()
    if re.search(r'科技(少|减|别太多|太多)|少点科技|不要太科技|多来点别的', t):
        prefs = _load_prefs()
        cur = int(prefs.get('max_tech_items', 3) or 0)
        prefs['max_tech_items'] = max(0, cur - 1)
        _save_prefs(prefs)
        _cache.pop('hot_news', None)
        return f"✅ 科技类上限已降到 {prefs['max_tech_items']} 条\n\n" + show_news_prefs()
    if re.search(r'科技多|多点科技|多来点科技|科技加', t):
        prefs = _load_prefs()
        cur = int(prefs.get('max_tech_items', 3) or 0)
        prefs['max_tech_items'] = min(10, cur + 1)
        _save_prefs(prefs)
        _cache.pop('hot_news', None)
        return f"✅ 科技类上限已提到 {prefs['max_tech_items']} 条\n\n" + show_news_prefs()

    # 自然语言调偏好（只在消息带「偏好/关注/屏蔽」等词时才解析，避免误伤普通问句）
    if re.search(r'多关注|多来点|多点|想看更?多|关注一下|加上|加个|偏好', t):
        m_add = re.search(r'(?:多关注|多来点|多点|想看更?多|关注一下|加上|加个|偏好)\s*([^\s,，。！？!?、]{1,12})', t)
        if m_add:
            word = m_add.group(1).strip()
            prefs = _load_prefs()
            hit = next((sec for sec, al in SECTION_ALIASES.items()
                        if any(a and a in word for a in al)), None)
            if hit:
                interest = prefs.setdefault('interest', [])
                if hit not in interest:
                    interest.append(hit)
                cats = prefs.get('categories') or {}
                if hit in cats:
                    cats[hit]['quota'] = int(cats[hit].get('quota', 2) or 2) + 1
                _save_prefs(prefs)
                _cache.pop('hot_news', None)
                return f'✅ 已把「{hit}」设为兴趣板块，并加一条配额\n\n' + show_news_prefs()
            extra = prefs.setdefault('extra_keywords', [])
            if word and word not in extra:
                extra.append(word)
            _save_prefs(prefs)
            _cache.pop('hot_news', None)
            return f'✅ 已把「{word}」加入重点关注（命中会排在最前面）\n\n' + show_news_prefs()

    if re.search(r'屏蔽|不想看|别推|不要看', t):
        m_blk = re.search(r'(?:屏蔽|不想看|别推|不要看)\s*([^\s,，。！？!?、]{1,12})', t)
        if m_blk:
            word = m_blk.group(1).strip()
            prefs = _load_prefs()
            bl = prefs.setdefault('blocked', [])
            if word and word not in bl:
                bl.append(word)
            _save_prefs(prefs)
            _cache.pop('hot_news', None)
            return f'✅ 已屏蔽「{word}」\n\n' + show_news_prefs()

    if re.search(r'天气|气候|气温|下雨|降温|带伞|冷不冷|热不热', t):
        return build_weather()
    if re.search(r'早报|晨报|morning', t, re.I):
        return build_morning_report('')
    if re.search(r'新闻|热点|热搜|资讯', t):
        return build_news()
    if re.search(r'本周|这周|周表|整周', t):
        return build_week_schedule()
    if re.search(r'下一节|下节|下节课', t):
        return build_next_course()
    m = re.search(r'周([一二三四五六日天1-7])', t)
    if m and re.search(r'课|表|有什么', t):
        wd = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '日': 7, '天': 7,
              '1': 1, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7}[m.group(1)]
        delta = wd - today.isoweekday()
        return build_schedule((today + datetime.timedelta(days=delta)).isoformat())
    if re.search(r'明天', t):
        return build_schedule((today + datetime.timedelta(days=1)).isoformat())
    if re.search(r'后天', t):
        return build_schedule((today + datetime.timedelta(days=2)).isoformat())
    if re.search(r'昨天', t):
        return build_schedule((today - datetime.timedelta(days=1)).isoformat())
    if re.search(r'课表|有什么课|今天.*课|课程', t):
        return build_schedule('')
    return f'没看懂「{t}」😅\n\n{USAGE}'


def show_news_prefs():
    prefs = _load_prefs()
    cats = _prefs_cats(prefs)
    interest = list(prefs.get('interest') or [])
    lines = ['## ⚙️ 当前新闻偏好', '']
    lines.append('**板块配额**（⭐ = 你的兴趣板块，优先排前）：')
    for name, cfg in cats:
        icon = cfg.get('icon') or '📌'
        q = int(cfg.get('quota', 2) or 0)
        star = '⭐' if name in interest else ''
        lines.append(f'  {icon} {name}{star}：{q} 条 / {len(cfg.get("keywords") or [])} 个关键词')
    lines.append(f"**科技类上限**：{prefs.get('max_tech_items', 3)} 条（AI/大模型 + 科技/大厂 合计）")
    lines.append(f"**全网热搜兜底**：{prefs.get('hot_items', 3)} 条")
    lines.append(f"**屏蔽词**：{'、'.join(prefs.get('blocked') or []) or '无'}")
    lines.append(f"**额外关注词**：{'、'.join(prefs.get('extra_keywords') or []) or '无'}")
    src = [k for k, on in (prefs.get('sources') or {}).items() if on]
    lines.append(f"**启用源**：{'、'.join(src)}")
    quiet = list(prefs.get('quiet_sources') or [])
    if quiet:
        lines.append(f"**不进热搜的来源**：{'、'.join(quiet)}")
    lines.append('')
    lines.append('调整方式：直接告诉我，例如「多关注游戏」「屏蔽汽车」「科技少一点」'
                 '「时政多两条」「本地新闻别放热搜」')
    return '\n'.join(lines)


# ============================================================
# MCP 工具注册
# ============================================================

@mcp.tool()
def get_today_schedule(date: str = '') -> str:
    """获取课表（节假日感知、上课状态标记、下一节倒计时、明日预告）。
    date 为 YYYY-MM-DD，留空表示今天。"""
    try:
        return build_schedule(date)
    except Exception as e:
        return f'课表生成失败: {e}'


@mcp.tool()
def get_next_course() -> str:
    """获取下一节课（含距上课/下课倒计时），以及当前是否正在上课。"""
    try:
        return build_next_course()
    except Exception as e:
        return f'查询失败: {e}'


@mcp.tool()
def get_week_schedule() -> str:
    """获取本周课表总览（周一到周日每天的课程紧凑列表）。"""
    try:
        return build_week_schedule()
    except Exception as e:
        return f'查询失败: {e}'


@mcp.tool()
def get_weather_climate() -> str:
    """获取本地（北京）近期总体气候趋势：未来一周气温区间、天气概况、降水天数、升温/降温趋势。
    用于回答「最近天气怎么样」「这几天冷不冷」「要带伞吗」这类问题；只讲趋势，不播报逐日天气。
    ⚠️ 原样转发即可，不要对天气发表感慨或延伸建议。"""
    try:
        return build_weather()
    except Exception as e:
        return f'气候获取失败: {e}'


@mcp.tool()
def get_hot_news() -> str:
    """获取今日热点新闻。多源聚合（澎湃/百度各榜/60s系IT资讯·微博·知乎·抖音/B站全站），
    按 news_prefs.json 的板块配额输出：兴趣板块（时政/国际、科学/健康、校园/教育、本地/生活）
    在前，全网热搜兜底，科技类（AI/大模型 + 科技/大厂）合计最多 3 条；
    开头会附一段「近期总体气候」趋势（可用 show_weather: false 关闭）。
    娱乐圈只屏蔽八卦绯闻，保留影视/音乐作品类新闻。
    ⚠️ 只负责搜集与罗列：将结果原样转发给用户，不要对新闻/天气内容发表任何看法、
    点评、总结或延伸解读。"""
    try:
        return build_news()
    except Exception as e:
        return f'新闻获取失败: {e}'


@mcp.tool()
def get_morning_report(date: str = '') -> str:
    """生成完整每日早报：今日课表 + 近期气候趋势 + 偏好定制的今日热点。date 为 YYYY-MM-DD，留空表示今天。
    ⚠️ 新闻与天气部分只搜集不评论：原样转发，不要发表看法、点评或总结。"""
    try:
        return build_morning_report(date)
    except Exception as e:
        return f'早报生成失败: {e}'


@mcp.tool()
def handle_command(text: str):
    """【手动触发入口】把用户从微信发来的消息原文传进来，自动识别意图并返回内容。
    课表类问题（课表/今天有什么课/明天课表/周X课表/本周课表）：
    服务器会把课表图片直接推送到用户微信，并返回一句短文案——把这句话原样发给用户即可，
    不要改写、不要加长、不要再说"已发送"，图片不需要你转发。
    其他：下一节/新闻/热点/早报/新闻偏好/帮助 → 返回文字，原样回复即可；
    偏好类指令（多关注X、屏蔽X、科技少一点、取消屏蔽娱乐圈）会直接改偏好并返回结果；
    新闻内容只搜集不评论，不要发表看法、点评或总结。"""
    try:
        t = (text or '').strip()
        today = datetime.date.today()

        # 课表类意图 → 直接发图（高亮跟随被问的日期）
        if re.search(r'课表|有什么课|今天.{0,4}课|明天.{0,4}课|后天.{0,4}课|课程安排', t) \
                and not re.search(r'文字|文本|不要图', t):
            import schedule_image
            from mcp.server.fastmcp import Image as _MCPImage
            target = today
            m_ = re.search(r'周([一二三四五六日天1-7])', t)
            if m_:
                wd = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '日': 7, '天': 7,
                      '1': 1, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7}[m_.group(1)]
                target = today + datetime.timedelta(days=wd - today.isoweekday())
            elif re.search(r'明天', t):
                target = today + datetime.timedelta(days=1)
            elif re.search(r'后天', t):
                target = today + datetime.timedelta(days=2)
            img_path = schedule_image.render_week_image(ref_date=target)
            # 优先由服务器直接推送图片到微信（ilink 通道，不依赖客户端转发图片）；
            # 无活跃微信会话时推送会失败，回退为返回图片内容由客户端展示
            try:
                push = json.loads(_wechat_send_image(img_path))
                if push.get('success'):
                    return push.get('reply') or schedule_quip()
            except Exception:
                pass
            return _MCPImage(path=img_path)

        return handle_command_logic(t)
    except Exception as e:
        return f'指令处理失败: {e}'


@mcp.tool()
def get_news_prefs() -> str:
    """查看当前新闻偏好配置（板块配额、科技类上限、屏蔽词、启用的源）。"""
    return show_news_prefs()


@mcp.tool()
def set_news_prefs(add_keywords: str = '', remove_keywords: str = '',
                   add_blocked: str = '', remove_blocked: str = '',
                   interest_sections: str = '', uninterested_sections: str = '',
                   section_quotas: str = '', max_tech_items: int = -1) -> str:
    """调整新闻偏好。逗号分隔（中英文逗号、顿号均可）：
    add_keywords 追加重点关注词（如「考研,四六级」，命中后排最前）；
    remove_keywords 移除关注词；add_blocked 追加屏蔽词；remove_blocked 移除屏蔽词；
    interest_sections 标记兴趣板块（如「时政/国际,科学/健康」，会排到最前面）；
    uninterested_sections 取消兴趣标记；
    section_quotas 调整板块条数，格式「板块名=条数」，如「时政/国际=4,科技/大厂=1」；
    max_tech_items 科技类（AI/大模型+科技/大厂）总条数上限，-1 表示不改。"""
    prefs = _load_prefs()
    extra = prefs.setdefault('extra_keywords', [])
    blocked = prefs.setdefault('blocked', [])
    interest = prefs.setdefault('interest', [])

    def split(s):
        return [w.strip() for w in re.split(r'[,，、;；]', s or '') if w.strip()]

    for w in split(add_keywords):
        if w not in extra:
            extra.append(w)
    for w in split(remove_keywords):
        if w in extra:
            extra.remove(w)
    for w in split(add_blocked):
        if w not in blocked:
            blocked.append(w)
    for w in split(remove_blocked):
        if w in blocked:
            blocked.remove(w)

    cats = prefs.get('categories') or {}
    for name in split(interest_sections):
        if name and name not in interest:
            interest.append(name)
    for name in split(uninterested_sections):
        if name in interest:
            interest.remove(name)

    def norm_sec(s):
        """板块名容错：「科技」按「大厂/科技」处理，去掉空格。"""
        return (s or '').replace('科技', '大厂').replace(' ', '').strip()

    for pair in split(section_quotas):
        if '=' not in pair and '：' not in pair:
            continue
        k, v = re.split(r'[=：]', pair, maxsplit=1)
        k, v = k.strip(), v.strip()
        try:
            q = max(0, int(v))
        except Exception:
            continue
        hit = None
        for name in cats:
            if k == name or k in name or norm_sec(k) in name:
                hit = name
                break
        if hit is None:
            for name in cats:
                if any(tok and tok in name for tok in re.split(r'[/／]', k)):
                    hit = name
                    break
        if hit:
            cats[hit]['quota'] = q
    if cats:
        prefs['categories'] = cats

    try:
        mt = int(max_tech_items)
    except Exception:
        mt = -1
    if mt >= 0:
        prefs['max_tech_items'] = mt

    _save_prefs(prefs)
    _cache.pop('hot_news', None)
    return '✅ 偏好已更新：\n' + show_news_prefs()


@mcp.tool()
def get_schedule_image():
    """生成超级课程表风格的本周彩色格子课表图片（PNG 图片内容直接返回）。
    当用户要求「课表图片」「发一张课表图」时使用。
    ⚠️ 返回的图片就是给用户的完整回复：请直接展示/转发图片；如需说话，
    只说一句简短自然的口语，不要汇报"已发送/已生成"。"""
    try:
        from mcp.server.fastmcp import Image as _MCPImage
        import schedule_image
        return _MCPImage(path=schedule_image.render_week_image())
    except Exception as e:
        return f'课表图片生成失败: {e}'


@mcp.tool()
def send_schedule_image_to_wechat() -> str:
    """渲染本周课表图片并直接发送到用户的微信（通过 Cherry Studio 微信频道的 ilink 通道）。
    成功后微信里会收到一张彩色格子课表图。
    ⚠️ 调用成功后如需对用户说话，只使用返回值中 reply 字段的原句，不要改写、不要加长。"""
    try:
        import schedule_image
        png = schedule_image.render_week_image()
        return _wechat_send_image(png)
    except Exception as e:
        return json.dumps({'success': False, 'error': str(e)}, ensure_ascii=False)


# ============================================================
# 微信图片直发（移植自 voicebox_wechat_mcp 的 ilink CDN 上传逻辑）
# ============================================================

ILINK_BASE_URL = "https://ilinkai.weixin.qq.com"
ILINK_CHANNEL_DIR = os.environ.get('ILINK_CHANNEL_DIR') or os.path.expanduser("~/AppData/Roaming/CherryStudio/Data/Channels")
_ILINK_TOKEN = ''
_ILINK_UID = ''


def _init_ilink():
    global _ILINK_TOKEN, _ILINK_UID
    if _ILINK_TOKEN and _ILINK_UID:
        return
    import glob as _glob
    files = sorted(_glob.glob(os.path.join(ILINK_CHANNEL_DIR, 'weixin_bot_*.json')),
                   key=os.path.getmtime, reverse=True)
    for f in files:
        try:
            with open(f, encoding='utf-8') as fh:
                cfg = json.load(fh)
            tok, uid = cfg.get('token', ''), cfg.get('userId', '')
            if tok and uid:
                _ILINK_TOKEN, _ILINK_UID = tok, uid
                return
        except Exception:
            continue
    raise RuntimeError('没有可用的微信 bot token，请确认 Cherry Studio 微信频道已连接')


def _ilink_headers():
    import base64 as _b64, random as _rnd
    _init_ilink()
    return {
        'Content-Type': 'application/json',
        'AuthorizationType': 'ilink_bot_token',
        'Authorization': f'Bearer {_ILINK_TOKEN}',
        'X-WECHAT-UIN': _b64.b64encode(str(_rnd.getrandbits(32)).encode('ascii')).decode('ascii'),
        'iLink-App-Id': 'bot',
        'iLink-App-ClientVersion': str(((2 & 0xFF) << 16) | ((4 & 0xFF) << 8) | (3 & 0xFF)),
    }


def _ilink_base_info():
    return {'channel_version': '2.4.3', 'bot_agent': 'OpenClaw'}


def _get_context_token():
    import glob as _glob
    for f in sorted(_glob.glob(os.path.join(ILINK_CHANNEL_DIR, 'weixin_bot_*.context-tokens.json'))):
        try:
            with open(f, encoding='utf-8') as fh:
                d = json.load(fh)
            tok = d.get(_ILINK_UID)
            if tok:
                return tok
        except Exception:
            continue
    return None


def _wechat_send_image(png_path):
    """CDN 上传 PNG + 发送图片消息"""
    import uuid, hashlib, base64 as _b64
    import requests as _req
    from Crypto.Cipher import AES as _AES

    _init_ilink()

    with open(png_path, 'rb') as f:
        plaintext = f.read()
    rawsize = len(plaintext)
    rawfilemd5 = hashlib.md5(plaintext).hexdigest()
    cipher_size = ((rawsize // 16) + 1) * 16
    filekey = uuid.uuid4().hex[:32]
    aeskey = os.urandom(16)

    # 1. 申请上传地址（media_type=1 图片）
    resp = _req.post(f'{ILINK_BASE_URL}/ilink/bot/getuploadurl',
                     headers=_ilink_headers(),
                     json={'filekey': filekey, 'media_type': 1, 'to_user_id': _ILINK_UID,
                           'rawsize': rawsize, 'rawfilemd5': rawfilemd5,
                           'filesize': cipher_size, 'no_need_thumb': True,
                           'aeskey': aeskey.hex(), 'base_info': _ilink_base_info()},
                     timeout=30)
    data = resp.json() if resp.status_code == 200 else {}
    if data.get('ret') not in (None, 0):
        return json.dumps({'success': False, 'step': 'getuploadurl', 'detail': data}, ensure_ascii=False)
    upload_url = (data.get('upload_full_url') or '').strip()
    if not upload_url:
        return json.dumps({'success': False, 'step': 'getuploadurl', 'detail': '无 upload_full_url'}, ensure_ascii=False)

    # 2. AES-ECB 加密上传
    pad_len = 16 - (rawsize % 16)
    ciphertext = _AES.new(aeskey, _AES.MODE_ECB).encrypt(plaintext + bytes([pad_len] * pad_len))
    cdn = _req.post(upload_url, headers={'Content-Type': 'application/octet-stream'},
                    data=ciphertext, timeout=120)
    enc_param = cdn.headers.get('x-encrypted-param')
    if cdn.status_code != 200 or not enc_param:
        return json.dumps({'success': False, 'step': 'cdn_upload',
                           'detail': f'HTTP {cdn.status_code}'}, ensure_ascii=False)

    # 3. 发送图片消息（type=2 image_item），带 context_token，ret=-2 时去掉重试
    def build_msg(context_token=None):
        m_ = {
            'msg': {
                'from_user_id': '', 'to_user_id': _ILINK_UID,
                'client_id': f'schedule-mcp-{uuid.uuid4()}',
                'message_type': 2, 'message_state': 2,
                'item_list': [{
                    'type': 2,
                    'image_item': {
                        'media': {
                            'encrypt_query_param': enc_param,
                            'aes_key': _b64.b64encode(aeskey.hex().encode('ascii')).decode('utf-8'),
                            'encrypt_type': 1,
                        },
                        'mid_size': cipher_size,
                    },
                }],
            },
            'base_info': _ilink_base_info(),
        }
        if context_token:
            m_['msg']['context_token'] = context_token
        return m_

    result = {}
    for token in (_get_context_token(), None):
        payload = build_msg(context_token=token)
        resp = _req.post(f'{ILINK_BASE_URL}/ilink/bot/sendmessage',
                         headers=_ilink_headers(), json=payload, timeout=60)
        result = resp.json() if resp.status_code == 200 else {'ret': -99, 'http': resp.status_code}
        if result.get('ret') != -2:
            break
    if result.get('ret') in (None, 0):
        return json.dumps({'success': True,
                           'reply': schedule_quip(),
                           'instruction': '发送成功。如需回复用户，直接使用 reply 字段的原句，不要改写、不要加长。'},
                          ensure_ascii=False)
    return json.dumps({'success': False, 'step': 'sendmessage', 'detail': result}, ensure_ascii=False)


if __name__ == '__main__':
    mcp.run()  # stdio
