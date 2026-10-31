# -*- coding: utf-8 -*-
"""Web API 层测试（先写测试，模块尚未存在 → 预期 RED）。"""
import os
import sys
import json
import datetime
import unittest
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'src'))

import webapp  # noqa: E402

TODAY = datetime.date(2026, 10, 31)   # 周六，第 9 周


def call(path, query=None, method='GET', body=None):
    q = {k: [v] for k, v in (query or {}).items()}
    status, ctype, payload = webapp.handle(method, path, q, body, root=ROOT)
    return status, ctype, payload


def call_json(path, query=None, method='GET', body=None):
    status, ctype, payload = call(path, query, method, body)
    return status, json.loads(payload.decode('utf-8'))


class HealthAndStaticTest(unittest.TestCase):
    def test_healthz(self):
        status, ctype, payload = call('/healthz')
        self.assertEqual(status, 200)
        self.assertEqual(payload, b'ok')

    def test_index_served(self):
        status, ctype, payload = call('/')
        self.assertEqual(status, 200)
        self.assertIn('text/html', ctype)
        self.assertIn(b'<!DOCTYPE html>', payload)

    def test_unknown_path_404(self):
        status, ctype, payload = call('/api/nope')
        self.assertEqual(status, 404)


class MetaApiTest(unittest.TestCase):
    def test_meta_fields(self):
        status, data = call_json('/api/meta')
        self.assertEqual(status, 200)
        for key in ('student', 'className', 'semesterStart', 'today',
                    'currentWeek', 'weekday', 'totalCourses'):
            self.assertIn(key, data)
        self.assertIsInstance(data['currentWeek'], int)
        self.assertEqual(data['semesterStart'], '2026-08-31')
        self.assertEqual(data['totalCourses'], 8)


class WeekApiTest(unittest.TestCase):
    def test_week_by_number(self):
        status, data = call_json('/api/week', {'week': '10'})
        self.assertEqual(status, 200)
        self.assertEqual(data['week'], 10)
        self.assertEqual(len(data['days']), 7)
        self.assertEqual(sum(len(d['courses']) for d in data['days']), 7)

    def test_week_dates_are_consecutive_from_monday(self):
        _, data = call_json('/api/week', {'week': '10'})
        dates = [datetime.date.fromisoformat(d['date']) for d in data['days']]
        self.assertEqual(dates[0].isoweekday(), 1)
        self.assertEqual((dates[-1] - dates[0]).days, 6)

    def test_week_defaults_to_current(self):
        status, data = call_json('/api/week')
        self.assertEqual(status, 200)
        self.assertIn('week', data)
        self.assertGreaterEqual(data['week'], 0)

    def test_bad_week_returns_400(self):
        status, _ = call_json('/api/week', {'week': 'abc'})
        self.assertEqual(status, 400)


class TodayApiTest(unittest.TestCase):
    def test_today_with_date(self):
        status, data = call_json('/api/today', {'date': '2026-11-02'})
        self.assertEqual(status, 200)
        self.assertEqual(data['week'], 10)
        self.assertEqual(data['weekday'], '周一')
        self.assertEqual(len(data['courses']), 2)

    def test_today_bad_date_returns_400(self):
        status, _ = call_json('/api/today', {'date': '2026-13-99'})
        self.assertEqual(status, 400)


class AskIntentTest(unittest.TestCase):
    def ask(self, q):
        status, data = call_json('/api/ask', {'q': q})
        self.assertEqual(status, 200)
        self.assertIn('intent', data)
        self.assertIn('text', data)
        return data

    def test_today_intent(self):
        self.assertEqual(self.ask('今天有什么课')['intent'], 'today')

    def test_tomorrow_intent(self):
        d = self.ask('明天几节课')
        self.assertEqual(d['intent'], 'day')
        self.assertIn('明天', d['text'])

    def test_weekday_intent(self):
        self.assertEqual(self.ask('周三有课吗')['intent'], 'day')

    def test_week_intent(self):
        self.assertEqual(self.ask('本周课表')['intent'], 'week')

    def test_next_intent(self):
        self.assertEqual(self.ask('下一节是什么课')['intent'], 'next')

    def test_free_intent(self):
        self.assertEqual(self.ask('哪天空')['intent'], 'free')

    def test_course_intent(self):
        d = self.ask('数据结构什么时候上')
        self.assertEqual(d['intent'], 'course')
        self.assertIn('数据结构', d['text'])

    def test_help_intent(self):
        self.assertEqual(self.ask('帮助')['intent'], 'help')

    def test_unknown_intent(self):
        self.assertEqual(self.ask('今天天气不错')['intent'], 'unknown')

    def test_empty_query(self):
        status, data = call_json('/api/ask')
        self.assertEqual(status, 200)
        self.assertEqual(data['intent'], 'help')


class IcsExportTest(unittest.TestCase):
    def setUp(self):
        status, ctype, payload = call('/api/export.ics')
        self.assertEqual(status, 200)
        self.assertIn('text/calendar', ctype)
        self.text = payload.decode('utf-8')

    def test_calendar_envelope(self):
        self.assertTrue(self.text.startswith('BEGIN:VCALENDAR'))
        self.assertIn('END:VCALENDAR', self.text)

    def test_one_event_per_course(self):
        self.assertEqual(self.text.count('BEGIN:VEVENT'), 8)

    def test_dtstart_is_local_floating_time(self):
        # 样例课表的显式 weeks 从第 2 周开始 → 第 2 周周一是 2026-09-07
        self.assertIn('DTSTART:20260907T083000', self.text)

    def test_odd_week_course_has_biweekly_rule(self):
        # 计算机网络是单周课，必须以两周为间隔重复
        block = self.text.split('BEGIN:VEVENT')
        target = [b for b in block if '计算机网络' in b]
        self.assertTrue(target, 'ICS 里应当有计算机网络')
        self.assertIn('INTERVAL=2', target[0])

    def test_line_endings_are_crlf(self):
        self.assertIn('\r\n', self.text)


if __name__ == '__main__':
    unittest.main()
