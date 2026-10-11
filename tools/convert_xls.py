#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
示例大学教务处课表转换器
将 .xls/.xlsx 课表文件转换为小程序可导入的 JSON 格式

用法：
  python convert_xls.py 学生个人课表_xxx.xlsx

输出：
  schedule_data.json —— 可直接在小程序中导入
"""

import sys, os, re, json

def read_excel(filepath):
    """读取 xls 或 xlsx 文件，自动检测格式"""
    ext = os.path.splitext(filepath)[1].lower()

    # 先尝试 xlrd (支持真正的 .xls)
    if ext in ('.xls',):
        import xlrd
        wb = xlrd.open_workbook(filepath, encoding_override='gbk')
        ws = wb.sheet_by_index(0)
        rows = []
        for r in range(ws.nrows):
            row = []
            for c in range(ws.ncols):
                row.append(ws.cell_value(r, c))
            rows.append(row)
        return rows

    elif ext in ('.xlsx',):
        # .xlsx 可能是旧版 .xls 伪装，先试 xlrd
        try:
            import xlrd
            wb = xlrd.open_workbook(filepath, encoding_override='gbk')
            ws = wb.sheet_by_index(0)
            rows = []
            for r in range(ws.nrows):
                row = []
                for c in range(ws.ncols):
                    row.append(ws.cell_value(r, c))
                rows.append(row)
            return rows
        except:
            pass

        # 再试 openpyxl
        import openpyxl
        wb = openpyxl.load_workbook(filepath, data_only=True)
        ws = wb.active
        rows = []
        for row in ws.iter_rows(min_row=1, max_row=ws.max_row, values_only=True):
            rows.append([cell or '' for cell in row])
        return rows

    else:
        raise ValueError(f'不支持的文件格式: {ext}')


def parse_week_info(week_str):
    """
    解析周次字符串，返回 (weeks_list, week_type)
    支持格式:
      "2-17([周])"   "3,5,7,9([周])"   "5,7,9([单周])"   "2,4-13([周])"
    """
    week_str = week_str.strip()

    # 提取周类型
    week_type = 'all'
    if '单周' in week_str or '[单]' in week_str:
        week_type = 'odd'
    elif '双周' in week_str or '[双]' in week_str:
        week_type = 'even'
    elif '[周]' in week_str or '周' in week_str:
        week_type = 'all'
    else:
        week_type = 'all'

    # 去掉方括号和圆括号及内容
    week_str = re.sub(r'[\[\(][^\]\)]*[\]\)]', '', week_str).strip()

    # 去掉末尾残留的括号
    week_str = re.sub(r'[\(\)\[\]]', '', week_str).strip()

    # 解析周次列表
    weeks = set()
    parts = week_str.split(',')
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if '-' in part:
            try:
                a, b = part.split('-', 1)
                start, end = int(a.strip()), int(b.strip())
                for i in range(start, end + 1):
                    weeks.add(i)
            except:
                pass
        else:
            try:
                weeks.add(int(part))
            except:
                pass

    return sorted(weeks), week_type


def parse_period_info(period_str):
    """解析节次字符串, 如 "[01-02节]" → (1, 2)"""
    m = re.search(r'\[?(\d{2})-(\d{2})节\]?', period_str)
    if m:
        return int(m.group(1)), int(m.group(2))
    return 1, 2


def parse_cell(cell_text):
    """
    解析一个课表单元格中的文本，提取课程列表
    支持一个单元格中包含多门课程（用空行分隔）

    单元格格式（每门课）:
      课程名称
      (可选备注/分组)
      教师名
      周次信息([周/单周/双周])[节次信息]
      地点
    """
    if not cell_text or not cell_text.strip():
        return []

    # 标准化换行符（Excel 可能用 \r\n 或 \r）
    text = cell_text.strip()
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    courses = []

    # 按空行分割多门课程
    blocks = re.split(r'\n\s*\n', text)

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        lines = [l.strip() for l in block.split('\n') if l.strip()]
        if not lines:
            continue

        # 分类每一行
        name = ''
        teacher = ''
        location = ''
        weeks = []
        week_type = 'all'
        start_period = 1
        end_period = 2
        note = ''
        other_lines = []

        for line in lines:
            # 检测是否是备注行: (...)，短行
            if re.match(r'^\([^)]+\)$', line) and len(line) < 20:
                note = line.strip('()')
                continue

            # 检测周次/节次行
            if re.search(r'\[\d{2}[-–,]\d{2}节\]', line):
                # 提取节次
                sp, ep = parse_period_info(line)
                start_period, end_period = sp, ep

                # 提取周次部分（节次信息之前）
                week_part = re.sub(r'\[.*?节\].*', '', line).strip()
                if week_part:
                    # 确保包含周类型标记
                    if not re.search(r'[\[\(][周单双]', week_part):
                        week_part += '([周])'
                    weeks, week_type = parse_week_info(week_part)
                continue

            # 检测地点行（"实验"不在此处，因为很多课名含"实验"）
            if any(kw in line for kw in ['校区', '楼', '机房', '外语']):
                location = line
                continue

            # 收集其他行（课程名/教师）
            other_lines.append(line)

        # 从 other_lines 中分配课程名和教师
        if other_lines:
            # 第一行 → 课程名
            name = other_lines[0]
            # 第二行 → 教师（多人用逗号/顿号分隔）
            if len(other_lines) >= 2:
                teacher = other_lines[1]

        if name:
            courses.append({
                'name': name,
                'teacher': teacher,
                'location': location,
                'weeks': weeks,
                'weekType': week_type,
                'startPeriod': start_period,
                'endPeriod': end_period,
                'note': note
            })

    return courses


def convert(filepath):
    """主转换函数"""
    rows = read_excel(filepath)

    # 找到课表网格: Row 2 是表头 = 星期一~星期日
    # Row 3-8 是 第一大节~第六大节, col 1-7 是周一~周日

    # 查找星期行
    header_row = None
    day_mapping = {}
    for r, row in enumerate(rows):
        for c, val in enumerate(row):
            val = str(val).strip()
            if val in ['星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日', '周日']:
                if val == '周日':
                    val = '星期日'
                day_mapping[c] = val
        if len(day_mapping) >= 5:
            header_row = r
            break

    if header_row is None:
        return {'error': '未找到课表星期表头，请确认文件格式'}

    # 星期映射为数字
    day_num = {'星期一': 1, '星期二': 2, '星期三': 3, '星期四': 4,
               '星期五': 5, '星期六': 6, '星期日': 7}

    # 节次行映射 (row → periods)
    # 这些行包含 "第一大节" "第二大节" 等
    # 每行对应2个小节
    period_rows = []
    for r in range(header_row + 1, len(rows)):
        col0 = str(rows[r][0]).strip() if len(rows[r]) > 0 else ''
        if '大节' in col0 and '小节' in col0:
            period_rows.append(r)

    all_courses = []
    semester_info = ''
    student_info = ''

    # 提取学期信息
    for r in range(0, min(3, len(rows))):
        for c, val in enumerate(rows[r]):
            val = str(val).strip()
            if '学年学期' in val:
                semester_info = val
            if '学生个人课表' in val:
                student_info = val

    # 遍历课表网格
    for row_idx, data_row in enumerate(period_rows):
        # 这个节次行对应2个小节: (row_idx*2+1, row_idx*2+2)
        sp = row_idx * 2 + 1
        ep = row_idx * 2 + 2

        for col in day_mapping:
            day = day_num.get(day_mapping[col], col)
            if col >= len(rows[data_row]):
                continue
            cell_text = str(rows[data_row][col])
            courses = parse_cell(cell_text)

            for course in courses:
                course['day'] = day
                # 如果单元格解析没有提取到节次，使用默认
                if course.get('startPeriod', 1) == 1 and course.get('endPeriod', 2) == 2:
                    # 尝试用节次行的默认值
                    course['startPeriod'] = sp
                    course['endPeriod'] = ep

                # 规范化
                all_courses.append({
                    'name': course['name'],
                    'teacher': course.get('teacher', ''),
                    'location': course.get('location', ''),
                    'day': course['day'],
                    'startPeriod': course['startPeriod'],
                    'endPeriod': course['endPeriod'],
                    'startWeek': 1,
                    'totalWeeks': 20,
                    'weekType': course.get('weekType', 'all'),
                    'weeks': course.get('weeks', []),
                    'note': course.get('note', '')
                })

    # 提取学期起始日期
    import datetime
    semester_start = ''
    for r in range(0, min(3, len(rows))):
        for c, val in enumerate(rows[r]):
            val = str(val).strip()
            m = re.search(r'打印日期[：:](\d{4}-\d{2}-\d{2})', val)
            if m:
                semester_start = m.group(1)

    return {
        'meta': {
            'student': student_info,
            'semester': semester_info,
            'semesterStart': semester_start,
            'convertTime': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'totalCourses': len(all_courses)
        },
        'courses': all_courses
    }


def main():
    if len(sys.argv) < 2:
        print('用法: python convert_xls.py <课表文件.xls/xlsx>')
        print('示例: python convert_xls.py 学生个人课表_24690307.xlsx')
        sys.exit(1)

    filepath = sys.argv[1]
    if not os.path.exists(filepath):
        print(f'错误: 文件不存在 - {filepath}')
        sys.exit(1)

    print(f'正在解析: {filepath}')

    try:
        result = convert(filepath)
    except Exception as e:
        print(f'解析失败: {e}')
        import traceback
        traceback.print_exc()
        sys.exit(1)

    if 'error' in result:
        print(f'错误: {result["error"]}')
        sys.exit(1)

    # 输出 JSON
    outpath = os.path.splitext(filepath)[0] + '_courses.json'
    with open(outpath, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f'\n转换成功!')
    print(f'  学生: {result["meta"]["student"]}')
    print(f'  学期: {result["meta"]["semester"]}')
    print(f'  课程数: {result["meta"]["totalCourses"]}')
    print(f'  输出文件: {outpath}')

    # 显示课程预览
    print(f'\n--- 课程列表 ---')
    for i, c in enumerate(result['courses'], 1):
        weeks_str = ','.join(map(str, c['weeks'][:5]))
        if len(c['weeks']) > 5:
            weeks_str += '...'
        wt = {'all': '每周', 'odd': '单周', 'even': '双周'}.get(c['weekType'], '')
        print(f'{i:2}. {c["name"]:　<12s} | {c["teacher"]:　<8s} | 周{c["day"]} {c["startPeriod"]:02d}-{c["endPeriod"]:02d}节 | {wt} | {weeks_str} | {c["location"]}')


if __name__ == '__main__':
    main()
