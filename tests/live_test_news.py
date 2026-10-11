#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""真实联网测试：只启用澎湃 + 百度热搜（避开被限流的 60s），验证真实数据分布"""
import io
import json
import sys
from pathlib import Path
import types

try:  # Windows 控制台默认 GBK，输出含 emoji 会直接崩
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = str(Path(__file__).resolve().parents[1] / 'src')
SRC = BASE + r'\class_schedule_mcp.py'
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


fastmcp_mod.FastMCP = _FakeMCP
fastmcp_mod.Image = object
sys.modules['mcp'] = mcp_mod
sys.modules['mcp.server'] = server_mod
sys.modules['mcp.server.fastmcp'] = fastmcp_mod

code = io.open(SRC, encoding='utf-8').read()
ns = {'__name__': 'not_main', '__file__': SRC}
exec(compile(code, SRC, 'exec'), ns)

# 只留独立源，避免 60s 限流干扰
prefs = ns['_load_prefs']()
for k in list(prefs['sources'].keys()):
    prefs['sources'][k] = k in ('thepaper', 'baidu_hot')
ns['_load_prefs'] = lambda: prefs

print('=== 抓取真实数据（澎湃 + 百度四榜）===')
items, failed = ns['_collect_news'](prefs)
from collections import Counter
print('总条目 %d，失败源 %s' % (len(items), failed))
print('来源分布:', dict(Counter(x['source'] for x in items)))
print()

print('=== 分类分布 ===')
p2 = ns['_load_prefs']()
prefs['sources'] = p2['sources'] or prefs['sources']
cnt = Counter()
blocked = 0
for it in items:
    sec, tier = ns['_classify'](it, prefs)
    if tier < 0:
        blocked += 1
        continue
    cnt[sec or '(无板块→热搜兜底)'] += 1
for k, v in cnt.most_common():
    print('  %-18s %d' % (k, v))
print('  被屏蔽词过滤: %d' % blocked)
print()

print('=== 实际推送效果 ===')
ns['_cached'] = lambda k: None
ns['_set_cache'] = lambda *a, **k: None
out = ns['build_news']()
print(out)
