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
import hmac
import socket
import secrets
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
    # 由 main() 注入；None 表示不校验（只监听回环时）
    token = None

    def _dispatch(self, method):
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        length = int(self.headers.get('Content-Length') or 0)
        body = self.rfile.read(length) if length else None
        try:
            # respond 而不是 handle：多出来的是 ETag / Cache-Control / gzip 这些协议细节，
            # 内容逻辑仍然全在 webapp.handle 里（它的单测不受影响）
            status, headers, payload = webapp.respond(
                method, parsed.path, query, body,
                headers=self.headers, root=webapp.REPO_ROOT, token=self.token)
        except Exception as exc:  # 兜底：不让一个异常打挂整个进程
            status = 500
            headers = {'Content-Type': 'application/json; charset=utf-8'}
            payload = json.dumps(
                {'error': f'{type(exc).__name__}: {exc}'}, ensure_ascii=False).encode('utf-8')

        self.send_response(status)
        for name, value in headers.items():
            self.send_header(name, value)
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        if method != 'HEAD' and payload:
            self.wfile.write(payload)

    def do_GET(self):
        self._dispatch('GET')

    def do_POST(self):
        self._dispatch('POST')

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
    ap.add_argument('--token', help='写接口口令；只监听回环时不需要，'
                                    '监听到局域网时不填则自动生成并打印')
    args = ap.parse_args()

    # 只监听回环 = 本机自己用，不设口令；一旦暴露到局域网，写接口就必须凭证。
    lan = args.host not in ('127.0.0.1', 'localhost', '::1')
    token = args.token or (secrets.token_urlsafe(12) if lan else None)
    Handler.token = token

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f'课表助手已启动')
    print(f'  本机   http://127.0.0.1:{args.port}')
    if args.host in ('0.0.0.0', '::'):
        ip = lan_ip()
        if ip:
            # 带 ?t= 的链接：手机打开一次就把口令记在本地，之后不用再输
            print(f'  手机   http://{ip}:{args.port}/?t={token}')
            print(f'         （读接口不限；改调课需要上面这个链接里的口令）')
    print('  Ctrl+C 停止')
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('\n已停止')
    finally:
        httpd.server_close()


if __name__ == '__main__':
    main()
