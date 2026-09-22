import sqlite3
from concurrent.futures import ThreadPoolExecutor
import pytest
from cca_lab.db import init, connect, SCHEMA_VERSION
from cca_lab.models import Query
from cca_lab.worker import recover_interrupted_work


def dump():
    with connect() as db:
        return '\n'.join(db.iterdump())


def test_fresh_concurrent_and_idempotent_startup(tmp_path, monkeypatch):
    monkeypatch.setenv('CCA_LAB_DATA', str(tmp_path))
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(lambda _: init(), range(12)))
    with connect() as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == SCHEMA_VERSION
        db.execute("INSERT INTO tasks VALUES('task',1,'original saved JSON',42)")
    before = dump()
    init(); init()
    assert dump() == before


@pytest.mark.parametrize('damage', ['version', 'column', 'index', 'partial'])
def test_unsupported_database_is_not_modified(tmp_path, monkeypatch, damage):
    monkeypatch.setenv('CCA_LAB_DATA', str(tmp_path))
    init()
    with connect() as db:
        if damage == 'version': db.execute('PRAGMA user_version=5')
        if damage == 'column': db.execute('ALTER TABLE jobs DROP COLUMN fallback_count')
        if damage == 'index': db.execute('DROP INDEX result_errors')
        if damage == 'partial': db.execute('DROP TABLE results')
    before = dump()
    with pytest.raises(RuntimeError, match='Unsupported CCA-Lab database'):
        init()
    assert dump() == before


def test_crash_recovery_preserves_results_and_marks_timing(tmp_path, monkeypatch):
    monkeypatch.setenv('CCA_LAB_DATA', str(tmp_path))
    init()
    with connect() as db:
        db.execute("INSERT INTO datasets(id,name,path,bytes,delimiter,encoding,status,created) VALUES('d','D','unused',0,',','utf-8','ready',0)")
        db.execute("INSERT INTO jobs(id,name,dataset_id,snapshot,status,total,created,updated,active_since,runtime_complete,active_seconds) VALUES('j','J','d','{}','running',1,0,0,123,1,10)")
        db.execute("INSERT INTO predictions(id,name,dataset_id,created,artifact_status) VALUES('p','P','d',0,'building')")
    recover_interrupted_work()
    with connect() as db:
        row = db.execute('SELECT * FROM jobs').fetchone()
        assert row['active_since'] is None and row['runtime_complete'] == 0 and row['active_seconds'] == 10
        assert row['status'] == 'running'
        assert db.execute('SELECT artifact_status FROM predictions').fetchone()[0] == 'pending'


def test_only_current_protocol_metadata_is_accepted():
    assert Query(model='m', prompt_protocol='experiment-v3').prompt_protocol == 'experiment-v3'
    with pytest.raises(ValueError):
        Query(model='m', prompt_protocol='unsupported')


def test_previous_schema_rejected_without_migration(tmp_path,monkeypatch):
    from cca_lab.db import SCHEMA
    monkeypatch.setenv('CCA_LAB_DATA',str(tmp_path))
    with sqlite3.connect(tmp_path/'cca_lab.sqlite') as db:
        db.executescript(SCHEMA.split('CREATE TABLE llm_requests')[0])
        db.execute('PRAGMA user_version=6')
    before=dump()
    with pytest.raises(RuntimeError,match='Unsupported CCA-Lab database'):init()
    assert dump()==before


def test_previous_protocol_is_rejected():
    with pytest.raises(ValueError):Query(model='m',prompt_protocol='cca-reference-v2')
