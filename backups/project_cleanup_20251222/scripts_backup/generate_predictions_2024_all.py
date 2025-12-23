#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
2024年の全予測データを生成するスクリプト
338日間、12,300レース分の予測データを生成

【重要】
バックテスト用にはadvance予測（直前情報なし）を使用する必要がある。
直前情報（展示タイム、ST等）は当日にならないと分からないため、
過去データでの検証には使用できない。

- advance: 事前予測（直前情報なし）→ バックテストに使用
- before: 直前予測（直前情報あり）→ 実運用・リアルタイム予測に使用
"""
import sys
import os
import io
import sqlite3
import argparse
from datetime import datetime, timedelta
import subprocess

# Windows環境でのstdout/stderrエンコーディングをUTF-8に設定
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH

def get_2024_dates():
    """2024年のレースがある日付リストを取得"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT DISTINCT race_date
        FROM races
        WHERE race_date LIKE '2024%'
        ORDER BY race_date
    ''')

    dates = [row[0] for row in cursor.fetchall()]
    conn.close()
    return dates

def main():
    parser = argparse.ArgumentParser(description='2024年 全予測データ生成')
    parser.add_argument('--type', type=str, default='advance', choices=['advance', 'before'],
                        help='予測タイプ: advance=事前予測（直前情報なし）, before=直前予測（直前情報あり）。デフォルト: advance')
    args = parser.parse_args()

    prediction_type = args.type

    print("=" * 70)
    print("2024年 全予測データ生成")
    print("=" * 70)
    print(f"予測タイプ: {prediction_type}")
    if prediction_type == 'advance':
        print("  → 直前情報を使用しない（バックテスト用）")
    else:
        print("  → 直前情報を使用する（実運用用）")

    dates = get_2024_dates()
    print(f"対象日数: {len(dates)}日")
    print(f"期間: {dates[0]} 〜 {dates[-1]}")
    print()

    total_success = 0
    total_failed = 0
    total_races = 0

    start_time = datetime.now()

    for i, date in enumerate(dates, 1):
        print(f"\n[{i}/{len(dates)}] {date} を処理中...")

        # fast_prediction_generator.pyを呼び出し（--typeを明示的に指定）
        cmd = [
            sys.executable,
            os.path.join(PROJECT_ROOT, 'scripts', 'fast_prediction_generator.py'),
            '--date', date,
            '--type', prediction_type
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

            # 結果を解析
            output = result.stdout
            if '生成成功:' in output:
                for line in output.split('\n'):
                    if '生成成功:' in line:
                        success = int(line.split('生成成功:')[1].split('件')[0].strip())
                        total_success += success
                    elif '生成失敗:' in line:
                        failed = int(line.split('生成失敗:')[1].split('件')[0].strip())
                        total_failed += failed
                    elif '総レース数:' in line:
                        races = int(line.split('総レース数:')[1].split('件')[0].strip())
                        total_races += races

                print(f"  成功: {success}件, 失敗: {failed}件")

        except subprocess.TimeoutExpired:
            print(f"  [!] タイムアウト")
            total_failed += 1
        except Exception as e:
            print(f"  [!] エラー: {e}")
            total_failed += 1

        # 進捗表示
        elapsed = (datetime.now() - start_time).total_seconds()
        avg_time = elapsed / i
        remaining = avg_time * (len(dates) - i)
        print(f"  進捗: {i}/{len(dates)} ({i/len(dates)*100:.1f}%), 残り推定時間: {remaining/60:.1f}分")

    print("\n" + "=" * 70)
    print("完了")
    print("=" * 70)
    print(f"総処理時間: {(datetime.now() - start_time).total_seconds()/60:.1f}分")
    print(f"総レース数: {total_races}レース")
    print(f"生成成功: {total_success}レース")
    print(f"生成失敗: {total_failed}レース")
    print(f"成功率: {total_success/total_races*100 if total_races > 0 else 0:.1f}%")
    print("=" * 70)

if __name__ == '__main__':
    main()
