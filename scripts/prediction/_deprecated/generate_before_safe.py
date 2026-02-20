#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
安全なbefore予測再生成スクリプト（UPSERT方式）

特徴:
- 全削除せずに1日ずつ処理（削除→生成→コミット）
- 途中停止しても処理済み分は保持
- 進捗ファイルで再開可能

実行方法:
    python scripts/prediction/generate_before_safe.py
    python scripts/prediction/generate_before_safe.py --resume  # 中断から再開
"""
import sys
import os
import io
import sqlite3
import subprocess
import json
from datetime import datetime

# Windows環境でのstdout/stderrエンコーディングをUTF-8に設定
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH

# 進捗ファイル
PROGRESS_FILE = os.path.join(PROJECT_ROOT, 'data', '.before_generation_progress.json')


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


def delete_before_predictions_for_date(date: str):
    """指定日のbefore予測のみを削除"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 該当日のrace_idを取得
    cursor.execute('''
        SELECT id FROM races WHERE race_date = ?
    ''', (date,))
    race_ids = [row[0] for row in cursor.fetchall()]

    if race_ids:
        placeholders = ','.join('?' * len(race_ids))
        cursor.execute(f'''
            DELETE FROM race_predictions
            WHERE race_id IN ({placeholders}) AND prediction_type = 'before'
        ''', race_ids)
        deleted = cursor.rowcount
    else:
        deleted = 0

    conn.commit()
    conn.close()
    return deleted


def save_progress(last_date: str, total_success: int, total_failed: int, processed_dates: list):
    """進捗を保存"""
    progress = {
        'last_date': last_date,
        'total_success': total_success,
        'total_failed': total_failed,
        'processed_dates': processed_dates,
        'updated_at': datetime.now().isoformat()
    }
    with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


def load_progress():
    """進捗を読み込み"""
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


def clear_progress():
    """進捗ファイルを削除"""
    if os.path.exists(PROGRESS_FILE):
        os.remove(PROGRESS_FILE)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--resume', action='store_true', help='中断から再開')
    parser.add_argument('--start-year', type=int, default=2020, help='開始年')
    parser.add_argument('--end-year', type=int, default=2025, help='終了年')
    args = parser.parse_args()

    print("=" * 70)
    print("安全なbefore予測再生成（UPSERT方式）")
    print("=" * 70)
    print(f"開始時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # 日付リスト取得
    print("[1/2] レース日付リストを取得中...")
    dates = get_all_race_dates(args.start_year, args.end_year)
    print(f"  対象日数: {len(dates)}日")
    print(f"  期間: {dates[0]} ～ {dates[-1]}")
    print()

    # 再開処理
    total_success = 0
    total_failed = 0
    processed_dates = []
    start_index = 0

    if args.resume:
        progress = load_progress()
        if progress:
            processed_dates = progress.get('processed_dates', [])
            total_success = progress.get('total_success', 0)
            total_failed = progress.get('total_failed', 0)
            last_date = progress.get('last_date', '')
            if last_date in dates:
                start_index = dates.index(last_date) + 1
            print(f"  再開: {last_date} から継続")
            print(f"  処理済み: {len(processed_dates)}日, 成功: {total_success}件")
            print()

    # 生成実行
    print("[2/2] before予測を生成中（1日ずつ安全に処理）...")
    print()

    start_time = datetime.now()

    for i, date in enumerate(dates[start_index:], start_index + 1):
        elapsed = (datetime.now() - start_time).total_seconds()
        processed = i - start_index
        avg_time = elapsed / processed if processed > 0 else 0
        remaining = avg_time * (len(dates) - i)

        print(f"[{i}/{len(dates)}] {date} (残り: {int(remaining/60)}分{int(remaining%60)}秒)", end=" ", flush=True)

        # 1. 該当日のbefore予測を削除
        deleted = delete_before_predictions_for_date(date)

        # 2. fast_prediction_generator.pyを呼び出し
        cmd = [
            sys.executable,
            os.path.join(PROJECT_ROOT, 'scripts', 'prediction', 'fast_prediction_generator.py'),
            '--date', date,
            '--type', 'before',
            '--force'
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
                success_count = 0
                for line in result.stdout.split('\n'):
                    if '生成成功:' in line:
                        try:
                            success_count = int(line.split('生成成功:')[1].split('件')[0].strip())
                            total_success += success_count
                        except:
                            pass
                        break
                print(f"OK ({success_count}件)")
            else:
                print(f"NG")
                total_failed += 1

        except subprocess.TimeoutExpired:
            print("タイムアウト")
            total_failed += 1
        except Exception as e:
            print(f"エラー: {str(e)[:30]}")
            total_failed += 1

        # 3. 進捗を保存（毎回）
        processed_dates.append(date)
        save_progress(date, total_success, total_failed, processed_dates)

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

    # 進捗ファイルを削除
    clear_progress()


if __name__ == '__main__':
    main()
