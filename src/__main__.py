"""Unified CLI for the Automotive Data Engineering & AI Analytics Agent.

Usage:
  python -m src build                         # Seed -> ETL -> ODS checks -> dbt
  python -m src build --replay data/example_snapshot
  python -m src dashboard
  python -m src verify [--run data/example_snapshot]
"""
import argparse
import logging
import subprocess
from pathlib import Path

from .check import check
from .common import ROOT
from .pipeline import run_pipeline
from .seed import main as seed_business


def dbt_command(operation: str) -> None:
    subprocess.run(
        ['dbt', operation, '--project-dir', str(ROOT / 'dbt'),
         '--profiles-dir', str(ROOT / 'dbt')],
        cwd=ROOT, check=True,
    )


def latest_snapshot() -> Path:
    runs = sorted((ROOT / 'data/runs').glob('*/manifest.json'))
    if runs:
        return runs[-1].parent
    example = ROOT / 'data/example_snapshot'
    if (example / 'manifest.json').is_file():
        return example
    raise FileNotFoundError('没有可验证的快照；请先执行 build 或提供 --run')


def build(args) -> None:
    if args.replay is None and not args.skip_seed:
        print('[1/4] 初始化 PostgreSQL 模拟业务数据')
        seed_business()
    print('[2/4] 数据抽取和 dlt ODS 加载')
    run_dir, manifest = run_pipeline(replay=args.replay, page_size=args.page_size)
    print('[3/4] 检查 ODS 快照')
    check(run_dir)
    print('[4/4] dbt 构建 DWD / DWS / ADS，并执行数据测试')
    dbt_command('build')
    print(f"完成。快照: {run_dir} | ODS: {manifest['status']} | dbt build: passed")


def verify(run: Path | None = None) -> None:
    run_dir = run.resolve() if run is not None else latest_snapshot()
    check(run_dir)
    dbt_command('test')
    print(f'ODS 和 dbt 测试完成：{run_dir}')


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(
        prog='python -m src',
        description='一体化汽车数据工程与 Data Agent 演示系统',
    )
    commands = parser.add_subparsers(dest='command', required=True)

    full = commands.add_parser('build', help='PostgreSQL -> ETL -> ODS -> dbt')
    full.add_argument('--replay', type=Path, help='重放快照，跳过 PostgreSQL/NHTSA 抽取')
    full.add_argument('--skip-seed', action='store_true', help='不初始化模拟 PostgreSQL')
    full.add_argument('--page-size', type=int, default=100)

    etl = commands.add_parser('etl', help='只执行 ETL/ODS 加载与验收')
    etl.add_argument('--replay', type=Path)
    etl.add_argument('--page-size', type=int, default=100)

    checks = commands.add_parser('verify', help='检查 ODS 快照并运行 dbt test')
    checks.add_argument('--run', type=Path, help='指定快照目录')

    commands.add_parser('seed', help='只初始化 PostgreSQL 模拟业务数据')
    commands.add_parser('dashboard', help='打开 Streamlit 数据看板和 Agent')

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    if args.command in ('build', 'etl') and args.page_size < 1:
        parser.error('--page-size 必须是正整数')

    if args.command == 'build':
        build(args)
    elif args.command == 'etl':
        run_dir, manifest = run_pipeline(replay=args.replay, page_size=args.page_size)
        check(run_dir)
        print(f"ODS 完成: {run_dir} | 状态: {manifest['status']}")
    elif args.command == 'verify':
        verify(args.run)
    elif args.command == 'seed':
        seed_business()
    elif args.command == 'dashboard':
        subprocess.run(['streamlit', 'run', str(ROOT / 'app.py')], cwd=ROOT, check=True)


if __name__ == '__main__':
    main()
