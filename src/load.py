import json
from datetime import date, datetime
from decimal import Decimal

from .common import ROOT, now, write_json
import dlt
from .extract import TABLES, validate_response


def recall_rows(run_dir, manifest):
    seen = set()
    for item in manifest['nhtsa']:
        payload = json.loads((run_dir / item['file']).read_text(encoding='utf-8'))
        for raw in validate_response(payload):
            # 同一 campaign 可跨车型/年款，不能只用 campaign_number 当主键。
            # 再纳入原始 component，避免同 campaign 的不同部件记录互相覆盖。
            key = (raw['NHTSACampaignNumber'], item['make'].upper(), item['model'].upper(),
                   int(item['model_year']), raw.get('Component', ''))
            if key in seen:
                continue
            seen.add(key)
            yield {
                'campaign_number': key[0], 'make': key[1], 'model': key[2], 'model_year': key[3],
                'component': key[4], 'manufacturer': raw.get('Manufacturer'),
                'report_received_date_raw': raw.get('ReportReceivedDate'),
                'summary': raw.get('Summary'), 'consequence': raw.get('Consequence'),
                'remedy': raw.get('Remedy'),
                'raw_json': json.dumps(raw, ensure_ascii=False),
                'source_system': 'nhtsa_api', 'is_synthetic': False,
                'extracted_at': datetime.fromisoformat(item['fetched_at']), 'run_id': manifest['run_id']}


def business_rows(run_dir, manifest, table):
    rows = json.loads((run_dir / f'pg_{table}.json').read_text(encoding='utf-8'))
    for row in rows:
        for key in ('sale_price', 'cost'):
            if key in row:
                row[key] = Decimal(row[key])
        for key in ('sale_date', 'service_date'):
            if key in row:
                row[key] = date.fromisoformat(row[key])
        row.update(source_system='postgres_simulated', run_id=manifest['run_id'],
                   extracted_at=datetime.fromisoformat(manifest['extracted_at']))
        yield row


def load_snapshot(run_dir):
    manifest = json.loads((run_dir / 'manifest.json').read_text(encoding='utf-8'))
    if manifest['status'] not in ('extracted', 'loaded', 'load_failed'):
        raise ValueError('Only complete extraction snapshots can be loaded')
    resources = [dlt.resource(recall_rows(run_dir, manifest), name='nhtsa_recalls',
                             write_disposition='replace', columns={
                                 'campaign_number': {'data_type': 'text'},
                                 'model_year': {'data_type': 'bigint'},
                                 'raw_json': {'data_type': 'text'}})]
    for table, key in TABLES.items():
        resources.append(dlt.resource(business_rows(run_dir, manifest, table), name=table,
                                      primary_key=key, write_disposition='replace'))
    pipeline = dlt.pipeline(pipeline_name='ford_ods',
                           pipelines_dir=str(ROOT / 'data/pipelines'),
                           destination=dlt.destinations.duckdb(str(ROOT / 'data/warehouse.duckdb')),
                           dataset_name='ods')
    try:
        info = pipeline.run(resources)
        info.raise_on_failed_jobs()
        manifest.update(status='loaded', loaded_at=now(), load_ids=info.loads_ids)
    except Exception as exc:
        manifest.update(status='load_failed', error_type=type(exc).__name__)
        raise
    finally:
        write_json(run_dir / 'manifest.json', manifest)
    print(info)
    return manifest
