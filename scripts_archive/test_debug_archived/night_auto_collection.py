"""
2025年データ完全収集スクリプト

2025年データの不足分を順次自動収集します。
- レース詳細（ST time & actual_course）
- 払戻金
- 決まり手
- 結果データ

実行方法:
  python scripts/night_auto_collection.py

実行すると、各タスクを順次実行し、
すべて完了するまで待機します。

更新履歴:
  2025-12-06: スクリプト名を現在の構成に合わせて更新
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

    # レース詳細（ST time or actual_course が不足）
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
          AND r.race_date < date('now')
          AND NOT EXISTS (
              SELECT 1 FROM payouts p WHERE p.race_id = r.id
          )
    """)
    payout_missing = cursor.fetchone()[0]

    # 結果データ（過去レースのみ）
    cursor.execute("""
        SELECT COUNT(*)
        FROM races r
        WHERE r.race_date >= '2025-01-01' AND r.race_date < '2026-01-01'
          AND r.race_date < date('now')
          AND NOT EXISTS (
              SELECT 1 FROM results res WHERE res.race_id = r.id
          )
    """)
    results_missing = cursor.fetchone()[0]

    # 決まり手（結果があるが決まり手がないレース）
    cursor.execute("""
        SELECT COUNT(*)
        FROM races r
        WHERE r.race_date >= '2025-01-01' AND r.race_date < '2026-01-01'
          AND EXISTS (
              SELECT 1 FROM results res WHERE res.race_id = r.id AND res.rank = 1
          )
          AND EXISTS (
              SELECT 1 FROM results res WHERE res.race_id = r.id AND res.rank = 1 AND (res.kimarite IS NULL OR res.kimarite = '')
          )
    """)
    kimarite_missing = cursor.fetchone()[0]

    conn.close()

    return {
        'details': details_missing,
        'payout': payout_missing,
        'results': results_missing,
        'kimarite': kimarite_missing
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
    print("2025年データ完全収集")
    print(f"開始時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    print()

    overall_start = time.time()

    # 1. 現在の不足データを確認
    print("【データ不足状況の確認】")
    missing = check_missing_data()
    print(f"レース詳細(ST/コース): {missing['details']:,}件")
    print(f"払戻金: {missing['payout']:,}件")
    print(f"結果データ: {missing['results']:,}件")
    print(f"決まり手: {missing['kimarite']:,}件")
    print()

    tasks_completed = []
    tasks_failed = []

    # 2. レース詳細補完（最優先 - ST time & actual_course）
    if missing['details'] > 0:
        print(f"タスク1: レース詳細補完 ({missing['details']:,}件)")
        success = run_command(
            'python "補完_レース詳細データ_改善版v4.py" --start-date 2025-01-01 --end-date 2025-12-05',
            "レース詳細補完（ST/コース）"
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
        print("[OK] レース詳細は完了済み")
        print()

    # 3. 払戻金補完
    if missing['payout'] > 0:
        print(f"タスク2: 払戻金補完 ({missing['payout']:,}件)")
        success = run_command(
            'python "補完_払戻金データ.py" --start-date 2025-01-01 --end-date 2025-12-05',
            "払戻金補完"
        )
        if success:
            tasks_completed.append("払戻金")
        else:
            tasks_failed.append("払戻金")

        # 進捗確認
        missing_after = check_missing_data()
        print(f"残り: {missing_after['payout']:,}件")
        print()
    else:
        print("[OK] 払戻金は完了済み")
        print()

    # 4. 決まり手補完
    if missing['kimarite'] > 0:
        print(f"タスク3: 決まり手補完 ({missing['kimarite']:,}件)")
        success = run_command(
            'python "補完_決まり手データ_改善版.py" --start-date 2025-01-01 --end-date 2025-12-05',
            "決まり手補完"
        )
        if success:
            tasks_completed.append("決まり手")
        else:
            tasks_failed.append("決まり手")

        # 進捗確認
        missing_after = check_missing_data()
        print(f"残り: {missing_after['kimarite']:,}件")
        print()
    else:
        print("[OK] 決まり手は完了済み")
        print()

    # 5. 結果データ補完（並列版で高速処理）
    if missing['results'] > 0:
        print(f"タスク4: 結果データ補完 ({missing['results']:,}件)")
        success = run_command(
            'python scripts/bulk_missing_data_fetch_parallel.py --start-date 2025-01-01 --end-date 2025-12-05',
            "結果データ補完"
        )
        if success:
            tasks_completed.append("結果データ")
        else:
            tasks_failed.append("結果データ")

        # 進捗確認
        missing_after = check_missing_data()
        print(f"残り: {missing_after['results']:,}件")
        print()
    else:
        print("[OK] 結果データは完了済み")
        print()

    # 6. 最終確認
    print("=" * 80)
    print("【最終確認】")
    print("=" * 80)
    final_missing = check_missing_data()

    print("2025年データ不足状況:")
    print(f"  レース詳細: {final_missing['details']:,}件")
    print(f"  払戻金: {final_missing['payout']:,}件")
    print(f"  結果データ: {final_missing['results']:,}件")
    print(f"  決まり手: {final_missing['kimarite']:,}件")
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

    total_missing = sum(final_missing.values())
    if total_missing == 0:
        print()
        print("[SUCCESS] 2025年データの収集が完了しました！")
    elif total_missing < sum(missing.values()):
        print()
        print(f"[PROGRESS] データ収集が進捗しました（残り: {total_missing:,}件）")

    print()

if __name__ == "__main__":
    main()
