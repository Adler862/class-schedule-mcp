# -*- coding: utf-8 -*-
"""调课例外层测试。

这一层最容易出的错是「改了定义」——把某一次调课写成学期性修改，
导致前面上过的周次跟着变。所以测试重点盯两件事：
  1. 例外只影响它指向的那一次，其它周次纹丝不动
  2. 源位置消失、目标位置出现，且问答（courses_of）也跟着变
"""
import os
import sys
import json
import tempfile
import datetime
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'src'))

import semester  # noqa: E402
import webapp  # noqa: E402

D = datetime.date

SAMPLE = {
    'meta': {'semesterStart': '2026-08-31'},
    'courses': [
        {'name': '编译原理', 'teacher': '张老师', 'location': '东校区云海楼208',
         'day': 1, 'startPeriod': 1, 'endPeriod': 2,
         'weeks': list(range(2, 18))},
        {'name': '操作系统', 'teacher': '陈老师', 'location': '东校区云海楼209',
         'day': 5, 'startPeriod': 3, 'endPeriod': 4,
         'weeks': list(range(2, 18))},
    ],
}


class OverrideBase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.courses = os.path.join(self.tmpdir, 'courses.json')
        self.ovs = os.path.join(self.tmpdir, 'overrides.json')
        with open(self.courses, 'w', encoding='utf-8') as f:
            json.dump(SAMPLE, f, ensure_ascii=False)

        self.saved = (semester.COURSES_JSON, semester.OVERRIDES_JSON)
        semester.COURSES_JSON = self.courses
        semester.OVERRIDES_JSON = self.ovs
        semester._cache.clear()

    def tearDown(self):
        semester.COURSES_JSON, semester.OVERRIDES_JSON = self.saved
        semester._cache.clear()
        for p in (self.courses, self.ovs):
            if os.path.exists(p):
                os.unlink(p)
        try:
            os.rmdir(self.tmpdir)
        except OSError:
            pass

    def names_on(self, date):
        if isinstance(date, str):
            date = D.fromisoformat(date)
        for d in semester.week_grid(semester.current_week(date), data=SAMPLE):
            if d['date'] == date.isoformat():
                return [c['name'] for c in d['courses']]
        return []


class ApplyOverridesTest(OverrideBase):
    def test_move_removes_from_source_and_adds_to_target(self):
        ov = [{'name': '编译原理', 'fromDate': '2026-10-26', 'fromPeriod': 1,
               'span': 2, 'type': 'move', 'toDate': '2026-10-30', 'toPeriod': 5}]
        self.assertEqual(self.names_on('2026-10-26'), ['编译原理'])
        semester.save_overrides(ov)
        self.assertEqual(self.names_on('2026-10-26'), [])
        # 周五本来就有操作系统（3-4 节），编译原理按 5-6 节插到后面
        self.assertEqual(self.names_on('2026-10-30'), ['操作系统', '编译原理'])

    def test_source_weeks_are_untouched(self):
        semester.save_overrides([{'name': '编译原理', 'fromDate': '2026-10-26',
                                  'fromPeriod': 1, 'span': 2, 'type': 'move',
                                  'toDate': '2026-10-30', 'toPeriod': 5}])
        # 前一周、后一周都该保持原样，这是「不改定义」的核心保证
        self.assertEqual(self.names_on('2026-10-19'), ['编译原理'])
        self.assertEqual(self.names_on('2026-11-02'), ['编译原理'])

    def test_cancel_only_removes(self):
        semester.save_overrides([{'name': '编译原理', 'fromDate': '2026-10-26',
                                  'fromPeriod': 1, 'span': 2, 'type': 'cancel'}])
        self.assertEqual(self.names_on('2026-10-26'), [])
        self.assertEqual(self.names_on('2026-11-02'), ['编译原理'])

    def test_moved_block_is_marked_and_has_times(self):
        semester.save_overrides([{'name': '编译原理', 'fromDate': '2026-10-26',
                                  'fromPeriod': 1, 'span': 2, 'type': 'move',
                                  'toDate': '2026-10-30', 'toPeriod': 5,
                                  'location': '东校区云海楼208'}])
        for d in semester.week_grid(9, data=SAMPLE):
            if d['date'] == '2026-10-30':
                moved = [c for c in d['courses'] if c.get('moved')]
                self.assertEqual(len(moved), 1)
                self.assertEqual(moved[0]['start'], '14:30')
                self.assertEqual(moved[0]['end'], '16:10')
                self.assertEqual(moved[0]['room'], '208')
                return
        self.fail('没找到 2026-10-30')

    def test_courses_of_sees_the_move(self):
        semester.save_overrides([{'name': '编译原理', 'fromDate': '2026-10-26',
                                  'fromPeriod': 1, 'span': 2, 'type': 'move',
                                  'toDate': '2026-10-30', 'toPeriod': 5}])
        self.assertEqual(semester.courses_of(D(2026, 10, 26)), [])
        names = [c['name'] for c in semester.courses_of(D(2026, 10, 30))]
        self.assertIn('编译原理', names)

    def test_override_for_other_week_does_not_leak(self):
        semester.save_overrides([{'name': '编译原理', 'fromDate': '2026-10-26',
                                  'fromPeriod': 1, 'span': 2, 'type': 'move',
                                  'toDate': '2026-10-30', 'toPeriod': 5}])
        self.assertEqual(self.names_on('2026-11-02'), ['编译原理'])


