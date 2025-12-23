#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
全年度のbefore予測を再生成するスクリプト
2020-2025年の6年分を生成

実行方法:
    python scripts/prediction/generate_before_all_years.py
"""
import sys
import os
import io
import sqlite3
import subprocess
from datetime import datetime

# Windows環境でのstdout/stderrエンコーディングをUTF-8に設定
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH


def get_all_race_dates(start_year=2020, end_year=2025):
    """指定年度範囲のレース日付リストを取得"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT DISTINCT race_date
        FROM races
        WHERE substr(race_date, 1, 4) >= ? AND substr(race_date, 1, 4) <= ?
        ORDER BY race_date
    ''', (str(start_year), str(end_year)))

    dates = [row[0] for row in cursor.fetchall()]
    conn.close()
    return dates


def delete_existing_before_predictions():
    """既存のbefore予測を削除"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    cursor.execute("DELETE FROM race_predictions WHERE prediction_type = 'before'")
    deleted = cursor.rowcount

    conn.commit()
    conn.close()

    return deleted


def main():
    print("=" * 70)
    print("全年度 before予測 再生成")
    print("=" * 70)
    print(f"開始時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # 既存のbefore予測を削除
    print("[1/3] 既存のbefore予測を削除中...")
    deleted = delete_existing_before_predictions()
    print(f"  削除完了: {deleted:,}件")
    print()

    # 日付リスト取得
    print("[2/3] レース日付リストを取得中...")
    dates = get_all_race_dates(2020, 2025)
    print(f"  対象日数: {len(dates)}日")
    print(f"  期間: {dates[0]} ～ {dates[-1]}")
    print()

    # 生成実行
    print("[3/3] before予測を生成中...")
    print()

    total_success = 0
    total_failed = 0
    start_time = datetime.now()

    for i, date in enumerate(dates, 1):
        elapsed = (datetime.now() - start_time).total_seconds()
        avg_time = elapsed / i if i > 0 else 0
        remaining = avg_time * (len(dates) - i)

        print(f"[{i}/{len(dates)}] {date} (残り: {int(remaining/60)}分{int(remaining%60)}秒)", end=" ", flush=True)

        # fast_prediction_generator.pyを呼び出し
        cmd = [
            sys.executable,
            os.path.join(PROJECT_ROOT, 'scripts', 'prediction', 'fast_prediction_generator.py'),
            '--date', date,
            '--type', 'before',
            '--force'  # 既存があれば上書き
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=600
            )

            if result.returncode == 0:
                # 成功数を抽出
                for line in result.stdout.split('\n'):
                    if '生成成功:' in line:
                        try:
                            success = int(line.split('生成成功:')[1].split('件')[0].strip())
                            total_success += success
                            print(f"OK ({success}件)")
                        except:
                            print("OK")
                        break
                else:
                    print("OK")
            else:
                print(f"NG")
                total_failed += 1

        except subprocess.TimeoutExpired:
            print("タイムアウト")
            total_failed += 1
        except Exception as e:
            print(f"エラー: {str(e)[:30]}")
            total_failed += 1

    # 完了
    total_time = (datetime.now() - start_time).total_seconds()

    print()
    print("=" * 70)
    print("完了")
    print("=" * 70)
    print(f"終了時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"総処理時間: {int(total_time/60)}分{int(total_time%60)}秒")
    print(f"処理日数: {len(dates)}日")
    print(f"生成成功: {total_success:,}件")
    print(f"生成失敗: {total_failed}日")
    print("=" * 70)


if __name__ == '__main__':
    main()
