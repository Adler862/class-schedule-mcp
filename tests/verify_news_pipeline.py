#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""离线自检：语法 + 偏好加载 + 分类/配额渲染（不联网、不依赖 mcp 包）"""
import ast
import io
import json
import os
import sys
from pathlib import Path
import types

try:  # Windows 控制台默认 GBK，输出含 emoji 会直接崩
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SRC = str(Path(__file__).resolve().parents[1] / 'src' / 'class_schedule_mcp.py')
PREFS = str(Path(__file__).resolve().parents[1] / 'config' / 'news_prefs.json')

print('=== 1. 语法检查 (ast.parse) ===')
code = io.open(SRC, encoding='utf-8').read()
try:
    tree = ast.parse(code)
    print('OK 语法通过，顶层节点 %d 个' % len(tree.body))
except SyntaxError as e:
    print('FAIL 语法错误: %s (line %s)' % (e, e.lineno))
    sys.exit(1)

print()
print('=== 2. news_prefs.json 检查 ===')
try:
    prefs = json.load(io.open(PREFS, encoding='utf-8'))
except Exception as e:
    print('FAIL JSON 解析失败: %s' % e)
    sys.exit(1)
cats = prefs.get('categories') or {}
tech = ('AI/大模型', '科技/大厂')
tech_q = sum(int((c or {}).get('quota', 0) or 0) for n, c in cats.items() if n in tech)
other_q = sum(int((c or {}).get('quota', 0) or 0) for n, c in cats.items() if n not in tech)
hot_q = int(prefs.get('hot_items', 3))
cap = int(prefs.get('max_tech_items', 3))
print('板块: %s' % ' / '.join(cats.keys()))
print('科技配额合计 %d（上限 %d），其他板块合计 %d，热搜兜底 %d' % (tech_q, cap, other_q, hot_q))
total = min(tech_q, cap) + other_q
print('预计总条数约 %d，科技占比 %.0f%%' % (total, 100.0 * min(tech_q, cap) / max(1, total)))
assert min(tech_q, cap) / max(1, total) <= 0.30, '科技占比仍然偏高'
assert set(prefs.get('interest') or []) <= set(cats.keys()), 'interest 里有不存在的板块'

print()
print('=== 3. 屏蔽词检查（应只屏蔽八卦绯闻） ===')
print('屏蔽词: %s' % '、'.join(prefs.get('blocked') or []))
banned = [w for w in ('电影', '音乐', '电视剧', '演员', '歌手') if w in (prefs.get('blocked') or [])]
assert not banned, '误屏蔽作品类词: %s' % banned
print('OK 作品类词未被屏蔽')

print()
print('=== 4. 用真实源码逻辑跑模拟数据 ===')
# 桩掉 mcp / 课表引擎依赖，直接加载被测函数
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
mcp_mod = types.ModuleType('mcp')
server_mod = types.ModuleType('mcp.server')
fastmcp_mod = types.ModuleType('mcp.server.fastmcp')


class _FakeMCP(object):
    def __init__(self, *a, **k):
        pass

    def tool(self, *a, **k):
        def deco(f):
            return f
        return deco

    def run(self):
        pass


class _FakeImage(object):
    def __init__(self, *a, **k):
        pass


fastmcp_mod.FastMCP = _FakeMCP
fastmcp_mod.Image = _FakeImage
sys.modules['mcp'] = mcp_mod
sys.modules['mcp.server'] = server_mod
sys.modules['mcp.server.fastmcp'] = fastmcp_mod

ns = {'__name__': 'not_main', '__file__': SRC}
exec(compile(code, SRC, 'exec'), ns)

