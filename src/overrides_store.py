#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""调课例外的持久化：SQLite（标准库自带）+ WAL + 显式事务。

为什么不再用 JSON 文件
----------------------
原来的写法是「读出整个列表 → 在内存里改 → 整份写回」。单用户、单标签页时没问题，
但 `ThreadingHTTPServer` 是真并发：两个请求同时进来（两个标签页各拖一次课、
或者脚本和页面同时写），后写的会把先写的整份覆盖掉，而且没有任何报错。
`save_overrides` 里的 tmp+replace 只保证「不会写出半个坏文件」，不保证「不丢更新」。

换成 SQLite 之后：
  - 读改写放进一个 `BEGIN IMMEDIATE` 事务，写与写天然串行，不丢更新
  - 每次写入 revision +1，客户端可以拿它做乐观并发（对不上就 409）
  - 顺便有了 `id` 顺序、按字段查询的能力，不用每次全量反序列化

都没有的部分：不引入任何第三方依赖，sqlite3 是标准库。

文件布局
--------
`config/overrides.db`（WAL 模式，会多出 -wal / -shm 两个伴生文件）。
旧的 `config/overrides.json` 在第一次打开 db 时被**一次性导入**，然后改名成
`overrides.json.migrated` 留在原地当备份——不删，因为那是用户数据。
"""
import os
import json
import time
import sqlite3
import datetime
import threading

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(BASE_DIR)

DEFAULT_DB = os.environ.get('SCHEDULE_OVERRIDES_DB') or os.path.join(
    REPO_ROOT, 'config', 'overrides.db')

# 读取时丢弃没有这三项的记录（历史数据里出现过残缺条目）
REQUIRED = ('name', 'fromDate')

SCHEMA = """
CREATE TABLE IF NOT EXISTS override (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    from_date   TEXT NOT NULL,
    from_period INTEGER NOT NULL DEFAULT 0,
    type        TEXT NOT NULL DEFAULT 'cancel',
    to_date     TEXT,
    to_period   INTEGER,
    span        INTEGER,
    teacher     TEXT,
    location    TEXT,
    room        TEXT,
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT NOT NULL);
"""

# 列 → 字段名。顺序决定 load 出来的字段顺序，方便肉眼比对。
COLUMNS = (('name', 'name'), ('from_date', 'fromDate'),
           ('from_period', 'fromPeriod'), ('type', 'type'),
           ('to_date', 'toDate'), ('to_period', 'toPeriod'),
           ('span', 'span'), ('teacher', 'teacher'),
           ('location', 'location'), ('room', 'room'))


# ---------------------------------------------------------------------------
# 连接与迁移
# ---------------------------------------------------------------------------

def legacy_path_for(db_path):
    """与 db 同名的旧 JSON：config/overrides.db → config/overrides.json"""
    return os.path.splitext(db_path)[0] + '.json'


def _migrate_legacy(con, db_path):
    """把旧 JSON 一次性导入。坏文件、空文件都只当作「没有调课」。"""
    legacy = legacy_path_for(db_path)
    if not os.path.exists(legacy):
        return 0
    imported = 0
    try:
        with open(legacy, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = None
    items = []
    if isinstance(data, dict):
        items = data.get('overrides') or []
    elif isinstance(data, list):
        items = data
    if isinstance(items, list):
        for raw in items:
            clean = _clean(raw)
            if clean:
                _insert(con, clean)
                imported += 1
    try:
        os.replace(legacy, legacy + '.migrated')
    except OSError:
        pass
    return imported


_INIT_LOCK = threading.Lock()
_READY = set()          # 本进程里已经建过表的库，避免每次连接都跑一遍 DDL


def _open(db_path=None):
    """打开（必要时初始化）数据库。每次调用一个连接——sqlite 连接不能跨线程共用，
    而这个服务是多线程的；短连接的开销对「一天几十次请求」完全无感。

    初始化（建表 / WAL / 迁移）只在每个库第一次打开时做，并且进进程内锁：
    `PRAGMA journal_mode=WAL` 遇到别的连接持锁会直接报错，不会等 busy_timeout，
    24 个线程同时冷启动就会有一个失败。DDL 也没必要每次都跑。
    """
    path = db_path or DEFAULT_DB
    fresh = not os.path.exists(path)
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    con = sqlite3.connect(path, timeout=5.0, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA busy_timeout=5000')
    if path in _READY:
        return con
    try:
        with _INIT_LOCK:
            if path in _READY:
                return con
            con.execute('PRAGMA journal_mode=WAL')
            con.execute('PRAGMA synchronous=NORMAL')
            con.executescript(SCHEMA)
            con.execute("INSERT OR IGNORE INTO kv (k, v) VALUES ('revision', '0')")
            _READY.add(path)
            if fresh:
                _migrate_legacy(con, path)
    except Exception:
        con.close()
        raise
    return con


class _Tx:
    """显式事务。BEGIN IMMEDIATE 立刻拿写锁，避免「先读后写」中间被插队。"""

    def __init__(self, con):
        self.con = con

    def __enter__(self):
        """抢写锁。busy_timeout 挡不住 BEGIN IMMEDIATE 的立刻失败，
        多线程/多进程同时写同一份库时，退让重试比调大超时更可靠。"""
        for attempt in range(6):
            try:
                self.con.execute('BEGIN IMMEDIATE')
                return self.con
            except sqlite3.OperationalError as exc:
                text = str(exc).lower()
                if ('locked' not in text and 'busy' not in text) or attempt == 5:
                    raise
                time.sleep(0.02 * (attempt + 1))

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.con.execute('COMMIT')
        else:
            self.con.execute('ROLLBACK')
        return False


# ---------------------------------------------------------------------------
# 行 ↔ 字典
# ---------------------------------------------------------------------------

def _clean(raw):
    """外部输入 → 一行合法记录。缺必需字段就返回 None（丢弃，不抛异常）。"""
    if not isinstance(raw, dict):
        return None
    if any(not raw.get(k) for k in REQUIRED):
        return None
    out = {}
    for col, key in COLUMNS:
        value = raw.get(key)
        if col in ('from_period', 'to_period', 'span'):
            try:
                value = int(value) if value is not None else None
            except (TypeError, ValueError):
                value = None
        elif value is not None:
            value = str(value)
        out[col] = value
    if not out['type']:
        out['type'] = 'cancel'
    return out


def _row_to_dict(row):
    out = {}
    for col, key in COLUMNS:
        value = row[col]
        if value is not None:
            out[key] = value
    if 'fromPeriod' not in out:
        out['fromPeriod'] = 0
    return out


def _insert(con, item):
    cols = [c for c, _ in COLUMNS]
    con.execute(
        'INSERT INTO override (%s, created_at) VALUES (%s, ?)'
        % (', '.join(cols), ', '.join('?' * len(cols))),
        [item[c] for c in cols] + [datetime.datetime.now().isoformat(timespec='seconds')])


def _list(con):
    return [_row_to_dict(r) for r in con.execute('SELECT * FROM override ORDER BY id')]


def _bump(con):
    con.execute("UPDATE kv SET v = CAST(CAST(v AS INTEGER) + 1 AS TEXT) WHERE k = 'revision'")
    row = con.execute("SELECT v FROM kv WHERE k = 'revision'").fetchone()
    return int(row['v']) if row else 0


# ---------------------------------------------------------------------------
# 对外 API
# ---------------------------------------------------------------------------

def load(db_path=None):
    """→ 例外列表（按写入顺序）。没有任何记录就是空列表，不是错误。"""
    con = _open(db_path)
    try:
        return _list(con)
    finally:
        con.close()


def revision(db_path=None):
    con = _open(db_path)
    try:
        row = con.execute("SELECT v FROM kv WHERE k = 'revision'").fetchone()
        return int(row['v']) if row else 0
    finally:
        con.close()


def load_with_revision(db_path=None):
    con = _open(db_path)
    try:
        row = con.execute("SELECT v FROM kv WHERE k = 'revision'").fetchone()
        return _list(con), int(row['v']) if row else 0
    finally:
        con.close()


def append(item, db_path=None):
    """追加一条。读与写在同一事务里，所以并发 append 不会互相覆盖。"""
    clean = _clean(item)
    if clean is None:
        raise ValueError('缺少必需字段：' + '、'.join(REQUIRED))
    con = _open(db_path)
    try:
        with _Tx(con):
            _insert(con, clean)
            rev = _bump(con)
            return _list(con), rev
    finally:
        con.close()


def upsert(item, db_path=None):
    """同一「源位置」只保留一条：先删后插，两件事在同一个事务里。

    这就是原来 move/cancel 的「读列表 → 剔除同源 → 追加 → 整份写回」，
    只是搬进了事务。并发下不会再有「A 读到旧列表、B 写入、A 用旧列表覆盖」。
    """
    clean = _clean(item)
    if clean is None:
        raise ValueError('缺少必需字段：' + '、'.join(REQUIRED))
    con = _open(db_path)
    try:
        with _Tx(con):
            con.execute(
                'DELETE FROM override WHERE name = ? AND from_date = ? AND from_period = ?',
                (clean['name'], clean['from_date'], clean['from_period'] or 0))
            _insert(con, clean)
            return _list(con), _bump(con)
    finally:
        con.close()


def undo(name, from_date, from_period, db_path=None):
    """撤销某一处例外（按源位置定位）。"""
    con = _open(db_path)
    try:
        with _Tx(con):
            con.execute(
                'DELETE FROM override WHERE name = ? AND from_date = ? AND from_period = ?',
                (name, from_date, int(from_period)))
            rev = _bump(con)
            return _list(con), rev
    finally:
        con.close()


def clear(db_path=None):
    con = _open(db_path)
    try:
        with _Tx(con):
            con.execute('DELETE FROM override')
            rev = _bump(con)
            return [], rev
    finally:
        con.close()


def replace(items, db_path=None):
    """整份替换（兼容旧接口 save_overrides）。"""
    rows = [r for r in (_clean(x) for x in (items or [])) if r]
    con = _open(db_path)
    try:
        with _Tx(con):
            con.execute('DELETE FROM override')
            for r in rows:
                _insert(con, r)
            rev = _bump(con)
            return _list(con), rev
    finally:
        con.close()


def replace_if_revision(items, expected, db_path=None):
    """乐观并发：revision 对不上就不写，抛 RevisionConflict。

    前端目前是「动作式」写入（move / undo / clear），暂时用不到；
    留着是给脚本和以后的批量同步用——真丢了更新时至少能发现。
    """
    rows = [r for r in (_clean(x) for x in (items or [])) if r]
    con = _open(db_path)
    try:
        with _Tx(con):
            row = con.execute("SELECT v FROM kv WHERE k = 'revision'").fetchone()
            current = int(row['v']) if row else 0
            if expected is not None and int(expected) != current:
                raise RevisionConflict(current)
            con.execute('DELETE FROM override')
            for r in rows:
                _insert(con, r)
            return _list(con), _bump(con)
    finally:
        con.close()


class RevisionConflict(Exception):
    def __init__(self, current):
        super().__init__(f'调课记录已被改动（当前 revision={current}）')
        self.current = current
