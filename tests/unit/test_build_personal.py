# -*- coding: utf-8 -*-
"""个人页构建脚本测试。

重点是两条构建命令之间的耦合：3D 的 `--index` 必须等于 2D 的文件名。
这个错一旦发生，用户在浏览器里点到的就是 404，而单测以外没人拦得住。
"""
import io
import os
import sys
import tempfile
import contextlib
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

import build_personal  # noqa: E402


class PlanTest(unittest.TestCase):
    def test_href_equals_html_filename(self):
        p = build_personal.plan('mine.json', 'dist', '我的课表')
        self.assertEqual(p['href'], '我的课表.html')
        self.assertTrue(p['html'].endswith('我的课表.html'))
        # 两个产物必须同目录，否则相对链接会跨目录
        self.assertEqual(os.path.dirname(p['html']), os.path.dirname(p['three']))

    def test_name_with_extension_normalised(self):
        self.assertEqual(build_personal.plan('m.json', 'dist', '课表.html')['href'],
                         '课表.html')

    def test_absolute_out_dir_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = build_personal.plan('m.json', tmp, 'x')
            self.assertEqual(os.path.dirname(p['html']), tmp)


class CheckLinkTest(unittest.TestCase):
    def test_missing_link_is_detected(self):
        fd, path = tempfile.mkstemp(suffix='.html')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write('<a href="index.html?w=1">')
            self.assertFalse(build_personal.check_link(path, '我的课表.html'))
            self.assertTrue(build_personal.check_link(path, 'index.html'))
        finally:
            os.unlink(path)

    def test_missing_file_is_false_not_crash(self):
        self.assertFalse(build_personal.check_link('/definitely/not/here.html', 'x.html'))


class MainWiringTest(unittest.TestCase):
    """不真跑子进程，只验证传下去的参数对不对。"""

    def test_index_matches_2d_filename(self):
        with tempfile.TemporaryDirectory() as tmp:
            courses = os.path.join(tmp, 'mine.json')
            with open(courses, 'w', encoding='utf-8') as f:
                f.write('{"meta":{},"courses":[]}')

            out = os.path.join(tmp, 'dist')
            os.makedirs(out)
            # 3D 产物里带着正确的链接，自检才能过
            with open(os.path.join(out, '3d.html'), 'w', encoding='utf-8') as f:
                f.write('<a id="wsFull" href="我的课表.html?w=1">')

            calls = []

            def fake_run(cmd, cwd=None, quiet=False):
                calls.append(cmd)
                return ''

            with mock.patch.object(build_personal, 'run', fake_run), \
                    mock.patch.object(build_personal.shutil, 'which',
                                      return_value='/fake/node'), \
                    mock.patch.object(build_personal.os.path, 'isdir',
                                      return_value=True), \
                    mock.patch.object(build_personal, 'REPO_ROOT', tmp):
                with contextlib.redirect_stdout(io.StringIO()):
                    code = build_personal.main(['--courses', courses, '--name', '我的课表'])

            self.assertEqual(code, 0)
            self.assertEqual(len(calls), 2, '应该正好跑两条命令（2D、3D）')

            single = calls[0]
            self.assertIn('build_single.py', ' '.join(single))
            self.assertIn('--link-3d', single)

            node_cmd = calls[1]
            self.assertIn('build.mjs', ' '.join(node_cmd))
            idx = node_cmd.index('--index')
            self.assertEqual(node_cmd[idx + 1], '我的课表.html',
                             '--index 必须是 2D 页的文件名，否则点进去 404')

    def test_no_3d_skips_node(self):
        with tempfile.TemporaryDirectory() as tmp:
            courses = os.path.join(tmp, 'mine.json')
            with open(courses, 'w', encoding='utf-8') as f:
                f.write('{"meta":{},"courses":[]}')
            calls = []
            with mock.patch.object(build_personal, 'run',
                                   lambda cmd, cwd=None, quiet=False: calls.append(cmd) or ''), \
                    mock.patch.object(build_personal, 'REPO_ROOT', tmp):
                with contextlib.redirect_stdout(io.StringIO()):
                    code = build_personal.main(['--courses', courses, '--no-3d'])
            self.assertEqual(code, 0)
            self.assertEqual(len(calls), 1)


if __name__ == '__main__':
    unittest.main()
