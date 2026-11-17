import json
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env')
os.environ.setdefault('DLT_TELEMETRY', 'FALSE')


def now():
    return datetime.now(timezone.utc).isoformat()


def dsn():
    value = os.getenv('PG_DSN')
    if not value:
        raise ValueError('请复制 .env.example 为 .env，并配置 PG_DSN')
    return value


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
