# -*- coding: utf-8 -*-
"""学期引擎测试（先写测试，模块尚未存在 → 预期 RED）。"""
import os
import sys
import datetime
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'src'))

import semester  # noqa: E402

D = datetime.date


class ResolveStartTest(unittest.TestCase):
    def test_monday_is_taken_as_is(self):
        self.assertEqual(semester.snap_to_monday(D(2026, 9, 7)), D(2026, 9, 7))

    def test_thursday_snaps_back_to_monday(self):
        # 教务系统导出的 semesterStart 常常是打印日期（2026-09-03 是周四）
        self.assertEqual(semester.snap_to_monday(D(2026, 9, 3)), D(2026, 8, 31))

    def test_sunday_snaps_back_six_days(self):
        self.assertEqual(semester.snap_to_monday(D(2026, 9, 6)), D(2026, 8, 31))

    def test_env_override_wins(self):
        old = os.environ.get('SCHEDULE_SEMESTER_START')
        os.environ['SCHEDULE_SEMESTER_START'] = '2026-09-14'
        try:
            self.assertEqual(semester.resolve_start(), D(2026, 9, 14))
        finally:
            if old is None:
                os.environ.pop('SCHEDULE_SEMESTER_START', None)
            else:
                os.environ['SCHEDULE_SEMESTER_START'] = old


class CurrentWeekTest(unittest.TestCase):
    def test_first_day_is_week_one(self):
        self.assertEqual(semester.current_week(D(2026, 8, 31)), 1)

    def test_last_day_of_week_one(self):
        self.assertEqual(semester.current_week(D(2026, 9, 6)), 1)

    def test_second_week(self):
        self.assertEqual(semester.current_week(D(2026, 9, 7)), 2)

    def test_day_before_start_is_week_zero(self):
        self.assertEqual(semester.current_week(D(2026, 8, 30)), 0)

    def test_far_future(self):
        self.assertEqual(semester.current_week(D(2026, 11, 2)), 10)


class CourseActiveTest(unittest.TestCase):
    COURSE = {'startWeek': 1, 'totalWeeks': 20, 'weekType': 'all'}

    def test_plain_course_active_inside_range(self):
        self.assertTrue(semester.course_active(self.COURSE, 1))
        self.assertTrue(semester.course_active(self.COURSE, 20))

    def test_plain_course_inactive_after_range(self):
        self.assertFalse(semester.course_active(self.COURSE, 21))

    def test_odd_week_course(self):
        c = {'startWeek': 1, 'totalWeeks': 20, 'weekType': 'odd'}
        self.assertTrue(semester.course_active(c, 1))
        self.assertFalse(semester.course_active(c, 2))
        self.assertTrue(semester.course_active(c, 3))

    def test_even_week_course(self):
        c = {'startWeek': 1, 'totalWeeks': 20, 'weekType': 'even'}
        self.assertFalse(semester.course_active(c, 1))
        self.assertTrue(semester.course_active(c, 2))

    def test_odd_relative_to_start_week_not_absolute(self):
        c = {'startWeek': 2, 'totalWeeks': 10, 'weekType': 'odd'}
        self.assertTrue(semester.course_active(c, 2))   # 相对第 1 周
        self.assertFalse(semester.course_active(c, 3))  # 相对第 2 周

    def test_explicit_weeks_list_wins(self):
        c = {'startWeek': 1, 'totalWeeks': 20, 'weekType': 'all', 'weeks': [2, 5, 9]}
        self.assertTrue(semester.course_active(c, 5))
        self.assertFalse(semester.course_active(c, 3))


class PeriodTimeTest(unittest.TestCase):
    def test_first_two_periods(self):
        self.assertEqual(semester.period_time(1, 2), '08:30–10:10')

    def test_periods_seven_eight(self):
        self.assertEqual(semester.period_time(7, 8), '16:30–18:10')

    def test_unknown_period_returns_empty(self):
        self.assertEqual(semester.period_time(99, 100), '')


class CoursesOfTest(unittest.TestCase):
    def test_saturday_has_no_class(self):
        self.assertEqual(semester.courses_of(D(2026, 10, 31)), [])

    def test_monday_courses_sorted_by_start_period(self):
        got = semester.courses_of(D(2026, 11, 2))
        self.assertEqual([c['name'] for c in got], ['数据结构', '计算机组成原理'])
        self.assertEqual([c['startPeriod'] for c in got], [1, 3])

    def test_course_entry_shape(self):
        c = semester.courses_of(D(2026, 11, 2))[0]
        for key in ('name', 'teacher', 'location', 'startPeriod', 'endPeriod', 'start', 'end'):
            self.assertIn(key, c, f'课表条目缺少字段 {key}')
        self.assertEqual(c['start'], '08:30')
        self.assertEqual(c['end'], '10:10')

    def test_odd_week_course_hidden_in_even_week(self):
        # 周二 5-6 节在样例里是单周课；第 10 周应不可见
        names = [c['name'] for c in semester.courses_of(D(2026, 11, 3))]
        self.assertNotIn('计算机网络', names)


class WeekGridTest(unittest.TestCase):
    def test_grid_has_seven_days(self):
        grid = semester.week_grid(10)
        self.assertEqual(len(grid), 7)

    def test_grid_dates_are_consecutive_monday_first(self):
        grid = semester.week_grid(10)
        dates = [datetime.date.fromisoformat(d['date']) for d in grid]
        self.assertEqual(dates[0].isoweekday(), 1)
        self.assertEqual((dates[-1] - dates[0]).days, 6)

    def test_grid_courses_match_courses_of(self):
        grid = semester.week_grid(10)
        total = sum(len(d['courses']) for d in grid)
        self.assertEqual(total, 7, '第 10 周是双周：单周的计算机网络不生效，共 7 门')


if __name__ == '__main__':
    unittest.main()
