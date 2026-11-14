# -*- coding: utf-8 -*-
"""课表 .xls 解析器测试。

拆成两层：
  - 纯函数（mask_teacher / parse_week_info / parse_cell）直接断言
  - parse_sheet(rows) 吃二维数组，所以不用造 .xls 文件、不依赖 xlrd

真实的教务导出含个人信息，不进仓库；这里用一份结构等价的合成表格。
"""
import os
import sys
import json
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

import convert_xls  # noqa: E402

B = ''


def demo_rows(odd_even=True, weeks_only=False, no_weeks=False):
    """仿教务导出：第 1 行标题、第 2 行学期、第 4 行星期表头、第 5-10 行六个大节。

    列：0 节次，1-7 周一至周日。
    """
    rows = [
        ['示例大学  张同学  学生个人课表'] + [B] * 7,
        ['学年学期：2026-2027-1        班级：计算机2301        专业：计算机科学与技术'
         '  打印日期：2026-11-01'] + [B] * 7,
        [B] * 8,
        [B, '星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日'],
    ]
    for i in range(6):
        rows.append([f'第{i + 1}大节\n(0{2 * i + 1}-0{2 * i + 2}小节)'] + [B] * 7)

    rows[4][1] = '高等数学\n(必修)\n张伟\n2-17([周])[01-02节]\n东校区仁智楼A207'
    rows[4][2] = '大学英语\n李华\n1-16([周])[01-02节]\n东校区外语楼B301'
    rows[4][3] = ('程序设计基础\n王芳\n1-8([周])[01-02节]\n东校区机房C102\n\n'
                  '程序设计实验\n王芳\n9-16([周])[01-02节]\n东校区机房C102')
    rows[6][1] = '数据结构\n钱七\n2-17([周])[05-06节]\n东校区云海楼208'
    rows[6][2] = '概率论\n孙丽\n1-16([周])[05-06节]\n东校区仁智楼A101'
    rows[8][2] = '编译原理\n吴九\n2-17([周])[09-10节]\n东校区仁智楼A305'
    if odd_even:
        rows[4][4] = '体育\n赵强\n1-15([单周])[01-02节]\n东校区体育馆'
    if weeks_only:
        rows[7][3] = '形势与政策\n周八\n3,5,7,9([双周])\n东校区行政楼D201'
    if no_weeks:
        rows[8][4] = '军事理论\n郑十\n东校区行政楼D101'
    return rows


def parse(rows, **kw):
    kw.setdefault('start', '2026-08-31')
    return convert_xls.parse_sheet(rows, **kw)


def by_name(result, name):
    for c in result['courses']:
        if c['name'] == name:
            return c
    return None


class MaskTeacherTest(unittest.TestCase):
    def test_single_char_surname(self):
        self.assertEqual(convert_xls.mask_teacher('张伟'), '张老师')

    def test_two_char_name(self):
        self.assertEqual(convert_xls.mask_teacher('王芳'), '王老师')

    def test_compound_surname_kept_whole(self):
        self.assertEqual(convert_xls.mask_teacher('欧阳修'), '欧阳老师')
        self.assertEqual(convert_xls.mask_teacher('司马光'), '司马老师')

    def test_compound_surname_alone_is_not_split(self):
        # 「欧阳」两个字就是全名时不能取首字，否则变成「欧老师」
        self.assertEqual(convert_xls.mask_teacher('欧阳'), '欧老师')

    def test_multiple_teachers(self):
        self.assertEqual(convert_xls.mask_teacher('张伟、李华'), '张老师、李老师')
        self.assertEqual(convert_xls.mask_teacher('张伟,李华'), '张老师、李老师')

    def test_empty_and_none(self):
        self.assertEqual(convert_xls.mask_teacher(''), '')
        self.assertEqual(convert_xls.mask_teacher(None), '')

    def test_no_full_name_survives(self):
        for full in ('张伟', '陈静', '孙丽'):
            self.assertNotIn(full, convert_xls.mask_teacher(full))


class WeekNumberTest(unittest.TestCase):
    def test_cn_to_int(self):
        self.assertEqual(convert_xls.cn_to_int('一'), 1)
        self.assertEqual(convert_xls.cn_to_int('十'), 10)
        self.assertEqual(convert_xls.cn_to_int('十二'), 12)
        self.assertEqual(convert_xls.cn_to_int('二十'), 20)
        self.assertEqual(convert_xls.cn_to_int('07'), 7)
        self.assertIsNone(convert_xls.cn_to_int('见课表'))
        self.assertIsNone(convert_xls.cn_to_int(''))

    def test_week_number_variants(self):
        self.assertEqual(convert_xls._week_number('第三周'), 3)
        self.assertEqual(convert_xls._week_number('第3周'), 3)
        self.assertEqual(convert_xls._week_number('15'), 15)


