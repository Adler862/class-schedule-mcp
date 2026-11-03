"""通过 stdio 直接跟 MCP 服务对话，拿到真实的 tools/list 与 tools/call 输出。

用来替代附件里那几张"网页问答"截图——那些是 HTTP 接口，不是 MCP 协议。
"""
import json
import subprocess
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE) if os.path.basename(HERE) == 'tools' else HERE
PY = sys.executable


def send(p, obj):
    p.stdin.write((json.dumps(obj, ensure_ascii=False) + '\n').encode('utf-8'))
    p.stdin.flush()


def recv(p, want_id, timeout_lines=80):
    """读到指定 id 的响应为止（跳过通知类消息）。"""
    for _ in range(timeout_lines):
        line = p.stdout.readline()
        if not line:
            return None
        try:
            msg = json.loads(line.decode('utf-8'))
        except Exception:
            continue
        if msg.get('id') == want_id:
            return msg
    return None


def main():
    env = dict(os.environ)
    env['PYTHONIOENCODING'] = 'utf-8'
    p = subprocess.Popen(
        [PY, os.path.join(ROOT, 'src', 'class_schedule_mcp.py')],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        cwd=ROOT, env=env,
    )

    send(p, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                        "clientInfo": {"name": "probe", "version": "1.0"}}})
    init = recv(p, 1)
    if not init:
        print('初始化失败，stderr:', p.stderr.read().decode('utf-8', 'ignore')[:600])
        p.kill()
        return
    info = init.get('result', {}).get('serverInfo', {})
    print(f"[initialize] {info.get('name')} v{info.get('version')} · 协议 {init['result'].get('protocolVersion')}")

    send(p, {"jsonrpc": "2.0", "method": "notifications/initialized"})
    send(p, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    tl = recv(p, 2)
    tools = tl.get('result', {}).get('tools', []) if tl else []
    print(f"\n[tools/list] 共 {len(tools)} 个工具")
    for i, t in enumerate(tools, 1):
        desc = (t.get('description') or '').replace('\n', ' ')[:52]
        print(f"  {i:2d}. {t['name']:<32} {desc}")

    for name, args in [('get_today_schedule', {}), ('get_next_course', {})]:
        send(p, {"jsonrpc": "2.0", "id": 10, "method": "tools/call",
                 "params": {"name": name, "arguments": args}})
        r = recv(p, 10)
        print(f"\n[tools/call] {name}")
        if r and 'result' in r:
            for c in r['result'].get('content', []):
                if c.get('type') == 'text':
                    print('  ' + c['text'].replace('\n', '\n  ')[:700])
        else:
            print('  ', json.dumps(r, ensure_ascii=False)[:300])

    p.terminate()
    try:
        p.wait(timeout=5)
    except Exception:
        p.kill()


if __name__ == '__main__':
    main()
