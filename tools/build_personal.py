#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一条命令产出个人课表的两页（2D 单文件 + 3D 档案架），并保证互相指得对。

为什么要有这个脚本
------------------
手工出个人页要跑两步，而且两个命令之间存在一个**隐式耦合**：

    python tools/build_single.py --courses mine.json --out dist/我的课表.html --link-3d
    cd web3d && node build.mjs --courses ../mine.json --out ../dist/3d.html --index 我的课表.html

第二行的 `--index` 必须等于第一行输出的文件名。忘了改就是 404——这个坑真踩过：
3D 详情态的「完整学期表格」原来硬编码 index.html，而个人页根本叫别的名字。
把它俩绑在一个脚本里，这类错误就没有发生的机会。

用法
----
    # 从教务系统导出的 xls 一路做完（教师默认脱敏）
    python tools/build_personal.py 学生个人课表.xls --start 2026-08-31

    # 已经有 courses.json，只出页面
    python tools/build_personal.py --courses output/mine.json

    # 指定输出目录和文件名
    python tools/build_personal.py --courses output/mine.json --out-dir dist --name 我的课表

    # 机器上没有 node / 没装 web3d 依赖时，只出 2D
    python tools/build_personal.py --courses output/mine.json --no-3d
"""
import os
import sys
import json
import shutil
import argparse
import subprocess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(BASE_DIR)
sys.path.insert(0, BASE_DIR)


def plan(courses, out_dir='dist', name='我的课表'):
    """算出三个产物路径。抽成纯函数是为了能测——`--index` 和 2D 文件名必须一致。"""
    if name.endswith('.html'):
        name = name[:-5]
    out_dir = out_dir or 'dist'
    if not os.path.isabs(out_dir):
        out_dir = os.path.join(REPO_ROOT, out_dir)
    return {
        'courses': courses,
        'outDir': out_dir,
        'html': os.path.join(out_dir, name + '.html'),
        'href': name + '.html',                 # 3D 页里那个链接的 href
        'three': os.path.join(out_dir, '3d.html'),
    }


def convert_xls(xls, start=None, out=None, mask_teachers=True, school=None,
                class_name=None, diags=None):
    """教务导出 → courses.json。返回 (结果, 输出路径)。"""
    import convert_xls as cv
    result = cv.convert(xls, start=start, mask_teachers=mask_teachers,
                        school=school, class_name=class_name, diagnostics=diags)
    if 'error' in result:
        raise SystemExit(f'解析失败: {result["error"]}')
    out = out or os.path.join(REPO_ROOT, 'output', 'mine.json')
    os.makedirs(os.path.dirname(out) or '.', exist_ok=True)
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return result, out


def check_link(three_path, href):
    """3D 产物里有没有指向 href 的链接。

    这是本脚本存在的理由：两条构建命令之间靠「文件名一致」耦合，
    抽出来才能单独测，而不是等用户在浏览器里点到 404 才发现。
    """
    try:
        with open(three_path, 'r', encoding='utf-8') as f:
            return href in f.read()
    except OSError:
        return False


def run(cmd, cwd=None, quiet=False):
    """跑子进程；失败时把 stderr 一起抛出来，别只留一个返回码。"""
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError('%s\n%s' % (' '.join(cmd), (proc.stderr or proc.stdout).strip()))
    if not quiet:
        for line in (proc.stdout or '').splitlines():
            print('  ' + line)
    return proc.stdout


def main(argv=None):
    ap = argparse.ArgumentParser(description='一条命令产出个人课表 2D + 3D 页')
    ap.add_argument('xls', nargs='?', help='教务系统导出的 .xls / .xlsx')
    ap.add_argument('--courses', help='已有 courses.json（与 xls 二选一）')
    ap.add_argument('--start', help='学期首周周一 YYYY-MM-DD（从 xls 转换时强烈建议给）')
    ap.add_argument('--out-dir', default='dist', help='输出目录，默认 dist/')
    ap.add_argument('--name', default='我的课表', help='2D 页文件名（不含扩展名）')
    ap.add_argument('--keep-teacher', action='store_true',
                    help='保留教师全名（默认脱敏成「姓+老师」）')
    ap.add_argument('--no-3d', action='store_true', help='只出 2D 页')
    args = ap.parse_args(argv)

    # 1) 数据
    if args.xls:
        diags = []
        result, courses = convert_xls(
            args.xls, start=args.start, mask_teachers=not args.keep_teacher,
            diags=diags)
        print(f'解析 {args.xls}')
        print(f'  {result["meta"]["totalSlots"]} 个时段 · {result["meta"]["totalCourses"]} 门课'
              f' · 学期起点 {result["meta"]["semesterStart"] or "(未设置)"}')
        for d in diags[:5]:
            print(f'  {d}')
    elif args.courses:
        courses = os.path.abspath(args.courses)
        if not os.path.exists(courses):
            raise SystemExit(f'找不到 {courses}')
    else:
        ap.error('要么给一个 .xls，要么用 --courses 指定已有的 json')

    p = plan(courses, args.out_dir, args.name)

    # 2) 2D 单文件页
    print(f'\n生成 2D 页')
    run([sys.executable, os.path.join(BASE_DIR, 'build_single.py'),
         '--courses', p['courses'], '--out', p['html'], '--link-3d'])

    # 3) 3D 档案架
    if args.no_3d:
        print('\n按 --no-3d 跳过 3D 页')
        return 0

    node = shutil.which('node')
    if not node:
        print('\n跳过 3D：机器上没有 node（装上 node 后重跑即可）')
        return 0
    web3d = os.path.join(REPO_ROOT, 'web3d')
    if not os.path.isdir(os.path.join(web3d, 'node_modules')):
        print('\n跳过 3D：web3d 依赖没装（先 cd web3d && npm install）')
        return 0

    print(f'\n生成 3D 页')
    run([node, 'build.mjs', '--courses', p['courses'], '--out', p['three'],
         '--index', p['href']], cwd=web3d)

    # 4) 自检：3D 产物里那个链接必须指向刚生成的 2D 文件
    if not check_link(p['three'], p['href']):
        raise SystemExit(f'3D 页里没找到指向 {p["href"]} 的链接，产物不对')

    print(f'\n完成：')
    print(f'  2D  {p["html"]}')
    print(f'  3D  {p["three"]}')
    print(f'  两者同目录，3D 详情态的「完整学期表格」指向 {p["href"]}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
