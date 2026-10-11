#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""端到端握手测试：按 MCP stdio 协议启动服务并列出工具，抓出真实启动/运行错误"""
import json
import subprocess
import sys
from pathlib import Path
import threading
import time

try:  # Windows 控制台默认 GBK，输出含 emoji 会直接崩
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

PY = sys.executable
ALT_PY = sys.executable
SRV = str(Path(__file__).resolve().parents[1] / 'src' / 'class_schedule_mcp.py')


def run(interpreter, label):
    print('=' * 70)
    print('%s: %s' % (label, interpreter))
    print('=' * 70)
    try:
        p = subprocess.Popen([interpreter, SRV], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, encoding='utf-8', errors='replace', bufsize=1)
    except Exception as e:
        print('启动失败: %r' % (e,))
        return

    lines = []

    def reader(stream, tag):
        for line in stream:
            lines.append((tag, line.rstrip()))
            print('[%s] %s' % (tag, line.rstrip()[:400]))

    threading.Thread(target=reader, args=(p.stdout, 'OUT'), daemon=True).start()
    threading.Thread(target=reader, args=(p.stderr, 'ERR'), daemon=True).start()

    def send(obj):
        try:
            p.stdin.write(json.dumps(obj) + '\n')
            p.stdin.flush()
        except Exception as e:
            print('写入失败: %r' % (e,))

    send({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
          'params': {'protocolVersion': '2024-11-05',
                     'capabilities': {},
                     'clientInfo': {'name': 'probe', 'version': '1.0'}}})
    time.sleep(3)
    send({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
    time.sleep(1)
    send({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list', 'params': {}})
    time.sleep(3)
    send({'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call',
          'params': {'name': 'get_weather_climate', 'arguments': {}}})
    time.sleep(12)

    if p.poll() is None:
        p.terminate()
        time.sleep(1)
    print('进程退出码:', p.poll())
    tools = [l for tag, l in lines if tag == 'OUT' and '"tools"' in l]
    if tools:
        try:
            data = json.loads(tools[-1])
            print('工具数量: %d' % len(data.get('result', {}).get('tools', [])))
            print('工具名: %s' % ', '.join(t['name'] for t in data['result']['tools']))
        except Exception as e:
            print('解析 tools/list 失败: %r' % (e,))
    else:
        print('!! 没有收到 tools/list 响应')
    print()


run(PY, 'Cherry Studio 实际使用的解释器')
run(ALT_PY, '当前系统 python')
