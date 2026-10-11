#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
课表图片渲染器 —— 超级课程表风格的彩色格子周课表
输出 PNG，供 MCP 工具调用。
"""
import os, sys, datetime, hashlib

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'class-schedule')))
import today_schedule as ts  # noqa: E402

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

# ---- 布局常量 ----
W = 860
HEADER_H = 100         # 顶部星期/日期行
TITLE_H = 68           # 标题行
LEFT_W = 76            # 左侧节次列
ROW_H = 205            # 每个大节行高
N_PERIODS = 6          # 6 个大节
PAD = 18
COL_GAP = 8

# 地点前缀去掉哪些词（各校命名不同，逗号分隔；默认不去）
_LOCATION_STRIP = [p.strip() for p in
                   (os.environ.get('SCHEDULE_LOCATION_STRIP') or '').split(',') if p.strip()]

FONT_PATH = os.environ.get('SCHEDULE_FONT') or 'C:/Windows/Fonts/msyh.ttc'
FONT_BOLD_PATH = os.environ.get('SCHEDULE_FONT_BOLD') or 'C:/Windows/Fonts/msyhbd.ttc'

# 深色护眼主题（Tokyo Night 系）
PALETTE = [
    (247, 118, 142),  # 红
    (255, 158, 100),  # 橙
    (224, 175, 104),  # 黄
    (158, 206, 106),  # 绿
    (115, 218, 202),  # 青
    (122, 162, 247),  # 蓝
    (187, 154, 247),  # 紫
    (255, 121, 198),  # 粉
    (125, 207, 255),  # 天蓝
    (245, 169, 127),  # 杏
]

BG = (24, 25, 38)            # 深夜蓝黑
PANEL = (31, 33, 48)         # 略浅的面板
GRID_LINE = (42, 45, 64)
TEXT_DARK = (220, 222, 233)  # 主文字（亮）
TEXT_GRAY = (130, 134, 156)  # 次文字
TODAY_BG = (48, 42, 62)      # 今日列高亮底
ACCENT = (255, 184, 108)     # 今日强调橙


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


def _draw_block(draw, xy, color, title, sub_lines, radius=18):
    x0, y0, x1, y1 = xy
    # 柔和投影
    draw.rounded_rectangle((x0 + 2, y0 + 5, x1 + 2, y1 + 5), radius=radius, fill=(14, 15, 24))
    fill = _mix(color, PANEL, 0.78)          # 深色底透一点课程色
    title_c = _mix(color, (255, 255, 255), 0.30)  # 标题用同色浅调
    sub_c = _mix(color, (226, 228, 238), 0.72)
    draw.rounded_rectangle(xy, radius=radius, fill=fill,
                           outline=_mix(color, BG, 0.15), width=2)

    cx = (x0 + x1) / 2
    max_w = x1 - x0 - 10

    f_title = _font(22, bold=True)
    f_sub = _font(15)

    # 组装所有行（5-7 字纯中文课名按 3+2/4+3 均衡分行，避免 4+1 孤字）
    rows = []
    if (5 <= len(title) <= 7 and all('一' <= ch <= '鿿' for ch in title)
            and f_title.getlength(title) > max_w):
        mid = (len(title) + 1) // 2
        title_lines = [title[:mid], title[mid:]]
    else:
        title_lines = _wrap_cjk(title, f_title, max_w)
    for ln in title_lines:
        rows.append((ln, f_title, 32, title_c))
    for sub in sub_lines:
        for ln in _wrap_cjk(sub, f_sub, max_w):
            rows.append((ln, f_sub, 26, sub_c))

    total_h = sum(h for _, _, h, _ in rows)
    y = y0 + ((y1 - y0) - total_h) / 2
    for text, font, lh, color_ in rows:
        tw = font.getlength(text)
        draw.text((cx - tw / 2, y), text, font=font, fill=color_)
        y += lh


def render_week_image(out_path=None, ref_date=None):
    """渲染当前周课表 PNG，返回文件路径"""
    today = ref_date or datetime.date.today()
    monday = today - datetime.timedelta(days=today.isoweekday() - 1)
    week = ts.current_week(today)

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

    # 整体圆角面板
    draw.rounded_rectangle((8, TITLE_H - 6, W - 8, H - 8), radius=22, fill=PANEL)

    col_w = (W - LEFT_W - PAD * 2 - COL_GAP * 6) / 7

    # ---- 标题 ----
    f_title = _font(30, bold=True)
    title = f'第 {week} 周课表'
    tw = f_title.getlength(title)
    draw.text(((W - tw) / 2, 14), title, font=f_title, fill=TEXT_DARK)
    f_sub = _font(18)
    sub = f"{monday.strftime('%Y-%m-%d')} ~ {(monday + datetime.timedelta(days=6)).strftime('%m-%d')}"
    sw = f_sub.getlength(sub)
    draw.text(((W - sw) / 2, 48), sub, font=f_sub, fill=TEXT_GRAY)

    y0 = TITLE_H

    # ---- 表头 ----
    f_day = _font(20, bold=True)
    f_date = _font(17)
    for i in range(7):
        day = monday + datetime.timedelta(days=i)
        x = LEFT_W + PAD + i * (col_w + COL_GAP)
        is_today = (day == today)
        if is_today:
            draw.rounded_rectangle((x, y0 + 6, x + col_w, y0 + HEADER_H - 8),
                                   radius=12, fill=TODAY_BG)
        name = DAY_NAMES[i]
        nw = f_day.getlength(name)
        draw.text((x + (col_w - nw) / 2, y0 + 18), name, font=f_day,
                  fill=ACCENT if is_today else TEXT_DARK)
        ds = day.strftime('%m-%d')
        dw = f_date.getlength(ds)
        draw.text((x + (col_w - dw) / 2, y0 + 50), ds, font=f_date,
                  fill=ACCENT if is_today else TEXT_GRAY)

    # ---- 左侧节次列 + 网格 ----
    f_pnum = _font(22, bold=True)
    f_ptime = _font(14)
    grid_top = y0 + HEADER_H
    for p in range(n_rows):
        ry = grid_top + p * ROW_H
        mid = ry + ROW_H / 2
        # 节次号
        ns = str(p + 1)
        nw = f_pnum.getlength(ns)
        draw.text(((LEFT_W - nw) / 2, mid - 42), ns, font=f_pnum, fill=TEXT_DARK)
        # 时间
        for j, tline in enumerate(BIG_PERIOD_TIMES[p].split('\n')):
            lw_ = f_ptime.getlength(tline)
            draw.text(((LEFT_W - lw_) / 2, mid - 8 + j * 22), tline, font=f_ptime, fill=TEXT_GRAY)
        # 横线
        draw.line((LEFT_W + 4, ry, W - PAD, ry), fill=GRID_LINE, width=1)

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
        by0 = grid_top + bp0 * ROW_H + 4
        by1 = grid_top + (bp1 + 1) * ROW_H - 4

        weeks = c.get('weeks') or []
        if weeks:
            wr = f"({weeks[0]}-{weeks[-1]}周)" if len(weeks) > 1 else f"({weeks[0]}周)"
        else:
            wr = ''
        loc = c.get('location') or ''
        for _p in _LOCATION_STRIP:
            loc = loc.replace(_p, '')
        loc = loc.replace('楼', '')
        teacher = c.get('teacher') or ''
        subs = []
        if loc:
            subs.append(f"@{loc}")
        if teacher:
            subs.append(teacher)
        if wr:
            subs.append(wr)
        _draw_block(draw, (x, by0, x + col_w, by1), _color_for(c['name']),
                    c['name'], [s for s in subs if s])

    if out_path is None:
        out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'output')
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f'week_{today.isoformat()}.png')
    img.save(out_path, 'PNG')
    return out_path


if __name__ == '__main__':
    p = render_week_image()
    print('已生成:', p)