class OverrideStorageTest(OverrideBase):
    def test_missing_file_means_no_overrides(self):
        self.assertEqual(semester.load_overrides(), [])

    def test_roundtrip(self):
        ov = [{'name': '编译原理', 'fromDate': '2026-10-26', 'fromPeriod': 1,
               'type': 'cancel'}]
        semester.save_overrides(ov)
        self.assertEqual(semester.load_overrides(), ov)

    def test_broken_file_does_not_crash(self):
        with open(self.ovs, 'w', encoding='utf-8') as f:
            f.write('{ not json')
        self.assertEqual(semester.load_overrides(), [])

    def test_entries_without_required_fields_are_dropped(self):
        with open(self.ovs, 'w', encoding='utf-8') as f:
            json.dump({'overrides': [{'name': 'X'}, {'fromDate': '2026-10-26'},
                                     {'name': '编译原理', 'fromDate': '2026-10-26',
                                      'fromPeriod': 1, 'type': 'cancel'}]}, f)
        self.assertEqual(len(semester.load_overrides()), 1)


class OverrideApiTest(OverrideBase):
    def post(self, payload):
        status, _, body = webapp.handle('POST', '/api/overrides', None,
                                        json.dumps(payload).encode('utf-8'), '.',
                                        today=D(2026, 10, 26))
        return status, json.loads(body.decode('utf-8'))

    def get_week(self, week):
        status, _, body = webapp.handle('GET', '/api/week', {'week': [str(week)]},
                                        None, '.', today=D(2026, 10, 26))
        return json.loads(body.decode('utf-8'))

    def test_move_then_week_reflects_it(self):
        status, data = self.post({'action': 'move', 'name': '编译原理',
                                  'fromDate': '2026-10-26', 'fromPeriod': 1,
                                  'span': 2, 'toDate': '2026-10-30', 'toPeriod': 5})
        self.assertEqual(status, 200)
        self.assertEqual(len(data['overrides']), 1)
        week = self.get_week(9)
        monday = [d for d in week['days'] if d['date'] == '2026-10-26'][0]
        friday = [d for d in week['days'] if d['date'] == '2026-10-30'][0]
        self.assertEqual(monday['courses'], [])
        self.assertIn('编译原理', [c['name'] for c in friday['courses']])

    def test_undo_restores(self):
        self.post({'action': 'move', 'name': '编译原理', 'fromDate': '2026-10-26',
                   'fromPeriod': 1, 'span': 2, 'toDate': '2026-10-30', 'toPeriod': 5})
        status, data = self.post({'action': 'undo', 'name': '编译原理',
                                  'fromDate': '2026-10-26', 'fromPeriod': 1})
        self.assertEqual(status, 200)
        self.assertEqual(data['overrides'], [])
        monday = [d for d in self.get_week(9)['days'] if d['date'] == '2026-10-26'][0]
        self.assertEqual([c['name'] for c in monday['courses']], ['编译原理'])

    def test_clear(self):
        self.post({'action': 'cancel', 'name': '编译原理',
                   'fromDate': '2026-10-26', 'fromPeriod': 1})
        status, data = self.post({'action': 'clear'})
        self.assertEqual(data['overrides'], [])
        self.assertEqual(semester.load_overrides(), [])

    def test_missing_fields_rejected(self):
        status, data = self.post({'action': 'move', 'name': '编译原理'})
        self.assertEqual(status, 400)
        self.assertIn('缺少字段', data['error'])

    def test_same_target_rejected(self):
        status, data = self.post({'action': 'move', 'name': '编译原理',
                                  'fromDate': '2026-10-26', 'fromPeriod': 1,
                                  'toDate': '2026-10-26', 'toPeriod': 1})
        self.assertEqual(status, 400)
        self.assertIn('相同', data['error'])

    def test_bad_action_rejected(self):
        status, _ = self.post({'action': 'explode'})
        self.assertEqual(status, 400)

    def test_broken_json_rejected(self):
        status, _, body = webapp.handle('POST', '/api/overrides', None, b'{oops',
                                        '.', today=D(2026, 10, 26))
        self.assertEqual(status, 400)

    def test_get_returns_list(self):
        self.post({'action': 'cancel', 'name': '编译原理',
                   'fromDate': '2026-10-26', 'fromPeriod': 1})
        status, _, body = webapp.handle('GET', '/api/overrides', None, None, '.',
                                        today=D(2026, 10, 26))
        self.assertEqual(status, 200)
        self.assertEqual(len(json.loads(body.decode('utf-8'))['overrides']), 1)


if __name__ == '__main__':
    unittest.main()
