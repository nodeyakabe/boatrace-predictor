"""
夜間自動データ収集スクリプト

2025年データの不足分を順次自動収集します。
- レース詳細（ST time & actual_course）
- 払戻金
- 直前情報

実行方法:
  python scripts/night_auto_collection.py

実行すると、各タスクを順次バックグラウンドで実行し、
すべて完了するまで待機します。
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import os
import subprocess
import time
import sqlite3
from datetime import datetime

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
os.chdir(PROJECT_ROOT)

def check_missing_data():
    """不足データを確認"""
    conn = sqlite3.connect("data/boatrace.db")
    cursor = conn.cursor()

    # レース詳細
    cursor.execute("""
        SELECT COUNT(DISTINCT r.id)
        FROM races r
        WHERE r.race_date >= '2025-01-01' AND r.race_date < '2026-01-01'
          AND EXISTS (
              SELECT 1 FROM race_details rd
              WHERE rd.race_id = r.id
              AND (rd.st_time IS NULL OR rd.actual_course IS NULL)
          )
    """)
    details_missing = cursor.fetchone()[0]

    # 払戻金
    cursor.execute("""
        SELECT COUNT(*)
        FROM races r
        WHERE r.race_date >= '2025-01-01' AND r.race_date < '2026-01-01'
          AND NOT EXISTS (
              SELECT 1 FROM payouts p WHERE p.race_id = r.id
          )
    """)
    payout_missing = cursor.fetchone()[0]

    # 直前情報（展示タイムで確認）
    cursor.execute("""
        SELECT COUNT(DISTINCT r.id)
        FROM races r
        WHERE r.race_date >= '2025-01-01' AND r.race_date < '2026-01-01'
          AND NOT EXISTS (
              SELECT 1 FROM race_details rd
              WHERE rd.race_id = r.id
              AND rd.exhibition_time IS NOT NULL
          )
    """)
    beforeinfo_missing = cursor.fetchone()[0]

    conn.close()

    return {
        'details': details_missing,
        'payout': payout_missing,
        'beforeinfo': beforeinfo_missing
    }

def run_command(cmd, description):
    """コマンドを実行して完了を待つ"""
    print("=" * 80)
    print(f"【{description}】")
    print(f"コマンド: {cmd}")
    print(f"開始時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    print()

    start_time = time.time()

    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=PROJECT_ROOT,
            capture_output=False,
            text=True,
            encoding='utf-8'
        )

        elapsed = time.time() - start_time

        print()
        print("-" * 80)
        if result.returncode == 0:
            print(f"✅ {description} 完了")
        else:
            print(f"❌ {description} エラー終了 (コード: {result.returncode})")
        print(f"処理時間: {elapsed/60:.1f}分")
        print("-" * 80)
        print()

        return result.returncode == 0

    except Exception as e:
        print(f"❌ エラー: {e}")
        return False

def main():
    print("=" * 80)
    print("夜間自動データ収集")
    print(f"開始時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    print()

    overall_start = time.time()

    # 1. 現在の不足データを確認
    print("【データ不足状況の確認】")
    missing = check_missing_data()
    print(f"レース詳細: {missing['details']:,}件")
    print(f"払戻金: {missing['payout']:,}件")
    print(f"直前情報: {missing['beforeinfo']:,}件")
    print()

    tasks_completed = []
    tasks_failed = []

    # 2. レース詳細補完（最優先）
    if missing['details'] > 0:
        print(f"タスク1: レース詳細補完 ({missing['details']:,}件)")
        success = run_command(
            "python 補完_レース詳細データ_軽量版.py --start-date 2025-01-01 --end-date 2025-12-31",
            "レース詳細補完"
        )
        if success:
            tasks_completed.append("レース詳細")
        else:
            tasks_failed.append("レース詳細")

        # 進捗確認
        missing_after = check_missing_data()
        print(f"残り: {missing_after['details']:,}件")
        print()
    else:
        print("✅ レース詳細は完了済み")
        print()

    # 3. 払戻金・直前情報補完（bulk_missing_data_fetch_12h.pyで一括処理）
    if missing['payout'] > 0 or missing['beforeinfo'] > 0:
        print(f"タスク2: 払戻金・直前情報補完")
        print(f"  払戻金: {missing['payout']:,}件")
        print(f"  直前情報: {missing['beforeinfo']:,}件")

        success = run_command(
            "python scripts/bulk_missing_data_fetch_12h.py --start-date 2025-01-01 --end-date 2025-12-31",
            "払戻金・直前情報補完"
        )
        if success:
            tasks_completed.append("払戻金・直前情報")
        else:
            tasks_failed.append("払戻金・直前情報")

        # 進捗確認
        missing_after = check_missing_data()
        print(f"残り払戻金: {missing_after['payout']:,}件")
        print(f"残り直前情報: {missing_after['beforeinfo']:,}件")
        print()
    else:
        print("✅ 払戻金・直前情報は完了済み")
        print()

    # 4. 最終確認
    print("=" * 80)
    print("【最終確認】")
    print("=" * 80)
    final_missing = check_missing_data()

    print("2025年データ不足状況:")
    print(f"  レース詳細: {final_missing['details']:,}件")
    print(f"  払戻金: {final_missing['payout']:,}件")
    print(f"  直前情報: {final_missing['beforeinfo']:,}件")
    print()

    total_elapsed = time.time() - overall_start

    print("=" * 80)
    print("【実行サマリー】")
    print("=" * 80)
    print(f"完了タスク: {', '.join(tasks_completed) if tasks_completed else 'なし'}")
    if tasks_failed:
        print(f"失敗タスク: {', '.join(tasks_failed)}")
    print(f"総処理時間: {total_elapsed/60:.1f}分 ({total_elapsed/3600:.2f}時間)")
    print(f"終了時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    if final_missing['details'] == 0 and final_missing['payout'] == 0 and final_missing['beforeinfo'] == 0:
        print()
        print("🎉 2025年データの収集が完了しました！")
    elif sum(final_missing.values()) < sum(missing.values()):
        print()
        print(f"✅ データ収集が進捗しました（残り: {sum(final_missing.values()):,}件）")

    print()

if __name__ == "__main__":
    main()
