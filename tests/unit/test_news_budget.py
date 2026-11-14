# -*- coding: utf-8 -*-
"""新闻抓取预算测试。

这条链最怕的不是"某个源挂了"（那只是缺一块），而是"一个慢源把整次早报拖住"。
旧实现每个 future 各等 15 秒、退出时还要等所有线程收工，所以这里盯两件事：
  1. 慢源不能拖过总预算
  2. 每个源的结局（ok / error / timeout）与耗时都要能拿到，便于排查
"""
import os
import sys
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'src'))

import class_schedule_mcp as ns  # noqa: E402


def fast():
    return [{'title': '快源', 'source': 'fast'}]


def slow():
    time.sleep(1.0)
    return [{'title': '慢源', 'source': 'slow'}]


def boom():
    raise RuntimeError('这个源挂了')


class CollectNewsBudgetTest(unittest.TestCase):
    def setUp(self):
        self._saved = ns.SOURCE_FUNCS
        ns.SOURCE_FUNCS = {'fast': fast, 'slow': slow, 'boom': boom, 'off': fast}

    def tearDown(self):
        ns.SOURCE_FUNCS = self._saved

    def test_slow_source_does_not_blow_the_budget(self):
        stats = {}
        t0 = time.monotonic()
        items, failed = ns._collect_news(
            {'sources': {'fast': True, 'slow': True}}, budget=0.25, stats=stats)
        elapsed = time.monotonic() - t0

        self.assertLess(elapsed, 0.9, '不能被 1 秒的慢源拖住')
        self.assertEqual([i['title'] for i in items], ['快源'])
        self.assertEqual(failed, ['slow'])
        self.assertEqual(stats['fast'][0], 'ok')
        self.assertEqual(stats['slow'][0], 'timeout')
        self.assertGreaterEqual(stats['slow'][1], 0.2)

    def test_error_source_is_recorded_not_raised(self):
        stats = {}
        items, failed = ns._collect_news({'sources': {'boom': True}}, budget=2, stats=stats)
        self.assertEqual(items, [])
        self.assertEqual(failed, ['boom'])
        self.assertEqual(stats['boom'][0], 'error')

    def test_disabled_sources_are_not_fetched(self):
        items, failed = ns._collect_news({'sources': {'off': False, 'fast': True}}, budget=2)
        self.assertEqual([i['title'] for i in items], ['快源'])
        self.assertEqual(failed, [])

    def test_no_sources_is_not_an_error(self):
        self.assertEqual(ns._collect_news({'sources': {}}), ([], []))
        self.assertEqual(ns._collect_news({}), ([], []))

    def test_stats_is_optional(self):
        items, failed = ns._collect_news({'sources': {'fast': True}}, budget=2)
        self.assertEqual(len(items), 1)

    def test_budget_env_override(self):
        """SCHEDULE_NEWS_BUDGET 只在 import 时读一次，这里只验默认值可用。"""
        self.assertGreater(ns.NEWS_BUDGET_S, 0)
        self.assertLessEqual(ns.NEWS_BUDGET_S, 30)


if __name__ == '__main__':
    unittest.main()
