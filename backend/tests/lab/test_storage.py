import pytest
from app.lab.storage import LabStore,StoreConflict

def test_immutable_records_parameterized_and_restart(tmp_path):
    path=tmp_path/'lab.db'; store=LabStore(path)
    store.put_record('kind',"x'; DROP TABLE records;--",{'data':1},immutable=True)
    with pytest.raises(StoreConflict): store.put_record('kind',"x'; DROP TABLE records;--",{'data':2})
    store.close(); store=LabStore(path)
    assert store.list_records('kind')==[{'data':1}]

def test_cursor_advances_hidden_sequences(tmp_path):
    store=LabStore(tmp_path/'lab.db'); store.put_record('episodes','e',{'campaign_id':'c'})
    store.append_event('e',type='episode_started')
    store.append_event('e',type='verdict_recorded',visibility='PRIVATE_EVALUATOR',payload={'secret_fixture':True})
    store.append_event('e',type='report_submitted')
    first=store.events('e',limit=2)
    assert [e['seq'] for e in first['events']]==[1]
    assert first['next_after']==2 and first['has_more']
    assert [e['seq'] for e in store.events('e',after=2)['events']]==[3]

def test_atomic_pointer_rejects_stale_parent(tmp_path):
    store=LabStore(tmp_path/'lab.db'); store.compare_and_set_pointer('p',None,'v0')
    store.compare_and_set_pointer('p','v0','v1')
    with pytest.raises(StoreConflict): store.compare_and_set_pointer('p','v0','bad')
    assert store.get_pointer('p')=='v1'

def test_ingestion_dedup_conflict_and_fk(tmp_path):
    store=LabStore(tmp_path/'lab.db'); store.put_record('episodes','e',{'campaign_id':'c'})
    assert store.associate_ingestion('p','root','e')
    assert not store.associate_ingestion('p','root','e')
    with pytest.raises(StoreConflict): store.associate_ingestion('p','other','e')

def test_outer_transaction_rolls_back_records_and_pointer_after_nested_writes(tmp_path):
    store=LabStore(tmp_path/'lab.db')
    store.put_record('jobs','j',{'state':'RUNNING'})
    with pytest.raises(KeyboardInterrupt):
        with store.transaction():
            store.put_record('jobs','j',{'state':'COMPLETED'})
            store.compare_and_set_pointer('active',None,'policy-v1')
            raise KeyboardInterrupt()
    assert store.get_record('jobs','j')=={'state':'RUNNING'}
    assert store.get_pointer('active') is None
    assert not store.db.in_transaction
    store.close()

def test_caught_inner_failure_rolls_back_only_its_changes(tmp_path):
    store=LabStore(tmp_path/'lab.db')
    with store.transaction():
        store.put_record('jobs','kept',{'state':'RUNNING'})
        with pytest.raises(ValueError):
            with store.transaction():
                store.put_record('jobs','discarded',{'state':'COMPLETED'})
                raise ValueError('Injected failure')
        store.put_record('jobs','also-kept',{'state':'QUEUED'})
    assert len(store.list_records('jobs'))==2
    assert store.get_record('jobs','discarded') is None
    store.close()

def test_schema_initialization_failure_closes_the_opened_connection(tmp_path):
    import sqlite3
    from unittest.mock import patch
    connection=sqlite3.connect(tmp_path/'lab.db',isolation_level=None)
    connection.execute('CREATE TABLE episode_registry(id TEXT PRIMARY KEY)')
    with patch('app.lab.storage.sqlite3.connect',return_value=connection):
        with pytest.raises(sqlite3.OperationalError):
            LabStore(tmp_path/'lab.db')
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute('SELECT 1')
