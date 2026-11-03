#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
课表图片渲染器 —— 与网页版一致的米白细线周课表
输出 PNG，供 MCP 工具调用。
"""
import os, sys, datetime, hashlib
from itertools import combinations

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'class-schedule')))
import today_schedule as ts  # noqa: E402

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

# ---- 布局常量 ----
W = 860
HEADER_H = 100         # 顶部星期/日期行
TITLE_H = 88           # 标题行
LEFT_W = 76            # 左侧节次列
ROW_H = 205            # 每个大节行高
N_PERIODS = 6          # 6 个大节
PAD = 18
COL_GAP = 1            # 用细线分隔，不用间隙

# 地点前缀去掉哪些词（各校命名不同，逗号分隔；默认不去）
_LOCATION_STRIP = [p.strip() for p in
                   (os.environ.get('SCHEDULE_LOCATION_STRIP') or '').split(',') if p.strip()]

FONT_PATH = os.environ.get('SCHEDULE_FONT') or 'C:/Windows/Fonts/msyh.ttc'
FONT_BOLD_PATH = os.environ.get('SCHEDULE_FONT_BOLD') or 'C:/Windows/Fonts/msyhbd.ttc'

# 与 docs/index.html 同一套配色：米白底、近黑字、低饱和课程色
PALETTE = [
    (122, 96, 84),    # 赭
    (96, 110, 84),    # 苔绿
    (84, 96, 122),    # 灰蓝
    (122, 106, 68),   # 土黄
    (100, 82, 100),   # 灰紫
    (68, 100, 100),   # 青灰
    (118, 84, 96),    # 酒红
    (84, 100, 68),    # 橄榄
]

BG = (232, 229, 225)         # #e8e5e1 米白
PANEL = (244, 242, 238)      # #f4f2ee 面板
GRID_LINE = (205, 199, 186)  # #cdc7ba 细线
TEXT_DARK = (21, 23, 19)     # #151713 近黑
TEXT_GRAY = (143, 138, 128)  # #8f8a80 次要文字
TODAY_BG = (222, 215, 200)   # #ded7c8 今日列
ACCENT = (148, 107, 60)      # #946b3c 强调棕


def _mix(c1, c2, t):
    """c1 向 c2 混合 t（0~1）"""
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))

DAY_NAMES = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
BIG_PERIOD_TIMES = ['08:30\n10:10', '10:30\n12:10', '14:30\n16:10',
                    '16:30\n18:10', '19:00\n20:40', '21:00\n22:40']


def _font(size, bold=False):
    path = FONT_BOLD_PATH if bold and os.path.exists(FONT_BOLD_PATH) else FONT_PATH
    return ImageFont.truetype(path, size)


def _color_for(name):
    h = int(hashlib.md5(name.encode('utf-8')).hexdigest(), 16)
    return PALETTE[h % len(PALETTE)]


def _wrap_cjk(text, font, max_w):
    """按像素宽度对中英混排文本换行"""
    lines, cur = [], ''
    for ch in text:
        if ch == '\n':
            lines.append(cur)
            cur = ''
            continue
        if font.getlength(cur + ch) > max_w and cur:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    return lines


# 只用来避免从常见课程词素中间断行，不依赖外部分词库。
_COURSE_TERMS = (
    '计算机', '人工智能', '大学生', '操作系统', '组成', '原理', '实验',
    '算法', '设计', '分析', '移动', '应用', '开发', '基础', '编译',
    '仿真', '专业', '英语', '就业', '指导',
)


def _wrap_title(text, font, max_w):
    """短课名保持一行；长课名按宽度候选折行，并优先保留课程词素。"""
    if font.getlength(text) <= max_w:
        return [text]
    if not (5 <= len(text) <= 10 and all('\u4e00' <= ch <= '\u9fff' for ch in text)):
        return _wrap_cjk(text, font, max_w)

    n_lines = 2 if len(text) <= 8 else 3
    best = None
    for cuts in combinations(range(1, len(text)), n_lines - 1):
        bounds = (0,) + cuts + (len(text),)
        lines = [text[a:b] for a, b in zip(bounds, bounds[1:])]
        if any(len(line) < 2 for line in lines):
            continue
        widths = [font.getlength(line) for line in lines]
        if any(width > max_w for width in widths):
            continue
        broken = sum(
            any(start < cut < start + len(term) for cut in cuts)
            for term in _COURSE_TERMS
            for start in range(len(text) - len(term) + 1)
            if text.startswith(term, start)
        )
        target = sum(widths) / n_lines
        balance = sum((width - target) ** 2 for width in widths)
        # 同等条件下让末行不长于首行，避免视觉重心向右下坠。
        trailing = max(0, widths[-1] - widths[0])
        score = (broken, balance, trailing, cuts)
        if best is None or score < best[0]:
            best = (score, lines)
    return best[1] if best else _wrap_cjk(text, font, max_w)


def _draw_block(draw, xy, color, title, sub_lines, radius=0):
    """白底、3px 左色条；标题与说明分组后在块内居中。"""
    x0, y0, x1, y1 = xy
    draw.rectangle(xy, fill=(250, 248, 244))
    draw.rectangle((x0, y0, x0 + 2, y1), fill=color)

    tx = x0 + 12
    max_w = x1 - tx - 9
    f_title = _font(21, bold=True)
    f_sub = _font(16)

    title_lines = _wrap_title(title, f_title, max_w)
    sub_rows = [ln for sub in sub_lines for ln in _wrap_cjk(sub, f_sub, max_w)]
    title_step, sub_step, group_gap = 28, 21, 8
    total_h = len(title_lines) * title_step + group_gap + len(sub_rows) * sub_step
    y = y0 + ((y1 - y0) - total_h) / 2

    for line in title_lines:
        draw.text((tx, y), line, font=f_title, fill=TEXT_DARK, anchor='lt')
        y += title_step
    y += group_gap
    for line in sub_rows:
        draw.text((tx, y), line, font=f_sub, fill=TEXT_GRAY, anchor='lt')
        y += sub_step


def render_week_image(out_path=None, ref_date=None):
    """渲染当前周课表 PNG，返回文件路径"""
    # 两个日期别混用：anchor 决定画哪一周，real_today 只用来标「今天」那一列。
    # 混成一个是 bug——看下周的图时，下周二会被错误地标成今天。
    real_today = datetime.date.today()
    anchor = ref_date or real_today
    monday = anchor - datetime.timedelta(days=anchor.isoweekday() - 1)
    week = ts.current_week(anchor)
    today = real_today

    import json
    with open(ts.COURSES_JSON, 'r', encoding='utf-8') as f:
        all_courses = json.load(f)['courses']
    active = [c for c in all_courses if ts.course_active(c, week)]

    # 裁剪底部无课的大节（至少保留 4 个）
    max_bp = 3
    for c in active:
        max_bp = max(max_bp, (c['endPeriod'] - 1) // 2)
    n_rows = max_bp + 1

    H = TITLE_H + HEADER_H + n_rows * ROW_H + PAD
    img = Image.new('RGB', (W, H), BG)
    draw = ImageDraw.Draw(img)

    # 整体直角面板
    draw.rectangle((8, TITLE_H - 6, W - 8, H - 8), fill=PANEL)

    col_w = (W - LEFT_W - PAD * 2 - COL_GAP * 6) / 7

    # ---- 标题（对齐 docs/index.html：左上小标签 + 左标题 + 右日期）----
    f_kick = _font(12)
    draw.text((PAD + 6, 14), f'档案 / WEEK  {week:02d}', font=f_kick, fill=TEXT_GRAY,
              anchor='lt')
    f_title = _font(30, bold=True)
    draw.text((PAD + 6, 32), f'第 {week} 周', font=f_title, fill=TEXT_DARK, anchor='lt')
    f_sub = _font(16)
    sub = (f"{monday.strftime('%Y-%m-%d')} ~ "
           f"{(monday + datetime.timedelta(days=6)).strftime('%Y-%m-%d')}")
    sw = f_sub.getlength(sub)
    draw.text((W - PAD - 6 - sw, 43), sub, font=f_sub, fill=TEXT_GRAY, anchor='lt')

    y0 = TITLE_H

    # ---- 表头 ----
    f_day = _font(19, bold=True)
    f_date = _font(14)
    for i in range(7):
        day = monday + datetime.timedelta(days=i)
        x = LEFT_W + PAD + i * (col_w + COL_GAP)
        is_today = (day == today)
        if is_today:
            draw.rectangle((x, y0 + 8, x + col_w, y0 + HEADER_H - 8), fill=TODAY_BG)
        name = DAY_NAMES[i]
        nw = f_day.getlength(name)
        draw.text((x + (col_w - nw) / 2, y0 + 20), name, font=f_day,
                  fill=ACCENT if is_today else TEXT_DARK, anchor='lt')
        ds = day.strftime('%m-%d')
        dw = f_date.getlength(ds)
        draw.text((x + (col_w - dw) / 2, y0 + 54), ds, font=f_date,
                  fill=ACCENT if is_today else TEXT_GRAY, anchor='lt')

    # ---- 左侧节次列 + 网格 ----
    f_pnum = _font(21, bold=True)
    f_ptime = _font(13)
    grid_top = y0 + HEADER_H
    for p in range(n_rows):
        ry = grid_top + p * ROW_H
        mid = ry + ROW_H / 2
        # 节次号
        ns = str(p + 1)
        nw = f_pnum.getlength(ns)
        draw.text(((LEFT_W - nw) / 2, mid - 42), ns, font=f_pnum, fill=TEXT_DARK,
                  anchor='lt')
        # 时间
        for j, tline in enumerate(BIG_PERIOD_TIMES[p].split('\n')):
            lw_ = f_ptime.getlength(tline)
            draw.text(((LEFT_W - lw_) / 2, mid - 6 + j * 21), tline, font=f_ptime,
                      fill=TEXT_GRAY, anchor='lt')
        # 横线
        draw.line((LEFT_W + 4, ry, W - PAD, ry), fill=GRID_LINE, width=1)

    # 竖线（列分隔），与网页版一致
    for i in range(8):
        vx = LEFT_W + PAD + i * (col_w + COL_GAP) - COL_GAP
        draw.line((vx, y0, vx, grid_top + n_rows * ROW_H), fill=GRID_LINE, width=1)
    # 表格底线
    draw.line((LEFT_W + 4, grid_top + n_rows * ROW_H, W - PAD,
               grid_top + n_rows * ROW_H), fill=GRID_LINE, width=1)

    # ---- 课程块 ----
    for c in active:
        day_idx = c['day'] - 1
        if not (0 <= day_idx <= 6):
            continue
        sp, ep = c['startPeriod'], c['endPeriod']
        # 小节(1-2)→大节0, (3-4)→大节1 ...
        bp0 = (sp - 1) // 2
        bp1 = (ep - 1) // 2
        x = LEFT_W + PAD + day_idx * (col_w + COL_GAP)
        by0 = grid_top + bp0 * ROW_H + 7
        by1 = grid_top + (bp1 + 1) * ROW_H - 7

        weeks = c.get('weeks') or []
        if weeks:
            wr = f"({weeks[0]}-{weeks[-1]}周)" if len(weeks) > 1 else f"({weeks[0]}周)"
        else:
            wr = ''
        loc = c.get('location') or ''
        for _p in _LOCATION_STRIP:
            loc = loc.replace(_p, '')
        # 「东校区云海楼208」→「云海楼208」：不缩短的话一周七列的格子放不下，
        # 房间号会被拆成两行（云海2 / 08）
        import re as _re
        loc = _re.sub(r'^[\u4e00-\u9fff]{1,3}校区', '', loc)
        loc = loc.replace('楼', '')
        teacher = c.get('teacher') or ''
        subs = []
        if loc:
            subs.append(loc)
        if teacher:
            subs.append(teacher)
        # 周次不再显示：一周视图里每门课都占满大部分周，这行信息量低，
        # 去掉后每块少一行，垂直方向宽松不少。

        _draw_block(draw, (x, by0, x + col_w, by1), _color_for(c['name']),
                    c['name'], [s for s in subs if s])

    if out_path is None:
        out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'output')
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f'week_{anchor.isoformat()}.png')
    img.save(out_path, 'PNG')
    return out_path


if __name__ == '__main__':
    p = render_week_image()
    print('已生成:', p)
