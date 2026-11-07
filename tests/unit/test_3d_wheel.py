# -*- coding: utf-8 -*-
"""3D 档案架「滚轮切周」的静态护栏与产物同步检查。

docs/3d.html 是 web3d/build.mjs 把 scene.js + three 打进 shell.html 的产物，
只改产物的话下次构建就会丢，所以源码、产物、构建幂等都要锁住。
"""
import os
import shutil
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCENE = os.path.join(ROOT, 'web3d', 'scene.js')
SHELL = os.path.join(ROOT, 'web3d', 'shell.html')
BUILD = os.path.join(ROOT, 'web3d', 'build.mjs')
ARTIFACT = os.path.join(ROOT, 'docs', '3d.html')


def read(path):
    with open(path, 'r', encoding='utf-8', newline='') as f:
        return f.read().replace('\r\n', '\n')


class WheelWeekTest(unittest.TestCase):

    def test_scene_registers_throttled_wheel_handler(self):
        s = read(SCENE)
        self.assertIn("addEventListener('wheel'", s)
        for name in ('WHEEL_STEP', 'WHEEL_COOLDOWN', 'WHEEL_IDLE'):
            self.assertIn(name, s)
        self.assertIn('{ passive: false }', s, '要 preventDefault 就必须非 passive')
        # 冷却期内必须丢掉余量，否则长惯性手势会靠攒着的 deltaY 连翻好几周
        self.assertIn('now - wheelLastFlip < WHEEL_COOLDOWN) { wheelAccum = 0; return; }', s)
        # 首尾停住，和 2D 拖拽翻周一致
        self.assertIn('if (next < 0 || next >= PERIOD) return;', s)

    def test_wheel_works_in_rack_and_on_the_pulled_out_sheet(self):
        """档案架态和抽出课表纸态都要能滚；select() 会顺带换纸上的内容。"""
        s = read(SCENE)
        self.assertIn('if (ev.ctrlKey) return;', s)
        self.assertNotIn('if (sheetOpen || ev.ctrlKey) return;', s,
                          '不能用 sheetOpen 把滚轮挡在课表纸外面')
        self.assertIn('if (sheetOpen && nextWeek !== lastSheetWeek) openWeekSheet(nextWeek);', s)

    def test_wheel_does_not_hijack_scrollable_table_or_zoom(self):
        """能滚的容器留给它自己，Ctrl+滚轮是浏览器缩放，横滑不算切周。"""
        s = read(SCENE)
        self.assertIn('function wheelInsideScrollable(target)', s)
        self.assertIn('wheelInsideScrollable(ev.target)', s)
        self.assertNotIn("closest('.tbody, .twrap')", s,
                          '硬编码隐藏容器名会造成永不命中的死代码')
        self.assertIn('Math.abs(ev.deltaX) > Math.abs(ev.deltaY) * 1.2', s)
        self.assertIn('ev.deltaMode === 2 ? innerHeight : 1', s,
                      '页模式要按视口高折算，不是写死 400')

    def test_scene_exposes_readiness_for_e2e(self):
        self.assertIn('window.__sceneReady = true;', read(SCENE))

    def test_artifact_has_the_bundled_handler_and_hint(self):
        a = read(ARTIFACT)
        self.assertIn('addEventListener("wheel"', a, '产物里必须有打包后的 wheel 监听')
        self.assertIn('滚轮', a, '右下键位提示要告诉用户能滚轮切周')
        self.assertIn('__sceneReady', a)

    def test_artifact_matches_fresh_build(self):
        """改了 scene.js / shell.html / config 却忘了重建，这里必须挡下。"""
        if not shutil.which('node') or not os.path.isdir(os.path.join(ROOT, 'web3d', 'node_modules')):
            self.skipTest('没有 node 或 web3d 依赖，跳过构建幂等检查')
        r = subprocess.run(['node', 'build.mjs', '--check'],
                           cwd=os.path.join(ROOT, 'web3d'),
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_hint_present_in_shell(self):
        self.assertIn('<kbd>滚轮</kbd>', read(SHELL))


if __name__ == '__main__':
    unittest.main()