class WeekRangeTest(unittest.TestCase):
    def test_plain_range(self):
        weeks, kind = convert_xls.parse_week_info('2-5([周])')
        self.assertEqual(weeks, [2, 3, 4, 5])
        self.assertEqual(kind, 'all')

    def test_odd_range_expanded_to_effective_weeks(self):
        # 区间 + 单周 → 直接展开成生效周次，否则引擎只看 weeks、单周课会每周都上
        weeks, kind = convert_xls.parse_week_info('1-9([单周])')
        self.assertEqual(weeks, [1, 3, 5, 7, 9])
        self.assertEqual(kind, 'odd')

    def test_even_range_expanded(self):
        weeks, kind = convert_xls.parse_week_info('1-8([双周])')
        self.assertEqual(weeks, [2, 4, 6, 8])
        self.assertEqual(kind, 'even')

    def test_enumeration_with_even_marker_is_kept(self):
        # 枚举本身就是生效周次，再筛一次奇偶会把整个列表筛空
        weeks, kind = convert_xls.parse_week_info('3,5,7,9([双周])')
        self.assertEqual(weeks, [3, 5, 7, 9])
        self.assertEqual(kind, 'even')

    def test_reversed_range_warns_and_yields_nothing(self):
        diags = []
        weeks, _ = convert_xls.parse_week_info('5-2([周])', diags, row=4, col=1, sheet='S')
        self.assertEqual(weeks, [])
        self.assertEqual([d.code for d in diags], ['cell.week_range_reversed'])
        self.assertEqual(diags[0].cell, 'R5C2')
        self.assertEqual(diags[0].severity, convert_xls.WARNING)

    def test_out_of_range_warns_but_keeps_value(self):
        diags = []
        weeks, _ = convert_xls.parse_week_info('1-99([周])', diags, row=0, col=0)
        self.assertIn(99, weeks)
        self.assertEqual(diags[0].code, 'cell.week_out_of_range')

    def test_range_with_chinese_numbers(self):
        weeks, _ = convert_xls.parse_week_info('第三周-第五周([周])')
        self.assertEqual(weeks, [3, 4, 5])


class CellTest(unittest.TestCase):
    def test_full_cell(self):
        got = convert_xls.parse_cell('数据结构\n钱七\n2-17([周])[05-06节]\n东校区云海楼208')
        self.assertEqual(len(got), 1)
        c = got[0]
        self.assertEqual(c['name'], '数据结构')
        self.assertEqual(c['teacher'], '钱七')
        self.assertEqual(c['location'], '东校区云海楼208')
        self.assertEqual((c['startPeriod'], c['endPeriod']), (5, 6))
        self.assertEqual(c['weeks'][0], 2)

    def test_note_line(self):
        got = convert_xls.parse_cell('高等数学\n(必修)\n张伟\n2-3([周])[01-02节]\nA207')
        self.assertEqual(got[0]['note'], '必修')

    def test_two_courses_in_one_cell(self):
        got = convert_xls.parse_cell(
            '程序设计基础\n王芳\n1-8([周])[01-02节]\n机房C102\n\n'
            '程序设计实验\n王芳\n9-16([周])[01-02节]\n机房C102')
        self.assertEqual([c['name'] for c in got], ['程序设计基础', '程序设计实验'])
        self.assertEqual(got[1]['weeks'][0], 9)

    def test_weeks_without_period_is_recognised(self):
        got = convert_xls.parse_cell('形势与政策\n周八\n3,5,7,9([双周])\n行政楼D201')
        self.assertEqual(got[0]['weeks'], [3, 5, 7, 9])
        self.assertEqual(got[0]['weekType'], 'even')
        self.assertIsNone(got[0]['startPeriod'])

    def test_course_name_with_zhou_is_not_mistaken_for_weeks(self):
        got = convert_xls.parse_cell('周易研究\n孔子\n1-8([周])[01-02节]\nA101')
        self.assertEqual(got[0]['name'], '周易研究')
        self.assertEqual(got[0]['weeks'], list(range(1, 9)))

    def test_empty_cell(self):
        self.assertEqual(convert_xls.parse_cell(''), [])
        self.assertEqual(convert_xls.parse_cell(None), [])

    def test_no_name_block_is_dropped_with_warning(self):
        diags = []
        got = convert_xls.parse_cell('(只有备注)\n东校区A101', diags=diags, row=0, col=0)
        self.assertEqual(got, [])
        self.assertIn('cell.no_name', [d.code for d in diags])


