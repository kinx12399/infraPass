import json
from pathlib import Path
from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateTable
from app.main import Base

def test_catalog_contract():
    rows = json.loads(Path('data/certificates.json').read_text(encoding='utf-8'))
    assert len(rows) >= 100
    assert len({r['slug'] for r in rows}) == len(rows)
    for r in rows:
        assert r['source'].startswith('https://')
        assert all(k in r for k in ['name','provider','category','audience','process','exam','study','renewal','events','verified_at'])
        assert isinstance(r['events'], list)
    assert {'정보처리기사','정보보안기사','CKA','CCNA','CPPG 개인정보관리사'} <= {r['name'] for r in rows}

def test_mysql_schema_compiles():
    for table in Base.metadata.sorted_tables:
        statement = str(CreateTable(table).compile(dialect=mysql.dialect()))
        assert 'CREATE TABLE' in statement
