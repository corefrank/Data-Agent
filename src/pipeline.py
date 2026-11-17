import argparse
import logging
from pathlib import Path
from .extract import extract_all
from .load import load_snapshot


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--replay', type=Path, help='重放完整 data/runs/<run_id> 快照，不请求外部来源')
    parser.add_argument('--page-size', type=int, default=100)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    run_dir = args.replay.resolve() if args.replay else extract_all(args.page_size)
    manifest = load_snapshot(run_dir)
    print(f"完成: {run_dir}\n状态: {manifest['status']}")


if __name__ == '__main__':
    main()
