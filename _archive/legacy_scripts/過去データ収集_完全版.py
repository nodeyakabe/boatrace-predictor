#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
過去データ完全収集スクリプト

依存関係を考慮した順序で過去データを収集:
1. races テーブル作成 (fetch_historical_data.py)
2. race_details 作成 (補完_race_details_INSERT対応_高速版.py)
3. オリジナル展示収集 (収集_オリジナル展示_手動実行.py)

実行方法:
  python 過去データ収集_完全版.py 2025-11-17 2025-11-17
  python 過去データ収集_完全版.py 2025-11-01 2025-11-30
"""
import sys
import subprocess
import sqlite3
from datetime import datetime

def run_command(description, cmd, check_success=True):
    """
    コマンドを実行して結果を表示

    Args:
        description: 処理の説明
        cmd: 実行するコマンド（リスト形式）
        check_success: 成功チェックをするか

    Returns:
        bool: 成功したかどうか
    """
    print("\n" + "="*80)
    print(f"【{description}】")
    print("="*80)
    print(f"実行コマンド: {' '.join(cmd)}\n")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )

        # 標準出力を表示
        if result.stdout:
            print(result.stdout)

        # エラー出力を表示
        if result.stderr:
            # 進捗バーなどの通常出力もstderrに出る場合があるので常に表示
            print(result.stderr)

        if check_success and result.returncode != 0:
            print(f"\n[ERROR] {description}が失敗しました")
            print(f"終了コード: {result.returncode}")
            return False

        print(f"\n[OK] {description}完了")
        return True

    except Exception as e:
        print(f"\n[ERROR] {description}でエラーが発生: {e}")
        return False

def check_data_status(date_str):
    """
    指定日のデータ状況を確認

    Args:
        date_str: 日付文字列 (YYYY-MM-DD)

    Returns:
        dict: データ状況
    """
    conn = sqlite3.connect('data/boatrace.db')
    cursor = conn.cursor()

    # races数
    cursor.execute("""
        SELECT COUNT(*) FROM races
        WHERE race_date BETWEEN ? AND ?
    """, (date_str, date_str))
    races_count = cursor.fetchone()[0]

    # race_details数
    cursor.execute("""
        SELECT COUNT(*) FROM race_details rd
        JOIN races r ON rd.race_id = r.id
        WHERE r.race_date BETWEEN ? AND ?
    """, (date_str, date_str))
    details_count = cursor.fetchone()[0]

    # オリジナル展示数
    cursor.execute("""
        SELECT COUNT(*) FROM race_details rd
        JOIN races r ON rd.race_id = r.id
        WHERE r.race_date BETWEEN ? AND ?
        AND (rd.chikusen_time IS NOT NULL
             OR rd.isshu_time IS NOT NULL
             OR rd.mawariashi_time IS NOT NULL)
    """, (date_str, date_str))
    tenji_count = cursor.fetchone()[0]

    conn.close()

    return {
        'races': races_count,
        'race_details': details_count,
        'original_tenji': tenji_count
    }

def main():
    if len(sys.argv) < 3:
        print("使用方法: python 過去データ収集_完全版.py [開始日] [終了日]")
        print("例: python 過去データ収集_完全版.py 2025-11-17 2025-11-17")
        sys.exit(1)

    start_date_str = sys.argv[1]
    end_date_str = sys.argv[2]

    print("="*80)
    print("過去データ完全収集")
    print("="*80)
    print(f"対象期間: {start_date_str} ～ {end_date_str}")
    print()

    # 開始前のデータ状況確認
    print("【収集前のデータ状況】")
    before_status = check_data_status(start_date_str)
    print(f"  races: {before_status['races']}レース")
    print(f"  race_details: {before_status['race_details']}件")
    print(f"  オリジナル展示: {before_status['original_tenji']}件")

    # ステップ1: races テーブル作成
    success = run_command(
        "ステップ1: レース基本データ収集",
        [sys.executable, "fetch_historical_data.py",
         "--start-date", start_date_str,
         "--end-date", end_date_str,
         "--workers", "4"]
    )

    if not success:
        print("\n[ERROR] レース基本データ収集に失敗しました")
        sys.exit(1)

    # ステップ2: race_details 作成
    success = run_command(
        "ステップ2: race_details作成（高速版）",
        [sys.executable, "補完_race_details_INSERT対応_高速版.py",
         start_date_str, end_date_str]
    )

    if not success:
        print("\n[WARNING] race_details作成に失敗しましたが、処理を続行します")

    # ステップ3: オリジナル展示収集
    # 日付範囲の場合は1日ずつ処理
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d')

    if start_date == end_date:
        # 1日だけの場合
        success = run_command(
            "ステップ3: オリジナル展示収集",
            [sys.executable, "収集_オリジナル展示_手動実行.py",
             str((start_date - datetime.now()).days)]
        )

        if not success:
            print("\n[WARNING] オリジナル展示収集に失敗しましたが、処理を続行します")
    else:
        print("\n" + "="*80)
        print("【ステップ3: オリジナル展示収集】")
        print("="*80)
        print("複数日の場合、オリジナル展示は手動で日付を指定して実行してください:")
        print("  例: python 収集_オリジナル展示_手動実行.py -1  # 昨日")
        print("      python 収集_オリジナル展示_手動実行.py 0   # 今日")

    # 収集後のデータ状況確認
    print("\n" + "="*80)
    print("【収集後のデータ状況】")
    print("="*80)
    after_status = check_data_status(start_date_str)
    print(f"  races: {after_status['races']}レース (+{after_status['races'] - before_status['races']})")
    print(f"  race_details: {after_status['race_details']}件 (+{after_status['race_details'] - before_status['race_details']})")
    print(f"  オリジナル展示: {after_status['original_tenji']}件 (+{after_status['original_tenji'] - before_status['original_tenji']})")

    print("\n" + "="*80)
    print("完全収集完了")
    print("="*80)

if __name__ == "__main__":
    main()
