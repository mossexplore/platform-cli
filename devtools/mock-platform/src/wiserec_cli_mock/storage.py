"""Transactional, workspace-scoped entity storage."""
import json
import sqlite3
from contextlib import contextmanager


class Store:
    def __init__(self, root):
        self.root = root
        self.path = root / 'state.sqlite3'

    @contextmanager
    def transaction(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                db.row_factory = sqlite3.Row
                db.execute('PRAGMA foreign_keys=ON')
                db.execute('BEGIN IMMEDIATE')
                yield db
        finally:
            db.close()

    def create(self):
        with self.transaction() as db:
            db.execute('CREATE TABLE entities(scope TEXT, kind TEXT, id TEXT, payload TEXT, PRIMARY KEY(scope,kind,id))')
            db.execute('CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT)')
            db.execute("INSERT INTO meta VALUES('schema', '1')")
            db.execute("INSERT INTO meta VALUES('clock', '0')")
            db.execute('CREATE TABLE faults(path TEXT PRIMARY KEY, status INTEGER, remaining INTEGER)')

    def validate(self):
        if not self.path.is_file():
            raise ValueError('演示数据库不存在，请先初始化工作区')
        with self.transaction() as db:
            if db.execute("SELECT value FROM meta WHERE key='schema'").fetchone()[0] != '1':
                raise ValueError('不兼容的演示数据库版本')
            if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise ValueError('演示数据库损坏')

    @staticmethod
    def put(db, scope, kind, identifier, value):
        db.execute('INSERT OR REPLACE INTO entities VALUES(?,?,?,?)',
                   (scope, kind, identifier, json.dumps(value, ensure_ascii=False)))

    @staticmethod
    def get(db, scope, kind, identifier):
        row = db.execute('SELECT payload FROM entities WHERE scope=? AND kind=? AND id=?',
                         (scope, kind, identifier)).fetchone()
        if row is None:
            raise KeyError(f'{kind} {identifier} 不存在或不属于当前业务')
        value = json.loads(row[0])
        if value.get("_deleted"):
            raise KeyError(f"{kind} {identifier} 已删除")
        return value

    @staticmethod
    def items(db, scope, kind):
        rows = [json.loads(row[0]) for row in db.execute(
            'SELECT payload FROM entities WHERE scope=? AND kind=? ORDER BY rowid', (scope, kind))]
        return [value for value in rows if not value.get('_deleted')]
