"""先完整抓取并留存原始快照；任何来源失败均不启动 ODS 加载。"""
import json
import logging
import time
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row
from psycopg import sql
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .common import ROOT, dsn, now, write_json

LOG = logging.getLogger(__name__)
API = 'https://api.nhtsa.gov/recalls/recallsByVehicle'
TABLES = {'dealers': 'dealer_id', 'vehicles': 'vehicle_id', 'service_orders': 'order_id'}


def http_session():
    session = requests.Session()
    retry = Retry(total=4, backoff_factor=1, status_forcelist=[429,500,502,503,504],
                  allowed_methods=['GET'], respect_retry_after_header=True)
    session.mount('https://', HTTPAdapter(max_retries=retry))
    session.headers['User-Agent'] = 'vehicle-data-learning-project/1.0'
    return session


def validate_response(payload):
    # HTTP 200 不一定代表有效数据，不能把异常响应当作“零召回”。
    if not isinstance(payload, dict) or not isinstance(payload.get('results'), list):
        raise ValueError('NHTSA response missing results list')
    rows = payload['results']
    if 'Count' not in payload or int(payload['Count']) != len(rows):
        raise ValueError('NHTSA Count mismatch')
    if any(not r.get('NHTSACampaignNumber') for r in rows):
        raise ValueError('NHTSA campaign key missing')
    return rows


def extract_nhtsa(run_dir, specs):
    manifest = []
    with http_session() as session:
        for i, spec in enumerate(specs):
            params = {'make': spec['make'], 'model': spec['model'], 'modelYear': spec['model_year']}
            response = session.get(API, params=params, timeout=(10,60))
            response.raise_for_status()
            payload = response.json()
            rows = validate_response(payload)
            path = f'nhtsa_{i}.json'
            write_json(run_dir / path, payload)
            manifest.append(dict(spec, file=path, count=len(rows), fetched_at=now(), url=response.url))
            LOG.info('NHTSA %s %s %s: %s rows', *spec.values(), len(rows))
            time.sleep(0.2)
    return manifest


def extract_postgres(run_dir, page_size=100):
    if page_size < 1:
        raise ValueError('page_size must be positive')
    # 同一个 REPEATABLE READ 只读事务保证三张表及其分页使用一致快照。
    # 连接/查询失败时重新抽取整个快照，避免恢复后混合两个时间点的数据。
    for attempt in range(3):
        try:
            counts = {}
            with psycopg.connect(dsn(), connect_timeout=10, row_factory=dict_row) as conn:
                conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
                for table, key in TABLES.items():
                    rows, last_id, pages = [], None, 0
                    while True:
                        if last_id is None:
                            query = sql.SQL('SELECT * FROM business.{} ORDER BY {} LIMIT %s').format(
                                sql.Identifier(table), sql.Identifier(key))
                            params = (page_size,)
                        else:
                            query = sql.SQL('SELECT * FROM business.{} WHERE {} > %s ORDER BY {} LIMIT %s').format(
                                sql.Identifier(table), sql.Identifier(key), sql.Identifier(key))
                            params = (last_id, page_size)
                        page = conn.execute(query, params).fetchall()
                        if not page:
                            break
                        rows.extend(page)
                        last_id = page[-1][key]
                        pages += 1
                    write_json(run_dir / f'pg_{table}.json', rows)
                    counts[table] = {'count': len(rows), 'pages': pages}
                    LOG.info('Postgres %s: %s rows / %s pages', table, len(rows), pages)
            return counts
        except (psycopg.OperationalError, psycopg.InterfaceError):
            if attempt == 2:
                raise
            LOG.warning('Postgres extraction retry %s', attempt + 1)
            time.sleep(2 ** attempt)


def extract_all(page_size=100):
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    run_dir = ROOT / 'data/runs' / run_id
    run_dir.mkdir(parents=True)
    manifest = {'run_id': run_id, 'started_at': now(), 'status': 'extracting'}
    write_json(run_dir / 'manifest.json', manifest)
    try:
        specs = json.loads((ROOT / 'config/vehicles.json').read_text())
        manifest['nhtsa'] = extract_nhtsa(run_dir, specs)
        manifest['postgres'] = extract_postgres(run_dir, page_size)
        manifest.update(status='extracted', extracted_at=now())
    except Exception as exc:
        manifest.update(status='failed', error_type=type(exc).__name__)
        raise
    finally:
        write_json(run_dir / 'manifest.json', manifest)
    return run_dir
