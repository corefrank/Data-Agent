"""Data Agent checks that do not call an LLM or depend on a local warehouse."""
import pandas as pd
import pytest

from src import agent


@pytest.mark.parametrize('sql', [
    'DELETE FROM dashboard',
    'SELECT * FROM another_table',
    'SELECT * FROM dashboard; SELECT * FROM dashboard',
    'WITH x AS (SELECT * FROM dashboard) SELECT * FROM x',
    "SELECT * FROM read_csv('local.csv')",
])
def test_sql_validator_rejects_unsafe_queries(sql):
    with pytest.raises(ValueError):
        agent.validate_sql(sql)


def test_sql_validator_allows_ads_aggregation():
    sql = agent.validate_sql('SELECT model, SUM(simulated_vehicle_count) AS total FROM dashboard GROUP BY model')
    assert 'dashboard' in sql.lower()
    assert 'SUM(' in sql.upper()


def test_agent_recovers_after_one_failed_sql(monkeypatch):
    responses = iter([
        'SELECT * FROM invalid_table',
        'SELECT SUM(simulated_vehicle_count) AS total FROM dashboard',
        '共有 300 辆模拟车辆。',
    ])
    calls = []

    def fake_sql(sql):
        calls.append(sql)
        if len(calls) == 1:
            raise ValueError('表不存在')
        return sql, pd.DataFrame([{'total': 300}]), False

    monkeypatch.setattr(agent, 'call_model', lambda messages: next(responses))
    monkeypatch.setattr(agent, 'run_sql', fake_sql)
    monkeypatch.setattr(agent, 'quality_checks', lambda: {'异常数': 0})

    result = agent.run_agent('模拟车辆总数是多少？')
    assert result['attempts'] == 2
    assert len(calls) == 2
    assert result['rows'][0]['total'] == 300
    assert result['checks'] == {'异常数': 0}
    assert '300' in result['answer']
