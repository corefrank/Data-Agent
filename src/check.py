"""加载后验收：主键、外键、模拟标签、快照行数；失败返回非零退出码。"""
import argparse
import json
from pathlib import Path
import duckdb
from .common import ROOT
from .extract import TABLES
from .load import recall_rows


def check(run_dir):
    manifest = json.loads((run_dir / 'manifest.json').read_text(encoding='utf-8'))
    assert manifest['status'] == 'loaded', 'Snapshot not loaded'
    expected = {t: item['count'] for t, item in manifest['postgres'].items()}
    expected['nhtsa_recalls'] = sum(1 for _ in recall_rows(run_dir, manifest))
    with duckdb.connect(str(ROOT / 'data/warehouse.duckdb'), read_only=True) as conn:
        for table, count in expected.items():
            actual = conn.execute(f'SELECT count(*) FROM ods.{table}').fetchone()[0]
            assert actual == count, (table, actual, count)
            bad_run = conn.execute(f'SELECT count(*) FROM ods.{table} WHERE run_id IS NULL OR run_id <> ?',
                                   [manifest['run_id']]).fetchone()[0]
            assert bad_run == 0, f'{table}: stale run rows'
            print(f'PASS ods.{table}: {actual} rows')
        for table, key in TABLES.items():
            count, distinct, nulls = conn.execute(
                f'SELECT count(*), count(DISTINCT {key}), count(*) FILTER (WHERE {key} IS NULL) FROM ods.{table}'
            ).fetchone()
            assert count == distinct and nulls == 0, f'{table}: bad key'
            assert conn.execute(f'SELECT count(*) FROM ods.{table} WHERE is_synthetic IS DISTINCT FROM true').fetchone()[0] == 0
        assert conn.execute('''SELECT count(*) FROM ods.vehicles v LEFT JOIN ods.dealers d
                             USING(dealer_id) WHERE d.dealer_id IS NULL''').fetchone()[0] == 0
        assert conn.execute('''SELECT count(*) FROM ods.service_orders s LEFT JOIN ods.vehicles v
                             USING(vehicle_id) WHERE v.vehicle_id IS NULL''').fetchone()[0] == 0
        assert conn.execute('SELECT count(*) FROM ods.nhtsa_recalls WHERE is_synthetic IS DISTINCT FROM false').fetchone()[0] == 0
        print('PASS primary keys / foreign keys / provenance / run_id')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', type=Path)
    args = parser.parse_args()
    runs = sorted((ROOT / 'data/runs').glob('*/manifest.json'))
    if not args.run and not runs:
        raise SystemExit('请先运行 python -m src.pipeline')
    check(args.run or runs[-1].parent)


if __name__ == '__main__':
    main()
