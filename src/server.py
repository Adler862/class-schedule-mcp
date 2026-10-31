#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HTTP 适配器：把 webapp.handle 挂到标准库 http.server 上。

刻意不用 Flask/FastAPI——这个项目要能在一个没装任何第三方包的环境里直接跑起来，
评委拿到压缩包、双击、打开浏览器就能看。全部逻辑在 webapp.py 里，这里是薄壳。

用法：
  python src/server.py                # http://127.0.0.1:8765
  python src/server.py --port 9000 --host 0.0.0.0   # 手机同局域网可访问
"""
import os
import sys
import json
import socket
import argparse
import datetime
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import webapp  # noqa: E402


class Handler(BaseHTTPRequestHandler):
    server_version = 'ClassScheduleWeb/1.0'

    def _dispatch(self, method):
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        length = int(self.headers.get('Content-Length') or 0)
        body = self.rfile.read(length) if length else None
        try:
            status, ctype, payload = webapp.handle(
                method, parsed.path, query, body, root=webapp.REPO_ROOT)
        except Exception as exc:  # 兜底：不让一个异常打挂整个进程
            status, ctype, payload = 500, 'application/json; charset=utf-8', json.dumps(
                {'error': f'{type(exc).__name__}: {exc}'}, ensure_ascii=False).encode('utf-8')

        self.send_response(status)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        if method != 'HEAD':
            self.wfile.write(payload)

    def do_GET(self):
        self._dispatch('GET')

    def do_HEAD(self):
        self._dispatch('HEAD')

    def log_message(self, fmt, *args):
        sys.stderr.write(f'[{datetime.datetime.now():%H:%M:%S}] {fmt % args}\n')


def lan_ip():
    """拿到本机在局域网里的地址，方便手机扫同一个网访问。"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return None


def main():
    ap = argparse.ArgumentParser(description='课表助手 Web 服务')
    ap.add_argument('--host', default='127.0.0.1')
    ap.add_argument('--port', type=int, default=8765)
    args = ap.parse_args()

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f'课表助手已启动')
    print(f'  本机   http://127.0.0.1:{args.port}')
    if args.host in ('0.0.0.0', '::'):
        ip = lan_ip()
        if ip:
            print(f'  手机   http://{ip}:{args.port}')
    print('  Ctrl+C 停止')
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('\n已停止')
    finally:
        httpd.server_close()


if __name__ == '__main__':
    main()
