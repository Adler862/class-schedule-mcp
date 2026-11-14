#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""教务系统课表转换器：.xls / .xlsx → courses.json

三件事，按重要性排：

1. **表格长什么样是配置，不是代码。**
   表头在第几行、星期列怎么认、节次标签什么格式、单元格里哪一行是地点——
   各校导出都不一样，全在 DEFAULT_LAYOUT 里。换一所学校正常只改 JSON：

       python tools/convert_xls.py --print-layout > my-school.json
       # 改完
       python tools/convert_xls.py 课表.xls --layout my-school.json --start 2026-08-31

2. **解析过程留下可定位的诊断。**
   每条问题都带 sheet / 行列 / 原文 / 命中规则。以前「周次写成 2-1」只会变成
   一门没有周次的课，然后整学期不出现，没人知道为什么；现在会直接告诉你
   `[W] R4C2 cell.week_range_reversed：周次区间「2-1」是倒序的`。

3. **纯函数与 IO 分开。**
   `parse_sheet(rows)` 只吃二维数组，测试不用造 .xls；
   `read_sheet(path)` 负责把文件读成二维数组。解析器因此可以在没有 xlrd
   的环境里被完整测试。

用法：
  python tools/convert_xls.py 课表.xls --start 2026-08-31 --out config/mine.json
  python tools/convert_xls.py 课表.xls --layout 我校.json --strict
  python tools/convert_xls.py --print-layout
