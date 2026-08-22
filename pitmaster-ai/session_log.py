"""SQLite persistence for PitMaster AI cook sessions."""
from __future__ import annotations
import json, sqlite3
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).parent
class SessionLog:
 def __init__(self,path:Path|str=ROOT/'data'/'pitmaster.db'):
  Path(path).parent.mkdir(parents=True,exist_ok=True); self.conn=sqlite3.connect(path); self.conn.row_factory=sqlite3.Row; self.conn.execute('CREATE TABLE IF NOT EXISTS sessions (id INTEGER PRIMARY KEY, started_at TEXT NOT NULL, food TEXT NOT NULL, method TEXT NOT NULL, plan_json TEXT NOT NULL, actual_temp_f REAL, notes TEXT, rating INTEGER)'); self.conn.commit()
 def save(self,food,method,plan,actual_temp_f=None,notes='',rating=None):
  cur=self.conn.execute('INSERT INTO sessions(started_at,food,method,plan_json,actual_temp_f,notes,rating) VALUES(?,?,?,?,?,?,?)',(datetime.now(timezone.utc).isoformat(),food,method,json.dumps(plan),actual_temp_f,notes,rating)); self.conn.commit(); return cur.lastrowid
 def history(self,limit=100): return [dict(x) for x in self.conn.execute('SELECT * FROM sessions ORDER BY id DESC LIMIT ?', (limit,))]
