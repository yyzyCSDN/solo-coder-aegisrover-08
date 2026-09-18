import sqlite3, json, threading
from pathlib import Path

class Store:

    def __init__(self, path=':memory:'):
        self.path = str(path)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.execute('create table if not exists kv(namespace text,key text,value text,version integer,primary key(namespace,key))')
        self.db.commit()

    def get(self, ns, key):
        row = self.db.execute('select value,version from kv where namespace=? and key=?', (ns, key)).fetchone()
        return None if row is None else (json.loads(row[0]), row[1])

    def put(self, ns, key, value, expected=None):
        with self.lock:
            cur = self.get(ns, key)
            if expected is not None and (cur is None or cur[1] != expected):
                raise ValueError('version conflict')
            version = 1 if cur is None else cur[1] + 1
            self.db.execute('insert into kv values(?,?,?,?) on conflict(namespace,key) do update set value=excluded.value,version=excluded.version', (ns, key, json.dumps(value, sort_keys=True), version))
            self.db.commit()
            return version

    def list(self, ns):
        return [(r[0], json.loads(r[1]), r[2]) for r in self.db.execute('select key,value,version from kv where namespace=? order by key', (ns,))]