"""

import os
import re
import sys
import copy
import json
import datetime

# ---------------------------------------------------------------------------
# 布局规则：一个学校的导出格式 = 这一份 JSON
# ---------------------------------------------------------------------------

MAX_WEEK = 30          # 超出这个范围的周次基本是解析错了，只报不拦

DEFAULT_LAYOUT = {
    'version': 1,
    'meta': {
        # 标题/学期/打印日期只在前几行出现，扫全表既慢又容易误命中
        'scanRows': 3,
        'studentMarkers': ['学生个人课表'],
        'semesterMarkers': ['学年学期'],
        'printDateRegex': r'打印日期[：:]\s*(\d{4}-\d{2}-\d{2})',
    },
    'header': {
        # 星期标签 → 数字。各校写法不同，这里列全，多写不亏
        'labels': {
            '星期一': 1, '星期二': 2, '星期三': 3, '星期四': 4,
            '星期五': 5, '星期六': 6, '星期日': 7, '星期天': 7,
            '周一': 1, '周二': 2, '周三': 3, '周四': 4,
            '周五': 5, '周六': 6, '周日': 7, '周天': 7,
            '一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '日': 7,
        },
        # 一行里认出这么多星期列才算表头（五天工作制的学校可以调低到 5）
        'minColumns': 5,
        # 表头只在前面这些行里找。导出文件常有几十行空模板，扫全表会认错
        'searchRows': 15,
        # 显式列映射 {"1": 1, "2": 2, ...}（星期 → 列号，0 基）。
        # null 表示自动发现；学校布局怪异时填这个，就不用猜
        'columns': None,
    },
    'periods': {
        'column': 0,                       # 节次标签在哪一列
        'labelRegex': r'(?:第)?([一二三四五六七八九十]+|\d+)\s*大节',
        'labelMustContain': ['大节', '小节'],   # 收紧条件，避免把别的行认成节次行
        'rows': None,                      # 显式行号列表（0 基）；null 表示扫描
        'subPeriods': 2,                   # 每个大节包含几个小节
        'numberFromLabel': True,           # 节次编号取标签（「第三大节」→3）而不是行序
    },
    'cell': {
        'blockSeparator': r'\n\s*\n',      # 一个格子里多门课，用空行分隔
        # 逐行分类。按顺序试，先命中先生效；regex 与 anyOf 同时存在时两个都要满足
        'lineRules': [
            {'role': 'note', 'regex': r'^\([^)]+\)$', 'maxLength': 20},
            # 周次 + 节次写在同一行是最常见的形状
            {'role': 'period', 'regex': r'\[\d{1,2}[-–,，]\d{1,2}节\]'},
            # 只有周次、没写节次（如「3,5,7,9([双周])」）。单独一条，顺序在 period 之后。
            # 周字前面必须有数字或「第」，否则「周易研究」这种课名会被当成周次
            {'role': 'weeks',
             'regex': r'(?:[\d一二三四五六七八九十第,，\-–至]+\s*[\[\(（]*\s*[单双]?\s*周)'
                      r'|(?:^[单双]周$)'},
            {'role': 'location', 'anyOf': ['校区', '楼', '机房', '外语']},
        ],
        # 没被规则认领的行，按这个顺序当作课程名、教师
        'fieldOrder': ['name', 'teacher'],
    },
    'defaults': {
        'startWeek': 1,
        'totalWeeks': 20,
        'weekType': 'all',
    },
}

# 兼容旧名字：外部脚本可能 import 过 COMPOUND_SURNAMES
# 复姓表：只列常见的，判不出来就按单姓取首字，宁可粗一点也不要漏
COMPOUND_SURNAMES = ('欧阳', '司马', '上官', '诸葛', '东方', '独孤', '慕容', '令狐',
                     '皇甫', '尉迟', '公孙', '长孙', '宇文', '司徒', '夏侯', '轩辕',
                     '端木', '澹台', '南宫', '西门')

ERROR, WARNING, INFO = 'error', 'warning', 'info'


# ---------------------------------------------------------------------------
# 诊断
# ---------------------------------------------------------------------------

class Diagnostic:
    """一条可定位的问题。

    row / col 是 0 基（内部用），对外显示时 +1 变成 R4C2 这种人能读的坐标。
    rule 记录是哪条规则判的，换学校改配置时这一栏最有用。
    """

    __slots__ = ('severity', 'code', 'message', 'rule', 'sheet', 'row', 'col', 'snippet')

    def __init__(self, severity, code, message, rule='', sheet='',
                 row=None, col=None, snippet=''):
        self.severity = severity
        self.code = code
        self.message = message
        self.rule = rule
        self.sheet = sheet
        self.row = row
        self.col = col
        self.snippet = snippet

    @property
    def cell(self):
        if self.row is None:
            return ''
        if self.col is None:
            return f'R{self.row + 1}'
        return f'R{self.row + 1}C{self.col + 1}'

    def as_dict(self):
        return {
            'severity': self.severity, 'code': self.code, 'message': self.message,
            'rule': self.rule, 'sheet': self.sheet, 'cell': self.cell,
            'row': self.row, 'col': self.col, 'snippet': self.snippet,
        }

    def __str__(self):
        tag = {ERROR: 'E', WARNING: 'W', INFO: 'I'}.get(self.severity, '?')
        where = f'{self.cell} ' if self.cell else ''
        rule = f'（规则 {self.rule}）' if self.rule else ''
        snip = f'：{self.snippet}' if self.snippet else ''
        return f'[{tag}] {where}{self.code}{rule} {self.message}{snip}'


def _diag(diags, severity, code, message, **kw):
    """收集诊断。diags 为 None 时什么也不做——纯函数调用方不必关心。"""
    if diags is None:
        return
    diags.append(Diagnostic(severity, code, message, **kw))


def summarize(diags):
    """→ {'error': n, 'warning': n, 'info': n, 'total': n}"""
    out = {ERROR: 0, WARNING: 0, INFO: 0}
    for d in diags or []:
        out[d.severity] = out.get(d.severity, 0) + 1
    out['total'] = len(diags or [])
    return out


# ---------------------------------------------------------------------------
# 布局加载
# ---------------------------------------------------------------------------

def _deep_merge(base, over):
    out = dict(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            out[k] = _deep_merge(base[k], v)
        else:
            out[k] = v
    return out


def load_layout(source=None):
    """默认布局 / 部分覆盖的 dict / JSON 文件路径 → 完整布局。

    做深合并而不是整体替换：只想改一个标签的学校不必复制整份配置。
    """
    layout = copy.deepcopy(DEFAULT_LAYOUT)
    if source is None:
        return layout
    if isinstance(source, dict):
        return _deep_merge(layout, source)
    with open(source, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f'布局文件必须是一个 JSON 对象：{source}')
    return _deep_merge(layout, data)


def dump_layout(layout=None):
    """布局 → 可读 JSON 文本（--print-layout 用）。"""
    return json.dumps(layout or DEFAULT_LAYOUT, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# 读文件
# ---------------------------------------------------------------------------

def _txt(value):
    """单元格值 → 字符串。None 变成空串，而不是 "None"。"""
    if value is None:
        return ''
    return str(value)


def _read_with_xlrd(filepath):
    import xlrd
    wb = xlrd.open_workbook(filepath, encoding_override='gbk')
    ws = wb.sheet_by_index(0)
    rows = [[ws.cell_value(r, c) for c in range(ws.ncols)] for r in range(ws.nrows)]
    return rows, ws.name


def _read_with_openpyxl(filepath):
    import openpyxl
    wb = openpyxl.load_workbook(filepath, data_only=True)
    ws = wb.active
    rows = [[cell for cell in row]
            for row in ws.iter_rows(min_row=1, max_row=ws.max_row, values_only=True)]
    return rows, ws.title


def read_sheet(filepath):
    """→ (rows, sheet_name)。rows 是二维数组，含表头与空行，保留原坐标。"""
    ext = os.path.splitext(filepath)[1].lower()
    if ext == '.xls':
        return _read_with_xlrd(filepath)
    if ext == '.xlsx':
        # .xlsx 后缀有时其实是旧版 .xls（导出工具会干这事），先按 xls 试
        try:
            return _read_with_xlrd(filepath)
        except Exception:
            return _read_with_openpyxl(filepath)
    raise ValueError(f'不支持的文件格式: {ext}')


def read_excel(filepath):
    """只要二维数组（旧接口，保留）。"""
    return read_sheet(filepath)[0]


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------

_CN_DIGITS = {'零': 0, '一': 1, '二': 2, '三': 3, '四': 4,
              '五': 5, '六': 6, '七': 7, '八': 8, '九': 9}


def cn_to_int(text):
    """「一」「十二」「二十」→ 1 / 12 / 20；纯数字直接转；认不出返回 None。"""
    s = (text or '').strip()
    if not s:
        return None
    if s.isdigit():
        return int(s)
    if s in _CN_DIGITS:
        return _CN_DIGITS[s]
    if '十' in s:
        head, _, tail = s.partition('十')
        if head and head not in _CN_DIGITS:
            return None
        if tail and tail not in _CN_DIGITS:
            return None
        return (_CN_DIGITS.get(head, 1) if head else 1) * 10 + (_CN_DIGITS.get(tail, 0) if tail else 0)
    return None


def _classify(line, cfg):
    """按 cell.lineRules 给一行定性，返回 (role, rule_index) 或 (None, None)。"""
    for idx, rule in enumerate(cfg.get('lineRules') or []):
        regex = rule.get('regex')
        any_of = rule.get('anyOf')
        if not regex and not any_of:
            continue
        if regex and not re.search(regex, line):
            continue
        if any_of and not any(k in line for k in any_of):
            continue
        max_len = rule.get('maxLength')
        if max_len is not None and len(line) >= int(max_len):
            continue
        return rule.get('role'), idx
    return None, None


# ---------------------------------------------------------------------------
# 单元格解析
# ---------------------------------------------------------------------------

def _week_number(token):
    """单个周次 → int。认「3」「03」「第三」「第3周」，认不出返回 None。"""
    return cn_to_int(re.sub(r'[第周节\s]', '', _txt(token)))


# 只匹配「[01-02节]」这个记号本身。
# 旧实现用 \[.*?节\].* 从第一个方括号一路吃到「节]」，遇到
# 「1-15([单周])[01-02节]」会把「([单周])」一起吃进去，单双周标记就丢了。
_PERIOD_TOKEN = re.compile(r'\[?\s*\d{1,2}\s*[-–,，]\s*\d{1,2}\s*节\s*\]?')


def _strip_period_token(line):
    """摘掉节次记号，留下周次部分。"""
    return _PERIOD_TOKEN.sub('', line).strip()


def parse_week_info(week_str, diags=None, row=None, col=None, sheet=''):
    """周次字符串 → (weeks, week_type)。

    支持 "2-17([周])" "3,5,7,9([周])" "5,7,9([单周])" "2,4-13([周])"。
    区间倒序、越界都只报警告不抛异常：一张课表不该因为一个格子整份失败，
    但也不能悄悄变成「这门课整学期不上」。
    """
    week_str = _txt(week_str).strip()

    week_type = 'all'
    if '单周' in week_str or '[单]' in week_str:
        week_type = 'odd'
    elif '双周' in week_str or '[双]' in week_str:
        week_type = 'even'

    # 去掉方括号/圆括号及其中内容（周次标记本身）
    week_str = re.sub(r'[\[\(][^\]\)]*[\]\)]', '', week_str).strip()
    week_str = re.sub(r'[\(\)\[\]]', '', week_str).strip()

    weeks = set()
    from_range = False
    for part in week_str.split(','):
        part = part.strip()
        if not part:
            continue
        if re.search(r'[-–至]', part):
            a, b = re.split(r'[-–至]', part, maxsplit=1)
            lo, hi = _week_number(a), _week_number(b)
            if lo is None or hi is None:
                _diag(diags, WARNING, 'cell.week_unparsed',
                      '周次区间无法解析，已跳过', rule='parseWeekInfo',
                      sheet=sheet, row=row, col=col, snippet=part)
                continue
            if hi < lo:
                _diag(diags, WARNING, 'cell.week_range_reversed',
                      f'周次区间「{part}」是倒序的，这一段不会产生任何周次',
                      rule='parseWeekInfo', sheet=sheet, row=row, col=col, snippet=part)
                continue
            if lo < 1 or hi > MAX_WEEK:
                _diag(diags, WARNING, 'cell.week_out_of_range',
                      f'周次「{part}」超出 1–{MAX_WEEK} 的合理范围',
                      rule='parseWeekInfo', sheet=sheet, row=row, col=col, snippet=part)
            weeks.update(range(lo, hi + 1))
            from_range = True
        else:
            n = _week_number(part)
            if n is None:
                _diag(diags, WARNING, 'cell.week_unparsed',
                      '周次「%s」不是数字，已跳过' % part, rule='parseWeekInfo',
                      sheet=sheet, row=row, col=col, snippet=part)
                continue
            if n < 1 or n > MAX_WEEK:
                _diag(diags, WARNING, 'cell.week_out_of_range',
                      f'周次 {n} 超出 1–{MAX_WEEK} 的合理范围',
                      rule='parseWeekInfo', sheet=sheet, row=row, col=col, snippet=part)
            weeks.add(n)

    # 单双周展开成实际生效的周次。理由：semester.course_active 只要 weeks 非空
    # 就只看 weeks、忽略 weekType，把 1-15 原样留着，单周课会每周都上。
    #
    # 只对「区间」写法展开，不对「枚举」展开：
    #   1-15([单周])     → 区间 + 单周 → 1,3,…,15（标记是对区间的修饰）
    #   3,5,7,9([双周])  → 枚举本身就是生效周次 → 原样保留，再筛一次会筛空
    ordered = sorted(weeks)
    if from_range and week_type == 'odd':
        return [w for w in ordered if w % 2 == 1], week_type
    if from_range and week_type == 'even':
        return [w for w in ordered if w % 2 == 0], week_type
    return ordered, week_type


def parse_period_info(period_str):
    """「[03-04节]」→ (3, 4)；认不出返回 (None, None)。

    旧实现认不出时返回 (1, 2)，调用方再用它判断「没写节次」，于是
    真的写 [01-02节] 的格子和没写的格子无法区分。这里改成 None 表示未声明。
    """
    m = re.search(r'\[?(\d{1,2})\s*[-–,，]\s*(\d{1,2})\s*节\]?', _txt(period_str))
    if not m:
        return None, None
    return int(m.group(1)), int(m.group(2))


def _parse_block(lines, layout, diags=None, row=None, col=None, sheet=''):
    """一个空行分段 → 一门课。认不出课程名就返回 None 并记一条警告。"""
    cfg = layout['cell']
    name = teacher = location = note = ''
    weeks, week_type = [], layout['defaults'].get('weekType', 'all')
    start_period = end_period = None
    others = []

    for line in lines:
        role, _idx = _classify(line, cfg)
        if role == 'note':
            note = line.strip('()（）')
            continue
        if role in ('period', 'weeks'):
            sp, ep = parse_period_info(line)
            if sp is not None:
                start_period, end_period = sp, ep
            week_part = _strip_period_token(line)
            if week_part:
                if not re.search(r'[\[\(][周单双]', week_part):
                    week_part += '([周])'
                weeks, week_type = parse_week_info(week_part, diags, row=row, col=col, sheet=sheet)
            continue
        if role == 'location':
            location = line
            continue
        others.append(line)

    order = cfg.get('fieldOrder') or ['name', 'teacher']
    for i, field in enumerate(order):
        if i >= len(others):
            break
        if field == 'name':
            name = others[i]
        elif field == 'teacher':
            teacher = others[i]
    if len(others) > len(order):
        _diag(diags, WARNING, 'cell.extra_lines',
              f'有 {len(others) - len(order)} 行没被任何规则认领，已忽略',
              rule='cell.fieldOrder', sheet=sheet, row=row, col=col,
              snippet=' / '.join(others[len(order):]))

    if not name:
        _diag(diags, WARNING, 'cell.no_name',
              '这一段认不出课程名，整段已丢弃', rule='cell.fieldOrder',
              sheet=sheet, row=row, col=col, snippet=' / '.join(lines))
        return None

    if not weeks:
        sw = layout['defaults'].get('startWeek', 1)
        tw = layout['defaults'].get('totalWeeks', 20)
        _diag(diags, WARNING, 'cell.no_week_info',
              f'「{name}」没有周次信息，会按默认 {sw}–{sw + tw - 1} 周处理，可能不是真实周次',
              rule='cell.lineRules', sheet=sheet, row=row, col=col, snippet=' / '.join(lines))

    return {
        'name': name, 'teacher': teacher, 'location': location,
        'weeks': weeks, 'weekType': week_type,
        'startPeriod': start_period, 'endPeriod': end_period, 'note': note,
    }


def parse_cell(cell_text, layout=None, diags=None, row=None, col=None, sheet=''):
    """一个课表格子 → 课程列表。一个格子可以有多门课（空行分隔）。"""
    layout = layout or DEFAULT_LAYOUT
    text = _txt(cell_text).strip()
    if not text:
        return []
    text = text.replace('\r\n', '\n').replace('\r', '\n')

    courses = []
    for block in re.split(layout['cell']['blockSeparator'], text):
        block = block.strip()
        if not block:
            continue
        lines = [l.strip() for l in block.split('\n') if l.strip()]
        if not lines:
            continue
        rec = _parse_block(lines, layout, diags, row=row, col=col, sheet=sheet)
        if rec:
            courses.append(rec)
    return courses


# ---------------------------------------------------------------------------
# 表头与节次行
# ---------------------------------------------------------------------------

def _find_header(rows, layout, diags=None, sheet=''):
    """→ {'row': r, 'dayCols': {col: day}}；找不到返回 None。"""
    cfg = layout['header']
    labels = {str(k): int(v) for k, v in cfg['labels'].items()}
    min_cols = int(cfg.get('minColumns') or 5)
    search = min(int(cfg.get('searchRows') or 15), len(rows))

    explicit = cfg.get('columns')
    if explicit:
        day_cols = {int(col): int(day) for day, col in explicit.items()}
        header_row = None
        for r in range(search):
            if any(col < len(rows[r]) and _txt(rows[r][col]).strip() in labels
                   for col in day_cols):
                header_row = r
                break
        if header_row is None:
            _diag(diags, WARNING, 'header.labels_missing',
                  '布局里声明了星期列，但没在表里找到对应标签，按声明位置继续',
                  rule='header.columns', sheet=sheet)
        return {'row': header_row, 'dayCols': day_cols}

    best = {}
    best_row = None
    for r in range(search):
        found = {}
        for c, val in enumerate(rows[r]):
            text = _txt(val).strip()
            if text in labels:
                found[c] = labels[text]
        if len(found) > len(best):
            best, best_row = found, r
        if len(found) >= min_cols:
            if len(found) < 7:
                _diag(diags, INFO, 'header.partial_week',
                      f'只认出 {len(found)} 个星期列（共 {len(found)} 天有课）',
                      rule='header.labels', sheet=sheet, row=r)
            return {'row': r, 'dayCols': found}

    if best:
        _diag(diags, ERROR, 'header.too_few_columns',
              f'第 {best_row + 1} 行只认出 {len(best)} 个星期列，少于要求的 {min_cols} 个',
              rule='header.minColumns', sheet=sheet, row=best_row)
    else:
        _diag(diags, ERROR, 'header.not_found',
              f'前 {search} 行里没有找到任何星期表头', rule='header.labels', sheet=sheet)
    return None


def _find_period_rows(rows, layout, header_row, diags=None, sheet=''):
    """→ [(row, label_text)]，按表里出现的顺序。"""
    cfg = layout['periods']
    explicit = cfg.get('rows')
    if explicit:
        return [(int(r), _txt(rows[int(r)][int(cfg.get('column') or 0)]).strip()
                 if int(r) < len(rows) else '') for r in explicit]

    col = int(cfg.get('column') or 0)
    must = [str(k) for k in (cfg.get('labelMustContain') or [])]
    start = (header_row + 1) if header_row is not None else 0

    out = []
    for r in range(start, len(rows)):
        text = _txt(rows[r][col]).strip() if col < len(rows[r]) else ''
        if all(k in text for k in must):
            out.append((r, text))
    return out


def _period_number(label, index, layout, diags=None, sheet='', row=None):
    """节次行 → 第几个大节。取不到就用行序，并记一条警告。"""
    cfg = layout['periods']
    if not cfg.get('numberFromLabel', True):
        return index + 1

    m = re.search(cfg['labelRegex'], label or '')
    if m:
        raw = m.group(2) if (m.lastindex or 1) >= 2 else m.group(1)
        n = cn_to_int(raw)
        if n:
            return n
    _diag(diags, WARNING, 'periods.label_unparsed',
          '节次标签认不出编号，按行序处理', rule='periods.labelRegex',
          sheet=sheet, row=row, snippet=label)
    return index + 1


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def parse_sheet(rows, layout=None, sheet_name='', diags=None, start=None,
                mask_teachers=False, school=None, class_name=None):
    """二维数组 → {meta, courses}。这是整条转换链的核心，也是唯一需要测的函数。

    diags 传一个 list 进来，诊断会追加到里面；不传就静默（纯函数用法）。
    """
    layout = load_layout(layout)
    rows = [list(r) for r in (rows or [])]

    if not rows:
        _diag(diags, ERROR, 'sheet.empty', '表格是空的', sheet=sheet_name)
        return {'error': '表格是空的'}

    header = _find_header(rows, layout, diags, sheet_name)
    if header is None:
        return {'error': '未找到课表星期表头，请确认文件格式'}

    day_cols = header['dayCols']
    header_row = header['row']

    period_rows = _find_period_rows(rows, layout, header_row, diags, sheet_name)
    if not period_rows:
        _diag(diags, ERROR, 'periods.not_found',
              '没有找到任何节次行（第 0 列应含「%s」）'
              % '」「'.join(layout['periods'].get('labelMustContain') or []),
              rule='periods.labelMustContain', sheet=sheet_name)
        return {'error': '未找到「第 N 大节」这类节次行，请确认文件格式'}

    if len(period_rows) < 6:
        _diag(diags, WARNING, 'periods.few_rows',
              f'只认出 {len(period_rows)} 个节次行，正常应是 6 个（或按学校作息）',
              rule='periods.labelMustContain', sheet=sheet_name)

    sub = max(1, int(layout['periods'].get('subPeriods') or 2))
    all_courses = []

    for idx, (data_row, label) in enumerate(period_rows):
        n = _period_number(label, idx, layout, diags, sheet_name, data_row)
        row_sp = (n - 1) * sub + 1
        row_ep = n * sub

        for col, day in sorted(day_cols.items()):
            if col >= len(rows[data_row]):
                continue
            cell_text = _txt(rows[data_row][col])
            for course in parse_cell(cell_text, layout, diags,
                                     row=data_row, col=col, sheet=sheet_name):
                sp, ep = course['startPeriod'], course['endPeriod']
                if sp is None:
                    sp, ep = row_sp, row_ep
                elif (sp, ep) == (1, 2) and (row_sp, row_ep) != (1, 2):
                    # 导出里「没写节次」常常就写成了 01-02，以格子所在大节为准
                    _diag(diags, WARNING, 'cell.period_ambiguous',
                          f'「{course["name"]}」写的是 01-02 节，与所在大节（{row_sp}-{row_ep}）不符，'
                          '按所在大节处理', rule='periods.subPeriods',
                          sheet=sheet_name, row=data_row, col=col)
                    sp, ep = row_sp, row_ep
                elif (sp, ep) != (row_sp, row_ep):
                    _diag(diags, INFO, 'cell.period_mismatch',
                          f'「{course["name"]}」声明 {sp}-{ep} 节，格子位于第 {n} 大节，按声明处理',
                          rule='periods.subPeriods',
                          sheet=sheet_name, row=data_row, col=col)

                all_courses.append({
                    'name': course['name'],
                    'teacher': course.get('teacher', ''),
                    'location': course.get('location', ''),
                    'day': day,
                    'startPeriod': sp,
                    'endPeriod': ep,
                    'startWeek': layout['defaults'].get('startWeek', 1),
                    'totalWeeks': layout['defaults'].get('totalWeeks', 20),
                    'weekType': course.get('weekType', 'all'),
                    'weeks': course.get('weeks', []),
                    'note': course.get('note', ''),
                })

    meta = _extract_meta(rows, layout, sheet_name, diags)
    if start:
        meta['semesterStart'] = start
    elif meta['semesterStart']:
        _diag(diags, WARNING, 'meta.print_date_used',
              '未指定 --start，学期起点取自「打印日期」%s，这通常是学期中的某一天，'
              '算出来的周次会整体偏移' % meta['semesterStart'],
              rule='meta.printDateRegex', sheet=sheet_name)

    if mask_teachers:
        for c in all_courses:
            c['teacher'] = mask_teacher(c.get('teacher'))

    if school and meta['student']:
        # 标题形如「<校名> <姓名> 学生个人课表」，只换第一段校名，后面保留
        meta['student'] = re.sub(r'^\s*\S+?(?=\s)', school, meta['student'], count=1)

    if class_name and meta['semester']:
        meta['semester'] = re.sub(r'班级：\s*\S+', f'班级：{class_name}', meta['semester'])

    meta.update({
        'convertTime': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        # 时段数 ≠ 课程数：一门课一周可能上 3 次
        'totalCourses': len({c['name'] for c in all_courses}),
        'totalSlots': len(all_courses),
        'teacherMasked': bool(mask_teachers),
        'sanitized': bool(school or class_name),
    })
    return {'meta': meta, 'courses': all_courses}


def _extract_meta(rows, layout, sheet_name='', diags=None):
    cfg = layout['meta']
    scan = min(int(cfg.get('scanRows') or 3), len(rows))
    student = semester = print_date = ''
    for r in range(scan):
        for val in rows[r]:
            text = _txt(val)
            if any(k in text for k in (cfg.get('studentMarkers') or [])):
                student = text
            if any(k in text for k in (cfg.get('semesterMarkers') or [])):
                semester = text
            m = re.search(cfg['printDateRegex'], text)
            if m:
                print_date = m.group(1)
    if not student and not semester:
        _diag(diags, INFO, 'meta.not_found',
              f'前 {scan} 行里没找到「%s」这类标题，标题会留空'
              % '」「'.join((cfg.get('semesterMarkers') or []) + (cfg.get('studentMarkers') or [])),
              rule='meta.semesterMarkers', sheet=sheet_name)
    return {'student': student, 'semester': semester, 'semesterStart': print_date}


def mask_teacher(name):
    """教师姓名 → 姓 + 老师。多位老师用「、」分隔后各自处理。

    只保留姓氏是刻意的：课表要能看出「这门课是谁带的」，但不需要知道全名。
    王芳 → 王老师；欧阳修 → 欧阳老师；空值原样返回。
    """
    name = (name or '').strip()
    if not name:
        return ''
    out = []
    for part in re.split(r'[,，、/;；\s]+', name):
        part = part.strip()
        if not part:
            continue
        for c in COMPOUND_SURNAMES:
            if part.startswith(c) and len(part) > len(c):
                out.append(c + '老师')
                break
        else:
            out.append(part[0] + '老师')
    return '、'.join(out)


def convert(filepath, start=None, mask_teachers=False, school=None, class_name=None,
            layout=None, diagnostics=None):
    """文件 → {meta, courses}。

    start:     学期首周周一 YYYY-MM-DD。导出文件里只有「打印日期」，它可能是学期中
               任意一天，拿来当学期起点会让整学期错位，所以能从外面指定就指定。
    layout:    布局 dict 或 JSON 路径，None 用内建默认。
    diagnostics: 传 list 进来收诊断（不改输出结构，courses.json 保持干净）。
    """
    rows, sheet_name = read_sheet(filepath)
    return parse_sheet(rows, layout=layout, sheet_name=sheet_name, diags=diagnostics,
                       start=start, mask_teachers=mask_teachers,
                       school=school, class_name=class_name)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_diags(diags, limit=10):
    if not diags:
        return
    s = summarize(diags)
    parts = []
    for key, label in ((ERROR, '错误'), (WARNING, '警告'), (INFO, '提示')):
        if s.get(key):
            parts.append(f'{s[key]} {label}')
    print(f'\n诊断：{s["total"]} 条（{" / ".join(parts)}）')
    for d in diags[:limit]:
        print(f'  {d}')
    if len(diags) > limit:
        print(f'  ……另有 {len(diags) - limit} 条，用 --report 看全部')


def main():
    import argparse
    p = argparse.ArgumentParser(description='教务系统课表 .xls/.xlsx → courses.json')
    p.add_argument('filepath', nargs='?', help='导出的 .xls / .xlsx')
    p.add_argument('--out', help='输出 JSON 路径（默认写在输入文件旁边）')
    p.add_argument('--start', help='学期首周周一 YYYY-MM-DD（强烈建议指定）')
    p.add_argument('--mask-teacher', action='store_true', dest='mask_teacher',
                   help='教师姓名换成「姓 + 老师」，其余内容原样保留')
    p.add_argument('--school', help='替换标题里的学校名，如 --school 示例大学')
    p.add_argument('--class-name', dest='class_name',
                   help='替换学期行里的班级名，如 --class-name 示例班级')
    p.add_argument('--layout', help='布局 JSON（先用 --print-layout 导一份再改）')
    p.add_argument('--print-layout', action='store_true', dest='print_layout',
                   help='打印内建布局并退出，用来给自己学校的导出格式改一份')
    p.add_argument('--report', help='把全部诊断写成 JSON')
    p.add_argument('--strict', action='store_true',
                   help='出现警告或错误时以退出码 2 结束（适合放进脚本/CI）')
    args = p.parse_args()

    if args.print_layout:
        print(dump_layout(load_layout(args.layout) if args.layout else None))
        return 0

    if not args.filepath:
        p.error('需要指定课表文件（或用 --print-layout 导出布局）')

    if not os.path.exists(args.filepath):
        print(f'错误: 文件不存在 - {args.filepath}')
        return 1

    diags = []
    print(f'正在解析: {args.filepath}')
    if args.layout:
        print(f'  布局: {args.layout}')
    try:
        result = convert(args.filepath, start=args.start, mask_teachers=args.mask_teacher,
                         school=args.school, class_name=args.class_name,
                         layout=args.layout, diagnostics=diags)
    except Exception as e:
        print(f'解析失败: {e}')
        import traceback
        traceback.print_exc()
        return 1

    if args.report:
        with open(args.report, 'w', encoding='utf-8') as f:
            json.dump({'diagnostics': [d.as_dict() for d in diags],
                       'summary': summarize(diags)}, f, ensure_ascii=False, indent=2)

    if 'error' in result:
        print(f'错误: {result["error"]}')
        _print_diags(diags, limit=20)
        return 1

    outpath = args.out or os.path.splitext(args.filepath)[0] + '_courses.json'
    with open(outpath, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print('\n转换成功!')
    print(f'  学生: {result["meta"]["student"]}')
    print(f'  学期: {result["meta"]["semester"]}')
    print(f'  {result["meta"]["totalSlots"]} 个上课时段 · {result["meta"]["totalCourses"]} 门课')
    print(f'  学期起点: {result["meta"]["semesterStart"] or "(未设置)"}')
    print(f'  教师姓名: {"已改为「姓+老师」" if args.mask_teacher else "原样保留"}')
    print(f'  输出文件: {outpath}')

    _print_diags(diags)
    if args.report:
        print(f'  诊断报告: {args.report}')

    if args.strict and any(d.severity in (ERROR, WARNING) for d in diags):
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
