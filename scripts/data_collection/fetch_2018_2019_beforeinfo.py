# -*- coding: utf-8 -*-
"""
2018-2019年のbeforeinfo（直前情報）を収集してCSV保存・DB投入するスクリプト

【前提条件】
- races/entries/results が DB に投入済みであること
- fetch_2018_2019_monthly.py + import_races_csv.py が完了済みであること

【特徴】
- collect_beforeinfo_to_csv_parallel.py は再起動耐性あり（CSV内の取得済みをスキップ）
- CSV→DB投入は import_beforeinfo_csv_to_db.py を使用

【使用方法】
  # 通常実行（収集→DB投入まで自動）
  python scripts/data_collection/fetch_2018_2019_beforeinfo.py

  # 収集のみ（DB投入は後で手動）
  python scripts/data_collection/fetch_2018_2019_beforeinfo.py --csv-only

  # 並列数を変更
  python scripts/data_collection/fetch_2018_2019_beforeinfo.py --workers 12
"""

import sys
import io
import sqlite3
import subprocess
import argparse
from pathlib import Path
from datetime import datetime

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

PROJECT_ROOT = Path(__file__).parent.parent.parent
OUTPUT_DIR_2018 = PROJECT_ROOT / "data" / "csv" / "beforeinfo" / "2018"
OUTPUT_DIR_2019 = PROJECT_ROOT / "data" / "csv" / "beforeinfo" / "2019"
LOG_FILE = PROJECT_ROOT / "data" / "csv" / "beforeinfo" / "fetch_2018_2019_log.txt"


