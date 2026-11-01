# -*- coding: utf-8 -*-
"""单文件构建器测试。

重点不是「构建能跑通」，而是锁住三件容易退化的行为：
  1. 房间号提取（窄屏唯一能看到的地点信息）
  2. 颜色序号按课程名稳定分配（同课同色、异课异色）
  3. 产物必须是真自包含：没有外部链接、没有 fetch、没有占位符残留
"""
import os
import sys
import json
import tempfile
import datetime
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'src'))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

import semester  # noqa: E402
import build_single as bs  # noqa: E402


class ShortRoomTest(unittest.TestCase):
    def test_strips_campus_and_building(self):
        self.assertEqual(semester.short_room('东校区云海楼208'), '208')

    def test_keeps_letter_prefix(self):
        self.assertEqual(semester.short_room('东校区仁智楼A207'), 'A207')

    def test_handles_direction_word(self):
        self.assertEqual(semester.short_room('东校区星瀚楼南101'), '101')

    def test_empty_stays_empty(self):
        self.assertEqual(semester.short_room(''), '')
        self.assertEqual(semester.short_room(None), '')

    def test_no_number_returns_whole_string(self):
        self.assertEqual(semester.short_room('图书馆'), '图书馆')

    def test_entry_carries_room(self):
        e = semester._entry({'name': 'X', 'location': '东校区云海楼209'})
        self.assertEqual(e['room'], '209')
        self.assertEqual(e['location'], '东校区云海楼209')


SAMPLE = {
    'meta': {'semesterStart': '2026-08-31'},
    'courses': [
        {'name': '编译原理', 'location': '东校区云海楼208', 'day': 1,
         'startPeriod': 1, 'endPeriod': 2, 'weeks': list(range(2, 18))},
        {'name': '算法设计与分析', 'location': '东校区云海楼207', 'day': 2,
         'startPeriod': 1, 'endPeriod': 2, 'weeks': list(range(2, 18))},
        {'name': '编译原理', 'location': '东校区云海楼413', 'day': 3,
         'startPeriod': 7, 'endPeriod': 8, 'weeks': [3, 5, 7, 9]},
        {'name': '短课', 'day': 4, 'startPeriod': 3, 'endPeriod': 4,
         'startWeek': 1, 'totalWeeks': 4},
    ],
}


class NeededWeeksTest(unittest.TestCase):
    def test_uses_last_week_in_weeks_list(self):
        self.assertEqual(bs.needed_weeks(SAMPLE), 17)

    def test_falls_back_to_start_plus_total(self):
        data = {'courses': [{'startWeek': 3, 'totalWeeks': 10}]}
        self.assertEqual(bs.needed_weeks(data), 16)  # 3+10-1=12，但下限 16

    def test_empty_data_has_floor(self):
        self.assertEqual(bs.needed_weeks({'courses': []}), 16)

    def test_capped_at_30(self):
        data = {'courses': [{'startWeek': 1, 'totalWeeks': 60}]}
        self.assertEqual(bs.needed_weeks(data), 30)


class PaletteTest(unittest.TestCase):
    def test_same_name_gets_same_index(self):
        p = bs.build_palette(SAMPLE)
        self.assertEqual(p['编译原理'], 0)
        self.assertEqual(p['算法设计与分析'], 1)

    def test_index_follows_first_appearance(self):
        p = bs.build_palette(SAMPLE)
        self.assertEqual(list(p.keys()), ['编译原理', '算法设计与分析', '短课'])

    def test_unique_names_get_unique_index(self):
        p = bs.build_palette(SAMPLE)
        self.assertEqual(len(set(p.values())), len(p))

    def test_empty_name_skipped(self):
        self.assertEqual(bs.build_palette({'courses': [{'name': ''}]}), {})


class RenderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.NamedTemporaryFile('w', suffix='.json',
                                              delete=False, encoding='utf-8')
        json.dump(SAMPLE, cls.tmp, ensure_ascii=False)
        cls.tmp.close()
        cls.saved = semester.COURSES_JSON
        semester.COURSES_JSON = cls.tmp.name
        semester._cache.clear()
        cls.payload = bs.build_data(datetime.date(2026, 11, 2), demo=True)
        cls.html = bs.render(cls.payload)

    @classmethod
    def tearDownClass(cls):
        semester.COURSES_JSON = cls.saved
        semester._cache.clear()
        os.unlink(cls.tmp.name)

    def test_placeholder_replaced(self):
        self.assertNotIn('/*__DATA__*/null', self.html)

    def test_no_external_resources(self):
        for bad in ('http://', 'https://', 'fetch(', '<script src', '<link '):
            self.assertNotIn(bad, self.html, bad)

    def test_max_week_matches_data(self):
        self.assertEqual(self.payload['maxWeek'], 17)

    def test_palette_in_payload(self):
        self.assertEqual(self.payload['palette']['编译原理'], 0)

    def test_demo_date_is_frozen(self):
        self.assertEqual(self.payload['today'], '2026-11-02')
        self.assertEqual(self.payload['currentWeek'], 10)

    def test_without_demo_date_today_is_null(self):
        real = bs.build_data()
        self.assertIsNone(real['today'], '正常构建不能把日期写死，否则文件放久了会「卡在那天」')

    def test_weeks_cover_max_week(self):
        self.assertIn('17', self.payload['weeks'])
        self.assertNotIn('18', self.payload['weeks'])

    def test_course_room_in_grid(self):
        hits = [c for d in self.payload['weeks']['2'] for c in d['courses']]
        self.assertTrue(all('room' in c for c in hits))
        self.assertTrue(any(c['room'] == '208' for c in hits))


if __name__ == '__main__':
    unittest.main()
