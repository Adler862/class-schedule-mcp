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


class ResponseSemanticsTest(unittest.TestCase):
    """HTTP 语义层：ETag / 304 / gzip。内容逻辑仍在 handle，这里只测协议行为。"""

    def rsp(self, path, headers=None, method='GET', query=None, body=None):
        q = {k: [v] for k, v in (query or {}).items()}
        return webapp.respond(method, path, q, body, headers=headers or {}, root=ROOT)

    def test_get_has_etag_and_no_cache(self):
        status, headers, _ = self.rsp('/api/meta')
        self.assertEqual(status, 200)
        self.assertTrue(headers['ETag'].startswith('"'))
        self.assertEqual(headers['Cache-Control'], 'no-cache')
        self.assertEqual(headers['Vary'], 'Accept-Encoding')

    def test_etag_is_stable_and_content_addressed(self):
        a = self.rsp('/api/meta')[1]['ETag']
        b = self.rsp('/api/meta')[1]['ETag']
        self.assertEqual(a, b)
        # 内容不同 → 指纹不同（同一接口换参数）
        c = self.rsp('/api/week', query={'week': '3'})[1]['ETag']
        d = self.rsp('/api/week', query={'week': '4'})[1]['ETag']
        self.assertNotEqual(c, d)

    def test_if_none_match_returns_304_without_body(self):
        etag = self.rsp('/api/meta')[1]['ETag']
        status, headers, payload = self.rsp('/api/meta', {'If-None-Match': etag})
        self.assertEqual(status, 304)
        self.assertEqual(payload, b'')
        self.assertEqual(headers['ETag'], etag)

    def test_stale_if_none_match_returns_200(self):
        status, _, payload = self.rsp('/api/meta', {'If-None-Match': '"deadbeef"'})
        self.assertEqual(status, 200)
        self.assertTrue(payload)

    def test_header_lookup_is_case_insensitive(self):
        etag = self.rsp('/api/meta')[1]['ETag']
        # 普通 dict 传小写键，也要能命中
        status, _, _ = self.rsp('/api/meta', {'if-none-match': etag})
        self.assertEqual(status, 304)

    def test_gzip_for_large_payload(self):
        status, headers, payload = self.rsp('/api/export.ics', {'Accept-Encoding': 'gzip'})
        self.assertEqual(status, 200)
        self.assertEqual(headers.get('Content-Encoding'), 'gzip')
        import gzip
        self.assertIn(b'BEGIN:VCALENDAR', gzip.decompress(payload))

    def test_no_gzip_when_client_does_not_ask(self):
        _, headers, payload = self.rsp('/api/export.ics')
        self.assertNotIn('Content-Encoding', headers)
        self.assertIn(b'BEGIN:VCALENDAR', payload)

    def test_small_payload_not_gzipped(self):
        _, headers, _ = self.rsp('/healthz', {'Accept-Encoding': 'gzip'})
        self.assertNotIn('Content-Encoding', headers)

    def test_write_request_gets_etag_but_never_304(self):
        # 写请求不该被客户端缓存：即使带了 If-None-Match 也必须是完整响应。
        # 用一个非法 action 触发 400，避免测试动到真实的 config/overrides.json
        body = json.dumps({'action': 'nope'}).encode('utf-8')
        status, headers, payload = self.rsp('/api/overrides', {'If-None-Match': '"x"'},
                                            method='POST', body=body)
        self.assertEqual(status, 400)
        self.assertNotEqual(status, 304)
        self.assertIn('ETag', headers)
        self.assertTrue(payload)


if __name__ == '__main__':
    unittest.main()
