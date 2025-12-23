#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
2020-2023年 advance予測生成完了後、自動的に直前情報収集を開始

このスクリプトは：
1. 2020-2023年のadvance予測生成の完了を監視
2. 完了したら自動的に直前情報収集をバックグラウンド開始
"""
import sys
import os
import subprocess
import time
import sqlite3
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
db_path = PROJECT_ROOT / "data" / "boatrace.db"

TARGET_RACES = 64168  # 2020-2023年の総レース数
CHECK_INTERVAL = 60  # チェック間隔（秒）


def get_advance_progress():
    """現在のadvance予測生成進捗を取得"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(DISTINCT race_id), MAX(generated_at)
        FROM race_predictions
        WHERE prediction_type = 'advance'
          AND race_id IN (SELECT id FROM races WHERE race_date >= '2020-01-01' AND race_date < '2024-01-01')
    """)

    races, latest = cursor.fetchone()
    conn.close()

    return races, latest


def start_beforeinfo_collection():
    """直前情報収集をバックグラウンドで開始"""
    script_path = PROJECT_ROOT / "scripts" / "collect_beforeinfo_2020_2023.py"

    print()
    print("=" * 80)
    print("直前情報収集を自動開始します")
    print("=" * 80)
    print()

    # 環境変数でAUTO_STARTを設定
    env = os.environ.copy()
    env['AUTO_START'] = '1'

    # バックグラウンドで実行
    if sys.platform == 'win32':
        # Windows: CREATE_NO_WINDOW フラグでバックグラウンド実行
        subprocess.Popen(
            [sys.executable, str(script_path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
    else:
        # Linux/Mac: nohup で実行
        subprocess.Popen(
            [sys.executable, str(script_path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            start_new_session=True
        )

    print("✓ 直前情報収集をバックグラウンドで開始しました")
    print(f"  スクリプト: {script_path}")
    print()


def main():
    print("=" * 80)
    print("2020-2023年 advance予測生成完了監視 → 自動的に直前情報収集開始")
    print("=" * 80)
    print(f"開始時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"対象レース数: {TARGET_RACES:,}件")
    print(f"チェック間隔: {CHECK_INTERVAL}秒")
    print()

    last_count = 0
    check_count = 0

    while True:
        check_count += 1
        current_count, latest_time = get_advance_progress()

        progress = current_count / TARGET_RACES * 100
        remaining = TARGET_RACES - current_count

        # 進捗表示
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"[{now}] チェック#{check_count}: {current_count:,}/{TARGET_RACES:,}件 ({progress:.1f}%) "
              f"残り{remaining:,}件", flush=True)

        if last_count > 0:
            increment = current_count - last_count
            if increment > 0:
                rate = increment / (CHECK_INTERVAL / 60)  # レース/分
                eta_min = remaining / rate if rate > 0 else 0
                print(f"  → 速度: {rate:.1f}レース/分, 推定残り時間: {eta_min:.0f}分")

        # 完了チェック（99%以上で完了とみなす）
        if progress >= 99.0:
            print()
            print("=" * 80)
            print("✓ 2020-2023年 advance予測生成が完了しました！")
            print("=" * 80)
            print(f"最終件数: {current_count:,}件")
            print(f"最終更新: {latest_time}")
            print()

            # 直前情報収集を自動開始
            start_beforeinfo_collection()

            print("=" * 80)
            print("監視を終了します")
            print("=" * 80)
            break

        last_count = current_count
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        print("=" * 80)
        print("監視を中断しました")
        print("=" * 80)
