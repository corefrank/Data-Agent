import psycopg
from .common import ROOT, dsn


def main():
    with psycopg.connect(dsn(), connect_timeout=10) as conn:
        conn.execute((ROOT / 'sql/business.sql').read_text(encoding='utf-8'))
        for name in ('dealers', 'vehicles', 'service_orders'):
            count = conn.execute(f'SELECT count(*) FROM business.{name}').fetchone()[0]
            print(f'business.{name}: {count}')


if __name__ == '__main__':
    main()
