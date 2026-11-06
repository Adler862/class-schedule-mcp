# -*- coding: utf-8 -*-
"""2D 明暗主题切换的静态护栏。

顺序「跟随系统 → 深色 → 浅色」是刻意的：多数人默认就是浅色，
第一下点击应该直接给深色。产物由模板生成，两边都要有。
"""
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TPL = os.path.join(ROOT, 'tools', 'single_template.html')
DOCS = os.path.join(ROOT, 'docs', 'index.html')
SCENE = os.path.join(ROOT, 'web3d', 'scene.js')
SHELL = os.path.join(ROOT, 'web3d', 'shell.html')


def read(path):
    with open(path, 'r', encoding='utf-8', newline='') as f:
        return f.read().replace('\r\n', '\n')


class ThemeTest(unittest.TestCase):

    def test_marker_in_template_and_artifact(self):
        for path in (TPL, DOCS):
            with self.subTest(path=os.path.relpath(path, ROOT)):
                self.assertIn('__THEME__', read(path))

    def test_cycle_order_is_auto_dark_light(self):
        tpl = read(TPL)
        self.assertIn("var THEME_ORDER = ['auto', 'dark', 'light'];", tpl)
        self.assertIn('THEME_KEY', tpl)

    def test_manual_overrides_beat_system_preference(self):
        tpl = read(TPL)
        media = tpl.index('@media (prefers-color-scheme:dark)')
        self.assertGreater(tpl.index('html[data-theme="light"]'), media,
                           '手动覆盖必须写在系统媒体查询之后')
        self.assertGreater(tpl.index('html[data-theme="dark"]'), media)
        self.assertIn('color-scheme:light', tpl)
        self.assertIn('color-scheme:dark', tpl)

    def test_no_flash_on_load(self):
        """主题要在首帧前落到 <html data-theme>，否则深色用户会先闪一下白。"""
        tpl = read(TPL)
        head = tpl[:tpl.index('</head>')]
        self.assertIn("document.documentElement.dataset.theme = m", head)

    def test_button_stays_discreet(self):
        tpl = read(TPL)
        self.assertIn('width:26px;height:26px', tpl)
        self.assertIn('opacity:.55', tpl)
        self.assertIn('id="themeBtn"', tpl)

    def test_3d_keeps_its_own_paper_palette(self):
        for path in (SCENE, SHELL):
            with self.subTest(path=os.path.relpath(path, ROOT)):
                self.assertNotIn('themeBtn', read(path))


if __name__ == '__main__':
    unittest.main()
