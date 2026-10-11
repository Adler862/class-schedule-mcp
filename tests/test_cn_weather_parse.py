#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""实测中国天气网 7 天页解析（兜底源）"""
import os
import re
import urllib.request

UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
URL = 'https://www.weather.com.cn/weather/%s.shtml' % os.environ.get('SCHEDULE_CITY_CODE', '101010100')

req = urllib.request.Request(URL, headers=UA)
with urllib.request.urlopen(req, timeout=15) as r:
    html = r.read().decode('utf-8', 'ignore')

print('页面长度', len(html))
blk = re.search(r'<ul class="t clearfix">(.*?)</ul>', html, re.S)
print('找到 7 日区块:', bool(blk))
if blk:
    body = blk.group(1)
    items = re.findall(r'<li.*?</li>', body, re.S)
    print('天数:', len(items))
    print('--- 第 2 天原始 HTML ---')
    print(items[1])
    print('--- 温度标记每种写法 ---')
    for pat in [r'<span>\s*(\d+)\s*</span>', r'<i>\s*(\d+)\s*</i>', r'>(\d+)℃<', r'(\d+)℃']:
        print('  %-28s %s' % (pat, re.findall(pat, items[1])))
    for li in items:
        h1 = re.search(r'<h1>(.*?)</h1>', li, re.S)
        p = re.search(r'<p[^>]*title="([^"]*)"[^>]*>(.*?)</p>', li, re.S)
        hi = re.search(r'<span>\s*(\d+)\s*</span>', li)
        lo = re.search(r'<i>\s*(\d+)\s*</i>', li)
        date = re.sub(r'<[^>]+>', '', h1.group(1)).strip() if h1 else '?'
        desc = (p.group(1) if p else '') or (re.sub(r'<[^>]+>', '', p.group(2)).strip() if p else '')
        print('  %-8s %-10s 高%s 低%s' % (date, desc, hi.group(1) if hi else '-', lo.group(1) if lo else '-'))