class SheetTest(unittest.TestCase):
    def test_geometry(self):
        r = parse(demo_rows(odd_even=False))
        self.assertEqual(r['meta']['totalSlots'], 7)
        self.assertEqual(r['meta']['totalCourses'], 7)
        ds = by_name(r, '数据结构')
        self.assertEqual((ds['day'], ds['startPeriod'], ds['endPeriod']), (1, 5, 6))
        self.assertEqual(by_name(r, '编译原理')['startPeriod'], 9)

    def test_meta_extracted(self):
        r = parse(demo_rows())
        self.assertIn('示例大学', r['meta']['student'])
        self.assertIn('计算机2301', r['meta']['semester'])
        self.assertEqual(r['meta']['semesterStart'], '2026-08-31')

    def test_print_date_used_with_warning(self):
        diags = []
        r = convert_xls.parse_sheet(demo_rows(), diags=diags)   # 不给 start
        self.assertEqual(r['meta']['semesterStart'], '2026-11-01')
        self.assertIn('meta.print_date_used', [d.code for d in diags])

    def test_missing_header_is_error_with_diagnostic(self):
        diags = []
        r = convert_xls.parse_sheet([[B] * 8 for _ in range(5)], diags=diags)
        self.assertIn('error', r)
        self.assertEqual(diags[0].code, 'header.not_found')
        self.assertEqual(diags[0].severity, convert_xls.ERROR)

    def test_missing_period_rows_is_error(self):
        rows = demo_rows()
        for r in rows[4:]:
            r[0] = '上午'
        diags = []
        out = convert_xls.parse_sheet(rows, diags=diags)
        self.assertIn('error', out)
        self.assertIn('periods.not_found', [d.code for d in diags])

    def test_no_results_without_diags_list(self):
        # 不传 diags 时不能因为收集诊断而炸
        r = parse(demo_rows())
        self.assertEqual(r['meta']['totalSlots'], 8)

    def test_mask_teachers(self):
        r = parse(demo_rows(), mask_teachers=True)
        self.assertEqual(by_name(r, '数据结构')['teacher'], '钱老师')
        self.assertTrue(r['meta']['teacherMasked'])


class LayoutTest(unittest.TestCase):
    def test_weekday_labels_variant(self):
        rows = demo_rows()
        rows[3] = [B, '周一', '周二', '周三', '周四', '周五', '周六', '周日']
        self.assertEqual(parse(rows)['meta']['totalSlots'], 8)

    def test_english_labels_via_custom_layout(self):
        rows = demo_rows()
        rows[3] = [B, 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        layout = {'header': {'labels': {'Mon': 1, 'Tue': 2, 'Wed': 3, 'Thu': 4,
                                        'Fri': 5, 'Sat': 6, 'Sun': 7}}}
        self.assertEqual(convert_xls.parse_sheet(rows, layout=layout, start='2026-08-31')
                         ['meta']['totalSlots'], 8)

    def test_sub_periods_three(self):
        # 每个大节 3 小节：第一大节=1-3，第二大节=4-6 ……
        layout = {'periods': {'subPeriods': 3}}
        rows = demo_rows(odd_even=False)
        rows[6][1] = '数据结构\n钱七\n2-17([周])[04-06节]\n东校区云海楼208'
        r = convert_xls.parse_sheet(rows, layout=layout, start='2026-08-31')
        ds = by_name(r, '数据结构')
        self.assertEqual((ds['startPeriod'], ds['endPeriod']), (4, 6))

    def test_explicit_period_rows(self):
        layout = {'periods': {'rows': [6]}}      # 只认第三大节那一行
        r = convert_xls.parse_sheet(demo_rows(odd_even=False), layout=layout, start='2026-08-31')
        self.assertEqual(r['meta']['totalSlots'], 2)
        self.assertEqual({c['startPeriod'] for c in r['courses']}, {5})

    def test_partial_layout_deep_merges(self):
        layout = convert_xls.load_layout({'meta': {'scanRows': 5}})
        self.assertEqual(layout['meta']['scanRows'], 5)
        self.assertEqual(layout['periods']['subPeriods'], 2)     # 其余保持不变
        self.assertIn('labels', layout['header'])

    def test_layout_from_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'layout.json')
            with open(path, 'w', encoding='utf-8') as f:
                json.dump({'periods': {'subPeriods': 3}}, f)
            layout = convert_xls.load_layout(path)
            self.assertEqual(layout['periods']['subPeriods'], 3)

    def test_dump_layout_roundtrips(self):
        text = convert_xls.dump_layout()
        self.assertEqual(json.loads(text)['version'], 1)
        self.assertEqual(convert_xls.load_layout(json.loads(text)), convert_xls.DEFAULT_LAYOUT)


