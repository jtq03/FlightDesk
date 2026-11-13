import hashlib
import json
import os
import secrets
import sqlite3
import threading
import time
from pathlib import Path
from .models import Settings


class Conflict(Exception):
    pass


class Store:
    """Small durable state; aircraft positions intentionally stay out of SQLite."""
    def __init__(self, directory: Path):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        directory.chmod(0o700)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(str(directory / 'flightdesk.sqlite3'), check_same_thread=False)
        version = self.db.execute('PRAGMA user_version').fetchone()[0]
        if version > 1:
            self.db.close()
            raise RuntimeError('Database is newer than this app; use the matching software version')
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY, document TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS sessions (digest TEXT PRIMARY KEY, expires REAL NOT NULL)')
        initial = {'revision': 0, 'settings': Settings().model_dump(),
                   'desk': {'mode': 'map', 'aircraft_id': None},
                   'display': {'confirmed_angle': 0, 'requested_angle': 0, 'pending': None}}
        self.db.execute('INSERT OR IGNORE INTO state VALUES (1,?)', (json.dumps(initial),))
        columns = {row[1] for row in self.db.execute('PRAGMA table_info(sessions)')}
        for name, definition in [('kind', "TEXT NOT NULL DEFAULT 'legacy'"), ('label', "TEXT NOT NULL DEFAULT 'Previously paired browser'"), ('created', 'REAL NOT NULL DEFAULT 0')]:
            if name not in columns:
                self.db.execute('ALTER TABLE sessions ADD COLUMN '+name+' '+definition)
        self.db.execute('PRAGMA user_version=1')
        self.db.commit()
        code_path = directory / 'pairing-code'
        if not code_path.exists():
            fd = os.open(str(code_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, 'w') as f:
                f.write('%06d' % secrets.randbelow(1000000))
        code_path.chmod(0o600)
        self.pairing_code = code_path.read_text().strip()
        # A pending physical display change must never survive a restart.
        self.update(lambda d: d['display'].update(requested_angle=d['display']['confirmed_angle'], pending=None))
        self.update(lambda d: d.update(settings=Settings(**d['settings']).model_dump()))

    def read(self):
        with self.lock:
            return json.loads(self.db.execute('SELECT document FROM state WHERE id=1').fetchone()[0])

    def update(self, fn, expected=None):
        with self.lock:
            d = self.read()
            if expected is not None and d['revision'] != expected:
                raise Conflict('Settings changed on another screen. Reload and try again.')
            fn(d)
            d['revision'] += 1
            self.db.execute('UPDATE state SET document=? WHERE id=1', (json.dumps(d),))
            self.db.commit()
            return d

    def session(self, label="Phone", kind="phone"):
        token = secrets.token_urlsafe(32)
        with self.lock:
            self.db.execute('DELETE FROM sessions WHERE expires < ?', (time.time(),))
            self.db.execute('INSERT INTO sessions (digest,expires,kind,label,created) VALUES (?,?,?,?,?)', (self.digest(token), time.time() + 90*86400, kind, label, time.time()))
            self.db.commit()
        return token

    @staticmethod
    def digest(token):
        return hashlib.sha256(token.encode()).hexdigest()

    def authenticated(self, token):
        if not token:
            return False
        with self.lock:
            return self.db.execute('SELECT 1 FROM sessions WHERE digest=? AND expires>?',
                                   (self.digest(token), time.time())).fetchone() is not None

    def logout(self, token):
        with self.lock:
            self.db.execute('DELETE FROM sessions WHERE digest=?', (self.digest(token or ''),))
            self.db.commit()

    def close(self):
        self.db.close()

    def devices(self):
        with self.lock:
            rows=self.db.execute("SELECT substr(digest,1,16),label,created,expires FROM sessions WHERE kind='phone' AND expires>? ORDER BY created",(time.time(),)).fetchall()
            return [dict(zip(('id','name','created_at','expires_at'),row)) for row in rows]

    def revoke_device(self, ident):
        with self.lock:
            self.db.execute("DELETE FROM sessions WHERE kind='phone' AND substr(digest,1,16)=?",(ident,))
            self.db.commit()
