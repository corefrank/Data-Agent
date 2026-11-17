"""Extract and load one complete ODS snapshot; reusable by the project CLI."""
import argparse
import logging
from pathlib import Path

from .extract import extract_all
from .load import load_snapshot


def run_pipeline(replay: Path | None = None, page_size: int = 100):
    """Return (snapshot directory, manifest) after dlt loads the ODS."""
    if page_size < 1:
        raise ValueError('page_size must be positive')
    run_dir = replay.resolve() if replay is not None else extract_all(page_size)
    if not (run_dir / 'manifest.json').is_file():
        raise FileNotFoundError(f'缺少快照 manifest.json: {run_dir}')
    return run_dir, load_snapshot(run_dir)


def main():
    parser = argparse.ArgumentParser(description='仅运行 ETL / ODS 加载')
    parser.add_argument('--replay', type=Path, help='使用已有完整快照，不访问外部来源')
    parser.add_argument('--page-size', type=int, default=100)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    run_dir, manifest = run_pipeline(replay=args.replay, page_size=args.page_size)
    print(f"ODS 完成: {run_dir}\n状态: {manifest['status']}")


if __name__ == '__main__':
    main()
