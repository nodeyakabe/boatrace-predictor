"""
バックテストデータ診断スクリプト

DBの状態を確認して、バックテストが実行可能か診断する
"""

import sys
import os
import sqlite3
from datetime import datetime, timedelta

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, PROJECT_ROOT)


def diagnose_database(db_path="data/boatrace.db"):
    """データベースを診断"""
    print("=" * 70)
    print("データベース診断")
    print("=" * 70)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 1. レースデータの期間確認
    print("\n[1] レースデータの期間")
    cursor.execute("SELECT MIN(race_date), MAX(race_date), COUNT(*) FROM races")
    min_date, max_date, race_count = cursor.fetchone()
    print(f"  最古のレース: {min_date}")
    print(f"  最新のレース: {max_date}")
    print(f"  総レース数: {race_count}")

    # 2. 結果データの期間確認
    print("\n[2] 結果データの期間")
    cursor.execute("""
        SELECT MIN(r.race_date), MAX(r.race_date), COUNT(DISTINCT res.race_id)
        FROM results res
        JOIN races r ON res.race_id = r.id
    """)
    min_result_date, max_result_date, result_count = cursor.fetchone()
    print(f"  最古の結果: {min_result_date}")
    print(f"  最新の結果: {max_result_date}")
    print(f"  結果があるレース数: {result_count}")

    # 3. 完全な結果データ（6艇）の確認
    print("\n[3] 完全な結果データ（6艇）")
    cursor.execute("""
        SELECT COUNT(*) FROM (
            SELECT race_id, COUNT(*) as cnt
            FROM results
            GROUP BY race_id
            HAVING cnt = 6
        )
    """)
    complete_results = cursor.fetchone()[0]
    print(f"  6艇の結果があるレース数: {complete_results}")

    # 4. 直前情報データの確認
    print("\n[4] 直前情報データ")
    try:
        cursor.execute("""
            SELECT COUNT(DISTINCT race_id) FROM beforeinfo
        """)
        beforeinfo_count = cursor.fetchone()[0]
        print(f"  直前情報があるレース数: {beforeinfo_count}")
    except sqlite3.OperationalError:
        print(f"  [警告] beforeinfoテーブルが存在しません")

    # 5. サンプル期間でのデータ確認
    print("\n[5] 直近1週間のデータ")
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')

    cursor.execute("""
        SELECT COUNT(*) FROM races
        WHERE race_date BETWEEN ? AND ?
    """, (start_date, end_date))
    recent_races = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(DISTINCT res.race_id)
        FROM results res
        JOIN races r ON res.race_id = r.id
        WHERE r.race_date BETWEEN ? AND ?
    """, (start_date, end_date))
    recent_results = cursor.fetchone()[0]

    print(f"  期間: {start_date} ~ {end_date}")
    print(f"  レース数: {recent_races}")
    print(f"  結果があるレース数: {recent_results}")

    # 6. 推奨期間の提案
    print("\n[6] 推奨テスト期間")
    if max_result_date:
        # 結果データがある最新日から遡って1ヶ月
        try:
            latest = datetime.strptime(max_result_date, '%Y-%m-%d')
            recommended_end = latest.strftime('%Y-%m-%d')
            recommended_start = (latest - timedelta(days=30)).strftime('%Y-%m-%d')

            cursor.execute("""
                SELECT COUNT(DISTINCT r.id)
                FROM races r
                JOIN results res ON r.id = res.race_id
                WHERE r.race_date BETWEEN ? AND ?
                GROUP BY res.race_id
                HAVING COUNT(res.race_id) = 6
            """, (recommended_start, recommended_end))

            testable_count = len(cursor.fetchall())

            print(f"  推奨期間: {recommended_start} ~ {recommended_end}")
            print(f"  テスト可能なレース数（推定）: {testable_count}")

            if testable_count > 0:
                print(f"\n  [推奨] 以下のコマンドでA/Bテストを実行してください:")
                print(f"  ```python")
                print(f"  from src.evaluation.ab_test_dynamic_integration import ABTestDynamicIntegration")
                print(f"  ab_test = ABTestDynamicIntegration()")
                print(f"  ab_test.run_ab_test(")
                print(f"      start_date='{recommended_start}',")
                print(f"      end_date='{recommended_end}',")
                print(f"      output_dir='temp/ab_test/recommended'")
                print(f"  )")
                print(f"  ```")
            else:
                print(f"\n  [警告] 推奨期間でもテスト可能なレースが見つかりません")

        except ValueError:
            print("  日付の解析に失敗しました")

    # 7. データベーステーブル確認
    print("\n[7] データベーステーブル一覧")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    print(f"  テーブル数: {len(tables)}")
    for table in ['races', 'results', 'beforeinfo', 'entries']:
        status = "✓" if table in tables else "✗"
        print(f"    {status} {table}")

    conn.close()

    print("\n" + "=" * 70)
    print("診断完了")
    print("=" * 70)


if __name__ == "__main__":
    diagnose_database()
