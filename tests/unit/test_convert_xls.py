# -*- coding: utf-8 -*-
"""课表 .xls 解析器的脱敏逻辑测试。

只测纯函数：真实的教务导出文件含个人信息，不进仓库。
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

import convert_xls  # noqa: E402


class MaskTeacherTest(unittest.TestCase):
    def test_single_char_surname(self):
        self.assertEqual(convert_xls.mask_teacher('刘波涛'), '刘老师')

    def test_two_char_name(self):
        self.assertEqual(convert_xls.mask_teacher('赵磊'), '赵老师')

    def test_compound_surname_kept_whole(self):
        self.assertEqual(convert_xls.mask_teacher('欧阳修'), '欧阳老师')
        self.assertEqual(convert_xls.mask_teacher('司马光'), '司马老师')

    def test_compound_surname_alone_is_not_split(self):
        # 「欧阳」两个字就是全名时不能取首字，否则变成「欧老师」
        self.assertEqual(convert_xls.mask_teacher('欧阳'), '欧老师')

    def test_multiple_teachers(self):
        self.assertEqual(convert_xls.mask_teacher('刘波涛、唐良文'), '刘老师、唐老师')
        self.assertEqual(convert_xls.mask_teacher('刘波涛,唐良文'), '刘老师、唐老师')

    def test_empty_and_none(self):
        self.assertEqual(convert_xls.mask_teacher(''), '')
        self.assertEqual(convert_xls.mask_teacher(None), '')

    def test_no_full_name_survives(self):
        for full in ('刘波涛', '姚丽君', '徐成林'):
            self.assertNotIn(full, convert_xls.mask_teacher(full))


if __name__ == '__main__':
    unittest.main()
