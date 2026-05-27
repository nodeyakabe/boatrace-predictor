"""
前日払戻金データ収集（block_a用）

補完_払戻金データ.py と import_payouts_csv.py をサブプロセスで呼び出し、
前日分の払戻金を収集して DB に投入する。
"""
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent


def fetch_yesterday_payouts(target_date: str = None) -> int:
    """
    対象日の払戻金を収集して DB に投入する。

    Args:
        target_date: 対象日（YYYY-MM-DD）。省略時は前日。

    Returns:
        投入件数（概算）
    """
    if target_date is None:
        target_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

    print(f"払戻金収集対象日: {target_date}")

    # Phase 1: スクレイピング → CSV
    phase1 = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / 'scripts' / 'data_collection' / '補完_払戻金データ.py'),
            '--start-date', target_date,
            '--end-date', target_date,
            '--overwrite',
        ],
        cwd=str(PROJECT_ROOT),
        capture_output=False,
        text=True,
    )

    if phase1.returncode != 0:
        print(f"Phase 1 失敗 (exit code {phase1.returncode})")
        return 0

    # Phase 2: CSV → DB
    csv_dir = PROJECT_ROOT / 'data' / 'payouts_csv' / target_date[:4]
    csv_path = csv_dir / f"{target_date}.csv"

    if not csv_path.exists():
        print("CSVが存在しない。DB投入スキップ。")
        return 0

    phase2 = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / 'scripts' / 'data_collection' / 'import_payouts_csv.py'),
            '--dir', str(csv_dir),
        ],
        cwd=str(PROJECT_ROOT),
        capture_output=False,
        text=True,
    )

    if phase2.returncode != 0:
        print(f"Phase 2 失敗 (exit code {phase2.returncode})")
        return 0

    # CSV行数を投入件数の概算として返す
    try:
        with open(csv_path, encoding='utf-8') as f:
            rows = sum(1 for _ in f) - 1  # ヘッダ除く
        return max(rows, 0)
    except Exception:
        return 1


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', type=str, help='対象日 (YYYY-MM-DD)。省略時は前日。')
    args = parser.parse_args()
    count = fetch_yesterday_payouts(args.date)
    print(f"完了: {count}件")
