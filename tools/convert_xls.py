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


# 复姓表：只列常见的，判不出来就按单姓取首字，宁可粗一点也不要漏
COMPOUND_SURNAMES = ('欧阳', '司马', '上官', '诸葛', '东方', '独孤', '慕容', '令狐',
                     '皇甫', '尉迟', '公孙', '长孙', '宇文', '司徒', '夏侯', '轩辕',
                     '端木', '澹台', '南宫', '西门')


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


def convert(filepath, start=None, mask_teachers=False, school=None, class_name=None):
    """主转换函数

    start:     学期首周周一 YYYY-MM-DD。导出文件里只有「打印日期」，它可能是学期中
               任意一天，拿来当学期起点会让整学期错位，所以能从外面指定就指定。
    mask_teachers: 教师姓名换成「姓 + 老师」，其余字段一概不动。
    school / class_name: 替换标题里的学校和学期行里的班级名。
    """
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

    if start:
        semester_start = start
    elif semester_start:
        print(f'注意: 未指定 --start，学期起点取自「打印日期」{semester_start}，'
              f'这通常是学期中的某一天，算出来的周次会整体偏移。', file=sys.stderr)

    if mask_teachers:
        for c in all_courses:
            c['teacher'] = mask_teacher(c.get('teacher'))

    if school:
        # 标题形如「<校名> <姓名> 学生个人课表」，只换第一段校名，后面保留
        student_info = re.sub(r'^\s*\S+?(?=\s)', school, student_info, count=1)

    if class_name:
        semester_info = re.sub(r'班级：\s*\S+', f'班级：{class_name}', semester_info)

    return {
        'meta': {
            'student': student_info,
            'semester': semester_info,
            'semesterStart': semester_start,
            'convertTime': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            # 时段数 ≠ 课程数：一门课一周可能上 3 次
            'totalCourses': len({c['name'] for c in all_courses}),
            'totalSlots': len(all_courses),
            'teacherMasked': bool(mask_teachers),
            'sanitized': bool(school or class_name),
        },
        'courses': all_courses
    }


def main():
    import argparse
    p = argparse.ArgumentParser(description='教务系统课表 .xls → courses.json')
    p.add_argument('filepath', help='导出的 .xls / .xlsx')
    p.add_argument('--out', help='输出 JSON 路径（默认写在输入文件旁边）')
    p.add_argument('--start', help='学期首周周一 YYYY-MM-DD（强烈建议指定）')
    p.add_argument('--mask-teacher', action='store_true', dest='mask_teacher',
                   help='教师姓名换成「姓 + 老师」，其余内容原样保留')
    p.add_argument('--school', help='替换标题里的学校名，如 --school 示例大学')
    p.add_argument('--class-name', dest='class_name',
                   help='替换学期行里的班级名，如 --class-name 示例班级')
    args = p.parse_args()

    if not os.path.exists(args.filepath):
        print(f'错误: 文件不存在 - {args.filepath}')
        sys.exit(1)

    print(f'正在解析: {args.filepath}')
    try:
        result = convert(args.filepath, start=args.start, mask_teachers=args.mask_teacher,
                     school=args.school, class_name=args.class_name)
    except Exception as e:
        print(f'解析失败: {e}')
        import traceback
        traceback.print_exc()
        sys.exit(1)

    if 'error' in result:
        print(f'错误: {result["error"]}')
        sys.exit(1)

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


if __name__ == '__main__':
    main()
