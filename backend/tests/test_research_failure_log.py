import json
from types import SimpleNamespace
from app.research_agent import failure_log


def test_database_independent_log_is_private_and_excludes_exception_values(tmp_path):
    db=SimpleNamespace(path=tmp_path/'unavailable.db')
    try:
        raise ValueError('API_KEY=SECRET /private/full/path holdout-data')
    except ValueError as exc:
        assert failure_log.record(db,exc)
    path=tmp_path/'research-private/coordinator-failures.jsonl'
    text=path.read_text()
    assert all(value not in text for value in ('SECRET','holdout-data','/private/full/path'))
    event=json.loads(text)
    assert not event['state_committed'] and event['trace'][0]['class']=='ValueError'
    assert not db.path.exists()


def test_rotation_is_bounded_and_does_not_print_failed_writes(tmp_path,monkeypatch,capsys):
    monkeypatch.setattr(failure_log,'MAX_BYTES',500)
    db=SimpleNamespace(path=tmp_path/'db')
    for _ in range(20): assert failure_log.record(db,RuntimeError('secret'))
    assert len(list((tmp_path/'research-private').iterdir()))==3
    monkeypatch.setattr(failure_log.os,'open',lambda *a,**kw:(_ for _ in ()).throw(OSError('SECRET')))
    assert not failure_log.record(db,RuntimeError('original'))
    captured=capsys.readouterr()
    assert captured.out==captured.err==''


def test_coordinator_stops_after_three_failures_and_logs_without_database(tmp_path):
    from datetime import datetime,timezone
    from app.research_agent.director import ResearchDirector
    director=ResearchDirector.__new__(ResearchDirector)
    director.database=SimpleNamespace(path=tmp_path/'broken.db')
    director.clock=lambda:datetime.now(timezone.utc)
    director.stop=SimpleNamespace(is_set=lambda:False)
    director.wake=SimpleNamespace(wait=lambda _:None,clear=lambda:None)
    director.tick=lambda:(_ for _ in ()).throw(OSError('secret database location'))
    director._run()
    assert director.last_error=='director_stopped_after_storage_failures'
    lines=(tmp_path/'research-private/coordinator-failures.jsonl').read_text().splitlines()
    assert len(lines)==3 and 'secret database location' not in ''.join(lines)