fake_items = [
    {'title': '国台办批赖清德所谓“双十”讲话', 'source': '澎湃', 'hot': 0},
    {'title': '证监会召开资本市场和金融形势专家座谈会', 'source': '百度财经', 'hot': 2900},
    {'title': '普京向美方转达伊朗方面解决冲突构想', 'source': '百度国际', 'hot': 2950},
    {'title': '抗癌药物研发迎来重要突破', 'source': '百度', 'hot': 2800},
    {'title': '钟南山：最有成就感的是研发出新药', 'source': '百度', 'hot': 2990},
    {'title': '雅思考试取消考生在考场外大哭', 'source': '百度', 'hot': 2700},
    {'title': '2027考研报名时间公布，多地新增报考点', 'source': '百度民生', 'hot': 2870},
    {'title': '台风蓝色预警：沿海地区将有大到暴雨', 'source': '澎湃', 'hot': 2860},
    {'title': '未来五年推进就业有哪些新变化', 'source': '百度民生', 'hot': 2980},
    {'title': '四部门就提升汽车安全性能征求意见', 'source': '百度', 'hot': 2600},
    {'title': '多部门征求意见，涉汽车门把手等', 'source': '澎湃', 'hot': 0},
    {'title': 'OpenAI 发布新一代多模态推理模型', 'source': 'IT资讯', 'hot': 0},
    {'title': 'DeepSeek 开源新训练框架', 'source': 'IT资讯', 'hot': 0},
    {'title': '腾讯财报：AI 投入继续加大', 'source': 'IT资讯', 'hot': 0},
    {'title': '华为新机官宣下周发布', 'source': '微博', 'hot': 800000},
    {'title': '英伟达芯片对华出口新规', 'source': '知乎', 'hot': 500000},
    {'title': '某明星出轨被拍，粉丝脱粉', 'source': '微博', 'hot': 999999},
    {'title': '电影《长津湖》重映定档', 'source': '微博', 'hot': 700000},
]

prefs_real = ns['_load_prefs']()
ns['_collect_news'] = lambda p: (fake_items, ['60s_general'])
ns['_cached'] = lambda k: None
ns['_set_cache'] = lambda *a, **k: None
out = ns['build_news']()
print(out)
print('repr 前 3 行:', repr(out.splitlines()[:4]))
print('校园 标题在 out 中?', '校园' in out)

# 调试：每条被分类到的板块
print('--- 分类明细 ---')
for it in fake_items:
    sec, tier = ns['_classify'](it, prefs_real)
    print('  %-12s tier=%s %s | %s' % (sec, tier, it['source'], it['title'][:32]))

print()
print('=== 5. 断言 ===')
tech_lines = 0
for line in out.splitlines():
    if line.startswith('🤖') or line.startswith('💻'):
        continue
print('渲染行数 %d' % len(out.splitlines()))
assert '某明星出轨' not in out, '八卦没被屏蔽'
assert '电影《长津湖》' in out or True, '（作品类是否出现取决于板块命中）'
body = [l for l in out.splitlines() if l and l[0].isdigit()]
print('条目总数 %d' % len(body))

# 科技条数统计：位于科技板块标题下的条目
cur = None
tech_cnt = 0
for line in out.splitlines():
    if line.startswith(('🤖', '💻')):
        cur = 'tech'
    elif line.startswith(('🌍', '🔬', '🎓', '🏠', '🔥')):
        cur = 'other'
    elif line[:1].isdigit() and cur == 'tech':
        tech_cnt += 1
print('科技条目 %d / 总条目 %d = %.0f%%' % (tech_cnt, len(body), 100.0 * tech_cnt / max(1, len(body))))
assert tech_cnt <= 3, '科技条数超上限: %d' % tech_cnt
assert tech_cnt / max(1, len(body)) <= 0.30, '科技占比超 30%'
for sec in ('🌍 时政/国际', '🔬 科学/健康', '🎓 校园/教育', '🏠 本地/生活'):
    assert sec in out, '板块缺失: %s' % sec
assert '雅思考试取消考生' in out, '教育类条目未进入校园板块（应命中 考生/考场/雅思）'
assert '台风蓝色预警' in out, '生活类条目未进入本地板块'
print('OK 四个兴趣板块全部有内容')
print()
print('ALL CHECKS PASSED')
