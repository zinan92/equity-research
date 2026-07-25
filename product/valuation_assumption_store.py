"""Append-only owner storage for explicit valuation assumption receipts."""
from __future__ import annotations
import json,sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any,Mapping
from auth_store import AUTH_DB_PATH,initialize_auth
from data_store import connect
from data_core.e4_valuation_assumptions import compile_assumption_receipt
SCHEMA="""CREATE TABLE IF NOT EXISTS e4_valuation_assumptions (receipt_hash TEXT PRIMARY KEY,ticker TEXT NOT NULL,author_id TEXT NOT NULL,payload_json TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP); CREATE TRIGGER IF NOT EXISTS e4_valuation_assumptions_no_update BEFORE UPDATE ON e4_valuation_assumptions BEGIN SELECT RAISE(ABORT,'append-only'); END; CREATE TRIGGER IF NOT EXISTS e4_valuation_assumptions_no_delete BEFORE DELETE ON e4_valuation_assumptions BEGIN SELECT RAISE(ABORT,'append-only'); END;"""
class ValuationAssumptionStoreError(RuntimeError):pass
def _init(db:Path):
 initialize_auth(db)
 with closing(connect(db)) as c:c.executescript(SCHEMA);c.commit()
def _owner(m:Mapping[str,Any],c:sqlite3.Connection):
 r=c.execute('SELECT role,status FROM members WHERE id=?',(m.get('id'),)).fetchone()
 if not r or r['role']!='owner' or r['status']!='active':raise PermissionError('owner access required')
def append_assumption(member:Mapping[str,Any],payload:Mapping[str,Any],db:Path=AUTH_DB_PATH)->dict:
 _init(db);value=compile_assumption_receipt({**payload,'author_id':member.get('id')})
 with closing(connect(db)) as c:
  c.execute('BEGIN IMMEDIATE');_owner(member,c)
  try:c.execute('INSERT INTO e4_valuation_assumptions(receipt_hash,ticker,author_id,payload_json) VALUES(?,?,?,?)',(value['receipt_hash'],value['ticker'],member['id'],json.dumps(value,ensure_ascii=False,sort_keys=True)))
  except sqlite3.IntegrityError as e:raise ValuationAssumptionStoreError('assumption receipt already exists') from e
  c.commit()
 return value
def export_assumptions(member:Mapping[str,Any],db:Path=AUTH_DB_PATH)->dict:
 _init(db)
 with closing(connect(db)) as c:
  _owner(member,c); rows=c.execute('SELECT payload_json FROM e4_valuation_assumptions ORDER BY created_at,receipt_hash').fetchall()
 return {'schema_version':'e4-s4-valuation-assumption-export-v1','data_kind':'analyst_judgment','receipts':[json.loads(r['payload_json']) for r in rows],'truth_boundary':{'no_default_assumptions':True,'does_not_change_e4_acceptance':True}}
