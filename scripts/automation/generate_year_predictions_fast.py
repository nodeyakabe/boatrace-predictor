#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
年度単位の予想生成スクリプト（fast_prediction_generator利用版）

generate_predictions.pyの代替として、fast_prediction_generator.pyを
日付ループで実行して年度全体の予想を生成します。
"""
import sys
import io
import sqlite3
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "boatrace.db"

def get_race_dates(year: str) -> list:
    """指定年度の開催日一覧を取得"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT race_date
        FROM races
        WHERE race_date LIKE ? || '%'
        ORDER BY race_date
    """, (year,))
    dates = [row[0] for row in cursor.fetchall()]
    conn.close()
    return dates

def main():
    import argparse
    parser = argparse.ArgumentParser(description='年度単位の予想生成（fast版）')
    parser.add_argument('--year', type=str, required=True, help='対象年度（例: 2020）')
    parser.add_argument('--type', type=str, default='before', choices=['advance', 'before'], help='予測タイプ')
    parser.add_argument('--force', action='store_true', help='既存予想を上書き')
    args = parser.parse_args()

    print("="*70)
    print(f"{args.year}年 {args.type}予想生成（fast版）")
    print("="*70)
    print(f"開始時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    dates = get_race_dates(args.year)
    total_dates = len(dates)
    print(f"対象日数: {total_dates}日")

    success_dates = 0
    failed_dates = 0
    start_time = datetime.now()

    for i, date in enumerate(dates, 1):
        print(f"\n[{i}/{total_dates}] {date} 処理中...")

        cmd = [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "prediction" / "fast_prediction_generator.py"),
            "--date", date,
            "--type", args.type
        ]

        if args.force:
            cmd.append("--force")

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=600)
            if result.returncode == 0:
                success_dates += 1
                # 成功時は1行サマリーのみ
                if "既存: " in result.stdout:
                    # 既存スキップの場合
                    for line in result.stdout.split('\n'):
                        if "既存スキップ:" in line:
                            print(f"  ✅ {line.strip()}")
                            break
                else:
                    # 新規生成の場合
                    for line in result.stdout.split('\n'):
                        if "生成完了:" in line or "更新完了:" in line:
                            print(f"  ✅ {line.strip()}")
                            break
            else:
                failed_dates += 1
                print(f"  ❌ 失敗（終了コード: {result.returncode}）")
                if result.stderr:
                    print(f"     エラー: {result.stderr[:200]}")
        except subprocess.TimeoutExpired:
            failed_dates += 1
            print(f"  ❌ タイムアウト（600秒超過）")
        except Exception as e:
            failed_dates += 1
            print(f"  ❌ エラー: {e}")

        # 進捗表示
        if i % 10 == 0 or i == total_dates:
            elapsed = (datetime.now() - start_time).total_seconds()
            rate = i / elapsed if elapsed > 0 else 0
            remaining = (total_dates - i) / rate if rate > 0 else 0
            eta = datetime.now() + timedelta(seconds=remaining)
            print(f"  進捗: {i}/{total_dates} ({100*i/total_dates:.1f}%) "
                  f"成功={success_dates} 失敗={failed_dates} "
                  f"残り{remaining/60:.0f}分 完了予定: {eta.strftime('%H:%M')}")

    elapsed = (datetime.now() - start_time).total_seconds()

    print("\n" + "="*70)
    print("完了サマリー")
    print("="*70)
    print(f"対象日数: {total_dates}日")
    print(f"成功: {success_dates}日")
    print(f"失敗: {failed_dates}日")
    print(f"処理時間: {elapsed/60:.1f}分")
    print(f"完了時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    return 0 if failed_dates == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
