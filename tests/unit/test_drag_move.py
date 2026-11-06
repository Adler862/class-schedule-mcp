# -*- coding: utf-8 -*-
"""拖拽调课的静态护栏。

单文件页是 tools/single_template.html 生成的。最容易退化的一件事是：
有人只改了 docs/index.html（线上演示页），看起来功能有了，下次一构建就没了。
这里锁住「模板与产物同源」，以及几个不该被悄悄改动的手势参数。
"""
import os
import re
import json
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TPL = os.path.join(ROOT, 'tools', 'single_template.html')
DOCS = os.path.join(ROOT, 'docs', 'index.html')

LINK_3D = ('<a class="to3d" href="3d.html"><b>3D</b>'
           '<span>档案架<br>视图</span><i>→</i></a>')


def read(path):
    with open(path, 'r', encoding='utf-8', newline='') as f:
        return f.read().replace('\r\n', '\n')


def data_blob(html):
    m = re.search(r'^var DATA = (.*);$', html, re.M)
    assert m, '找不到 var DATA 行'
    return m.group(1)


class DragTemplateTest(unittest.TestCase):

    def test_both_files_carry_the_drag_marker(self):
        """模板和生成页都必须含拖拽实现，少一份就说明产物没跟着重建。"""
        for path in (TPL, DOCS):
            with self.subTest(path=os.path.relpath(path, ROOT)):
                self.assertIn('__DRAG_MOVE__', read(path))

    def test_docs_is_template_with_data_filled_in(self):
        """docs/index.html 必须正好等于「模板 + 内联数据 + 3D 入口」。"""
        tpl, docs = read(TPL), read(DOCS)
        blob = data_blob(docs)
        expected = tpl.replace('/*__DATA__*/null', blob).replace('<!--LINK3D-->', LINK_3D)
        self.assertEqual(expected.replace('\r\n', '\n'), docs)

    def test_no_build_placeholder_left_in_docs(self):
        docs = read(DOCS)
        self.assertNotIn('/*__DATA__*/', docs)
        self.assertNotIn('<!--LINK3D-->', docs)
        self.assertIsInstance(json.loads(data_blob(docs)), dict)

    def test_gesture_and_edge_parameters(self):
        """这些数字是 grill 时定下来的交互契约，改了要同步改 E2E。"""
        tpl = read(TPL)
        for snippet in (
            'holdMs:220', 'mouseDist:8', 'touchSlop:10',
            'edgeIn:8', 'edgeOut:48', 'edgeMin:24',
            'dwellMs:500', 'repeatMs:800',
            'function flipWeek', 'function commitDragMove',
            'window.__dragProbe',
        ):
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, tpl)

    def test_text_selection_is_disabled_while_dragging(self):
        """鼠标拖过课程卡不能顺手选中里面的文字（整片蓝）。"""
        tpl = read(TPL)
        self.assertIn('user-select:none', tpl)
        self.assertIn('body.dragging{user-select:none', tpl)
        self.assertIn("document.addEventListener('selectstart'", tpl)
        self.assertIn("document.addEventListener('dragstart'", tpl)
        self.assertIn('sel.removeAllRanges()', tpl)

    def test_touch_action_and_readonly_probe(self):
        """手机上必须在按下前声明手势归属；探针只读，不提供改写数据的入口。"""
        tpl = read(TPL)
        self.assertIn('touch-action:none', tpl)
        self.assertIn("toastEl.querySelector('.tx').textContent = msg", tpl)
        self.assertNotIn('window.__dragProbe.commit', tpl)


if __name__ == '__main__':
    unittest.main()
