"""The unified command must preserve the ordering of pipeline stages."""
from pathlib import Path
from types import SimpleNamespace

from src import __main__ as cli


def test_build_orchestrates_seed_etl_ods_validation_and_dbt(monkeypatch, tmp_path):
    events = []
    monkeypatch.setattr(cli, 'seed_business', lambda: events.append('seed'))
    monkeypatch.setattr(cli, 'run_pipeline', lambda **kwargs: (
        events.append('etl') or (tmp_path, {'status': 'loaded'})
    ))
    monkeypatch.setattr(cli, 'check', lambda path: events.append('check'))
    monkeypatch.setattr(cli, 'dbt_command', lambda operation: events.append(operation))

    cli.build(SimpleNamespace(replay=None, skip_seed=False, page_size=100))
    assert events == ['seed', 'etl', 'check', 'build']


def test_replay_never_initializes_postgres(monkeypatch, tmp_path):
    events = []
    monkeypatch.setattr(cli, 'seed_business', lambda: events.append('seed'))
    monkeypatch.setattr(cli, 'run_pipeline', lambda **kwargs: (
        events.append('replay') or (tmp_path, {'status': 'loaded'})
    ))
    monkeypatch.setattr(cli, 'check', lambda path: events.append('check'))
    monkeypatch.setattr(cli, 'dbt_command', lambda operation: events.append(operation))

    cli.build(SimpleNamespace(replay=tmp_path, skip_seed=False, page_size=100))
    assert events == ['replay', 'check', 'build']
