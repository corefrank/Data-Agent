import json
from unittest.mock import patch
import pytest
from src.extract import validate_response, http_session, extract_postgres
from src.load import recall_rows


def test_bad_payload_is_not_silent_empty():
    for value in ({}, {'results': []}, {'Count': 1, 'results': []},
                  {'Count': 1, 'results': [{}]}):
        with pytest.raises(ValueError):
            validate_response(value)
    assert validate_response({'Count': 0, 'results': []}) == []


def test_same_campaign_keeps_different_vehicle_models(tmp_path):
    raw = {'Count': 1, 'results': [{'NHTSACampaignNumber': 'TEST', 'Component': 'SEATS'}]}
    (tmp_path / 'r.json').write_text(json.dumps(raw))
    items = [dict(make='FORD', model=m, model_year=2020, file='r.json',
                  fetched_at='2026-11-17T00:00:00+00:00') for m in ('ESCAPE','EXPLORER','ESCAPE')]
    rows = list(recall_rows(tmp_path, {'run_id':'test', 'nhtsa':items}))
    assert len(rows) == 2
    assert {r['model'] for r in rows} == {'ESCAPE', 'EXPLORER'}


def test_http_retry_policy():
    with http_session() as session:
        retry = session.get_adapter('https://').max_retries
        assert retry.is_retry('GET', 429)
        assert retry.is_retry('GET', 503)
        assert not retry.is_retry('GET', 404)
        assert retry.total == 4


def test_invalid_page_size():
    with pytest.raises(ValueError):
        extract_postgres(None, page_size=0)
