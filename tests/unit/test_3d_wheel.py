# -*- coding: utf-8 -*-
"""3D 档案架「滚轮切周」的静态护栏。

docs/3d.html 是 web3d/build.mjs 把 scene.js + three 打进 shell.html 的产物，
只改产物的话下次构建就会丢，所以源码和产物都要锁住。
"""
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCENE = os.path.join(ROOT, 'web3d', 'scene.js')
SHELL = os.path.join(ROOT, 'web3d', 'shell.html')
ARTIFACT = os.path.join(ROOT, 'docs', '3d.html')


def read(path):
    with open(path, 'r', encoding='utf-8', newline='') as f:
        return f.read().replace('\r\n', '\n')


class WheelWeekTest(unittest.TestCase):

    def test_scene_registers_throttled_wheel_handler(self):
        s = read(SCENE)
        self.assertIn("addEventListener('wheel'", s)
        self.assertIn('WHEEL_STEP', s)
        self.assertIn('WHEEL_COOLDOWN', s)
        self.assertIn('WHEEL_IDLE', s)
        self.assertIn('select(selected + dir)', s)
        self.assertIn('{ passive: false }', s, '要 preventDefault 就必须非 passive')

    def test_wheel_works_in_rack_and_on_the_pulled_out_sheet(self):
        """档案架态和抽出课表纸态都要能滚；select() 会顺带换纸上的内容。"""
        s = read(SCENE)
        self.assertIn('if (ev.ctrlKey) return;', s)
        self.assertNotIn('if (sheetOpen || ev.ctrlKey) return;', s,
                          '不能用 sheetOpen 把滚轮挡在课表纸外面')
        self.assertIn('if (sheetOpen && nextWeek !== lastSheetWeek) openWeekSheet(nextWeek);', s)

    def test_wheel_does_not_hijack_scrollable_table_or_zoom(self):
        """能滚的表格容器要留给它自己，Ctrl+滚轮是浏览器缩放，横滑不算切周。"""
        s = read(SCENE)
        self.assertIn(".tbody, .twrap", s)
        self.assertIn('Math.abs(ev.deltaX) > Math.abs(ev.deltaY)', s)
        self.assertIn('ev.deltaMode', s, '行/页模式的 deltaY 要折算成像素')

    def test_artifact_has_the_bundled_handler_and_hint(self):
        a = read(ARTIFACT)
        self.assertIn('addEventListener("wheel"', a, '产物里必须有打包后的 wheel 监听')
        self.assertIn('滚轮', a, '右下键位提示要告诉用户能滚轮切周')

    def test_hint_present_in_shell(self):
        self.assertIn('<kbd>滚轮</kbd>', read(SHELL))


if __name__ == '__main__':
    unittest.main()