class RegressionTest(unittest.TestCase):
    """锁住标准导出格式下的输出，防止重构悄悄改语义。"""

    def test_slots_snapshot(self):
        r = parse(demo_rows(odd_even=False))
        got = [(c['name'], c['day'], c['startPeriod'], c['endPeriod'],
                c['weekType'], c['weeks'], c['teacher'], c['location'], c['note'])
               for c in r['courses']]
        self.assertEqual(got, [
            ('高等数学', 1, 1, 2, 'all', list(range(2, 18)), '张伟', '东校区仁智楼A207', '必修'),
            ('大学英语', 2, 1, 2, 'all', list(range(1, 17)), '李华', '东校区外语楼B301', ''),
            ('程序设计基础', 3, 1, 2, 'all', list(range(1, 9)), '王芳', '东校区机房C102', ''),
            ('程序设计实验', 3, 1, 2, 'all', list(range(9, 17)), '王芳', '东校区机房C102', ''),
            ('数据结构', 1, 5, 6, 'all', list(range(2, 18)), '钱七', '东校区云海楼208', ''),
            ('概率论', 2, 5, 6, 'all', list(range(1, 17)), '孙丽', '东校区仁智楼A101', ''),
            ('编译原理', 2, 9, 10, 'all', list(range(2, 18)), '吴九', '东校区仁智楼A305', ''),
        ])

    def test_odd_week_course_is_snapshot(self):
        r = parse(demo_rows(odd_even=True))
        pe = by_name(r, '体育')
        self.assertEqual(pe['weekType'], 'odd')
        self.assertEqual(pe['weeks'], [1, 3, 5, 7, 9, 11, 13, 15])

    def test_period_in_other_great_section_keeps_declared(self):
        # 第五大节行里写了 [09-10节]，与所在大节一致，不该被改写
        r = parse(demo_rows(odd_even=False))
        self.assertEqual(by_name(r, '编译原理')['startPeriod'], 9)

    def test_ambiguous_period_follows_row_and_warns(self):
        rows = demo_rows(odd_even=False)
        rows[8][2] = '编译原理\n吴九\n2-17([周])[01-02节]\n东校区仁智楼A305'
        diags = []
        r = convert_xls.parse_sheet(rows, diags=diags, start='2026-08-31')
        c = by_name(r, '编译原理')
        self.assertEqual((c['startPeriod'], c['endPeriod']), (9, 10))
        self.assertIn('cell.period_ambiguous', [d.code for d in diags])


class CliTest(unittest.TestCase):
    """CLI 层：退出码、报告文件、print-layout。"""

    def _run(self, argv, rows):
        import io
        import contextlib
        from unittest import mock
        buf = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            # main() 会先检查文件存在，但读文件被替换掉了，给个空壳就行
            fake = os.path.join(tmp, '课表.xls')
            with open(fake, 'w', encoding='utf-8'):
                pass
            argv = [fake if a == '课表.xls' else a for a in argv]
            with mock.patch.object(convert_xls, 'read_sheet',
                                   return_value=(rows, '学生个人课表')), \
                    mock.patch.object(sys, 'argv', ['convert_xls.py'] + argv), \
                    contextlib.redirect_stdout(buf):
                code = convert_xls.main()
        return code, buf.getvalue()

    def test_print_layout_is_json(self):
        code, out = self._run(['--print-layout'], [])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)['version'], 1)

    def test_clean_run_exits_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, 'mine.json')
            code, text = self._run(['课表.xls', '--start', '2026-08-31', '--out', out],
                                   demo_rows(odd_even=False))
            self.assertEqual(code, 0)
            self.assertIn('转换成功', text)
            self.assertTrue(os.path.exists(out))

    def test_warning_without_strict_still_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, _ = self._run(['课表.xls', '--start', '2026-08-31',
                                 '--out', os.path.join(tmp, 'a.json')],
                                demo_rows(no_weeks=True))
            self.assertEqual(code, 0)

    def test_strict_turns_warning_into_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, _ = self._run(['课表.xls', '--start', '2026-08-31', '--strict',
                                 '--out', os.path.join(tmp, 'a.json')],
                                demo_rows(no_weeks=True))
            self.assertEqual(code, 2)

    def test_report_file_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, 'a.json')
            rep = os.path.join(tmp, 'report.json')
            self._run(['课表.xls', '--start', '2026-08-31', '--out', out, '--report', rep],
                      demo_rows(no_weeks=True))
            with open(rep, encoding='utf-8') as f:
                data = json.load(f)
            self.assertEqual(data['summary']['total'], 1)
            self.assertEqual(data['diagnostics'][0]['code'], 'cell.no_week_info')
            self.assertTrue(data['diagnostics'][0]['cell'].startswith('R'))


if __name__ == '__main__':
    unittest.main()
