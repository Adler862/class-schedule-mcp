# -*- coding: utf-8 -*-
"""重构回归测试：today_schedule 的输出必须逐字不变。

快照在重构前生成，用于锁住 MCP 侧看到的行为。
"""
import os
import sys
import unittest
import io
import contextlib

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'src'))
sys.path.insert(0, ROOT)

import today_schedule  # noqa: E402

GOLDEN_DIR = os.path.join(ROOT, 'tests', 'golden')
DATES = ['2026-10-31', '2026-11-02', '2026-11-03']


def _read_golden(date):
    path = os.path.join(GOLDEN_DIR, f'today_{date}.txt')
    with open(path, 'r', encoding='utf-8', newline='') as f:
        return f.read().replace('\r\n', '\n')


class TodayScheduleCompatTest(unittest.TestCase):
    def test_output_matches_golden(self):
        import datetime
        for d in DATES:
            with self.subTest(date=d):
                got = today_schedule.generate(datetime.date.fromisoformat(d))
                self.assertEqual(
                    got.replace('\r\n', '\n').strip(),
                    _read_golden(d).strip(),
                    f'{d} 的输出与重构前快照不一致',
                )


if __name__ == '__main__':
    unittest.main()