def log(message: str):
    """ログ出力（標準出力 + ファイル）"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{timestamp}] {message}"
    print(line)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(line + "\n")


def run_cmd(cmd: list, timeout: int, label: str) -> bool:
    """コマンドを実行して成否を返す"""
    log(f"[{label}] 開始")
    log(f"  コマンド: {' '.join(str(c) for c in cmd)}")
    try:
        result = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            timeout=timeout,
            text=True,
            encoding='utf-8',
            errors='replace',
        )
        if result.returncode == 0:
            log(f"[{label}] ✅ 完了")
            return True
        else:
            log(f"[{label}] ❌ 失敗 (returncode={result.returncode})")
            return False
    except subprocess.TimeoutExpired:
        log(f"[{label}] ❌ タイムアウト")
        return False
    except Exception as e:
        log(f"[{label}] ❌ 例外: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description='2018-2019年のbeforeinfo収集',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument('--workers', type=int, default=16,
                        help='並列ワーカー数（デフォルト: 16）')
    parser.add_argument('--timeout', type=int, default=10,
                        help='HTTPタイムアウト秒（デフォルト: 10）')
    parser.add_argument('--csv-only', action='store_true',
                        help='CSV収集のみ（DB投入を行わない）')
    args = parser.parse_args()

    OUTPUT_DIR_2018.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR_2019.mkdir(parents=True, exist_ok=True)

    # --- 前提条件チェック: 2018-2019年のレースデータがDBに存在するか確認 ---
    db_path = PROJECT_ROOT / "data" / "boatrace.db"
    if not db_path.exists():
        print(f"❌ DBファイルが見つかりません: {db_path}")
        sys.exit(1)

    try:
        conn = sqlite3.connect(str(db_path), timeout=30.0)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM races WHERE race_date BETWEEN '2018-01-01' AND '2019-12-31'"
        )
        race_count = cursor.fetchone()[0]
        conn.close()
    except Exception as e:
        print(f"❌ DB確認エラー: {e}")
        sys.exit(1)

    if race_count == 0:
        print("❌ 前提条件エラー: DBに2018-2019年のレースデータが存在しません。")
        print("   先に fetch_2018_2019_monthly.py を実行してください:")
        print("   python scripts/data_collection/fetch_2018_2019_monthly.py")
        sys.exit(1)
    elif race_count < 50000:
        print(f"⚠️  警告: 2018-2019年のレース数が少ない可能性があります（現在: {race_count:,}件）")
        print("   期待値は約110,000件（2年間 × 55,000件/年）")
        print("   fetch_2018_2019_monthly.py が完了していない場合は先に完了させてください。")
        print("   このまま続けますか？ 既存レースのbeforeinfoのみ収集します。")
        print()
    else:
        log(f"前提条件OK: 2018-2019年 {race_count:,}件のレースが存在します")

    print("=" * 70)
    print("2018-2019年 beforeinfo 収集")
    print("=" * 70)
    print(f"2018年出力先: {OUTPUT_DIR_2018}")
    print(f"2019年出力先: {OUTPUT_DIR_2019}")
    print(f"並列数:       {args.workers}スレッド")
    print(f"タイムアウト: {args.timeout}秒")
    print()
    print("※ 再起動耐性あり: 中断後に再実行すると取得済みレースを自動スキップします")
    print()

    collect_script = str(PROJECT_ROOT / "scripts" / "data_collection" / "collect_beforeinfo_to_csv_parallel.py")
    import_script  = str(PROJECT_ROOT / "scripts" / "data_collection" / "import_beforeinfo_csv_to_db.py")

    # --- Step 1: 2018年 beforeinfo 収集 ---
    print("=" * 60)
    print("Step 1/4: 2018年 beforeinfo 収集")
    print("=" * 60)
    ok_2018 = run_cmd(
        [sys.executable, collect_script,
         "--start", "2018-01-01",
         "--end",   "2018-12-31",
         "--output", str(OUTPUT_DIR_2018),
         "--workers", str(args.workers),
         "--timeout", str(args.timeout)],
        timeout=36000,  # 10時間タイムアウト
        label="2018年beforeinfo収集"
    )

    # --- Step 2: 2019年 beforeinfo 収集 ---
    print()
    print("=" * 60)
    print("Step 2/4: 2019年 beforeinfo 収集")
    print("=" * 60)
    ok_2019 = run_cmd(
        [sys.executable, collect_script,
         "--start", "2019-01-01",
         "--end",   "2019-12-31",
         "--output", str(OUTPUT_DIR_2019),
         "--workers", str(args.workers),
         "--timeout", str(args.timeout)],
        timeout=36000,  # 10時間タイムアウト
        label="2019年beforeinfo収集"
    )

    print()
    print("=" * 60)
    print("収集フェーズ完了")
    print(f"  2018年: {'✅ 完了' if ok_2018 else '❌ 失敗（再実行で再開可能）'}")
    print(f"  2019年: {'✅ 完了' if ok_2019 else '❌ 失敗（再実行で再開可能）'}")
    print("=" * 60)

    if args.csv_only:
        print("\n--csv-only モード。DB投入は手動で実行してください:")
        print(f"  python scripts/data_collection/import_beforeinfo_csv_to_db.py --input {OUTPUT_DIR_2018}")
        print(f"  python scripts/data_collection/import_beforeinfo_csv_to_db.py --input {OUTPUT_DIR_2019}")
        return

    # --- Step 3: 2018年 DB投入 ---
    print()
    print("=" * 60)
    print("Step 3/4: 2018年 beforeinfo → DB投入")
    print("=" * 60)
    ok_import_2018 = run_cmd(
        [sys.executable, import_script,
         "--input", str(OUTPUT_DIR_2018)],
        timeout=3600,
        label="2018年beforeinfo DB投入"
    )

    # --- Step 4: 2019年 DB投入 ---
    print()
    print("=" * 60)
    print("Step 4/4: 2019年 beforeinfo → DB投入")
    print("=" * 60)
    ok_import_2019 = run_cmd(
        [sys.executable, import_script,
         "--input", str(OUTPUT_DIR_2019)],
        timeout=3600,
        label="2019年beforeinfo DB投入"
    )

    # --- 最終サマリー ---
    print()
    print("=" * 70)
    print("beforeinfo 収集・投入 完了サマリー")
    print("=" * 70)
    all_ok = ok_2018 and ok_2019 and ok_import_2018 and ok_import_2019
    print(f"  2018年収集:    {'✅' if ok_2018       else '❌'}")
    print(f"  2019年収集:    {'✅' if ok_2019       else '❌'}")
    print(f"  2018年DB投入:  {'✅' if ok_import_2018 else '❌'}")
    print(f"  2019年DB投入:  {'✅' if ok_import_2019 else '❌'}")

    if all_ok:
        log("🎉 beforeinfo 収集・DB投入 全完了！")
        print()
        print("次のステップ:")
        print("  1. 統計指標再生成:")
        print("     python scripts/data_collection/build_indicator_stats.py --year 2018")
        print("     python scripts/data_collection/build_indicator_stats.py --year 2019")
        print("  2. advance予測生成:")
        print("     python scripts/prediction/generate_advance_fast.py --year 2018")
        print("     python scripts/prediction/generate_advance_fast.py --year 2019")
        print("  3. before予測生成:")
        print("     python scripts/prediction/generate_before_fast.py --year 2018")
        print("     python scripts/prediction/generate_before_fast.py --year 2019")
        print("  4. バックテスト:")
        print("     python scripts/backtest/standard_backtest_unique.py --full")
    else:
        print()
        print("⚠️  一部失敗があります。再実行すると続きから開始します:")
        print("  python scripts/data_collection/fetch_2018_2019_beforeinfo.py")


if __name__ == '__main__':
    main()
