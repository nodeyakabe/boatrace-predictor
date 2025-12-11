"""
データ充足状況確認スクリプト（簡易版）

2024年・2025年の2年間のデータ充足状況を調査
"""
import os
import sys
from datetime import datetime
import sqlite3

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)


def check_data_sufficiency():
    """データ充足状況を確認"""
    db_path = os.path.join(PROJECT_ROOT, 'data/boatrace.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("=" * 100)
    print("データ充足状況確認レポート（2024-2025年）")
    print(f"実行時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 100)

    # 対象期間: 2024年・2025年
    years = [2024, 2025]

    for year in years:
        print(f"\n{'=' * 100}")
        print(f"{year}年のデータ充足状況")
        print(f"{'=' * 100}")

        start_date = f"{year}-01-01"
        end_date = f"{year}-12-31"

        # 1. レース基本情報
        print(f"\n[1] レース基本情報")
        print("-" * 100)

        cursor.execute("""
            SELECT COUNT(*) as total_races
            FROM races
            WHERE race_date >= ? AND race_date <= ?
        """, (start_date, end_date))
        total_races = cursor.fetchone()[0]
        print(f"  総レース数: {total_races:,}レース")

        # 月別レース数
        cursor.execute("""
            SELECT
                strftime('%m', race_date) as month,
                COUNT(*) as race_count
            FROM races
            WHERE race_date >= ? AND race_date <= ?
            GROUP BY month
            ORDER BY month
        """, (start_date, end_date))
        monthly_races = cursor.fetchall()
        print(f"\n  月別レース数:")
        for month, count in monthly_races:
            print(f"    {month}月: {count:,}レース")

        # 2. 選手エントリー数
        print(f"\n[2] 選手エントリー数（race_detailsテーブル）")
        print("-" * 100)

        cursor.execute("""
            SELECT COUNT(*) as total_entries
            FROM race_details rd
            JOIN races r ON rd.race_id = r.id
            WHERE r.race_date >= ? AND r.race_date <= ?
        """, (start_date, end_date))
        total_entries = cursor.fetchone()[0]
        expected_entries = total_races * 6
        coverage = (total_entries / expected_entries * 100) if expected_entries > 0 else 0
        print(f"  総エントリー数: {total_entries:,}件 / 期待値: {expected_entries:,}件 ({coverage:.1f}%)")

        # 3. 直前情報の充足率
        print(f"\n[3] 直前情報の充足率")
        print("-" * 100)

        # 展示タイム
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN exhibition_time IS NOT NULL THEN 1 ELSE 0 END) as with_data
            FROM race_details rd
            JOIN races r ON rd.race_id = r.id
            WHERE r.race_date >= ? AND r.race_date <= ?
        """, (start_date, end_date))
        total, with_data = cursor.fetchone()
        exh_coverage = (with_data / total * 100) if total > 0 else 0
        print(f"  展示タイム: {with_data:,}件 / {total:,}件 ({exh_coverage:.1f}%)")

        # ST（start_timing）
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN st_time IS NOT NULL THEN 1 ELSE 0 END) as with_data
            FROM race_details rd
            JOIN races r ON rd.race_id = r.id
            WHERE r.race_date >= ? AND r.race_date <= ?
        """, (start_date, end_date))
        total, with_data = cursor.fetchone()
        st_coverage = (with_data / total * 100) if total > 0 else 0
        print(f"  ST（スタートタイミング）: {with_data:,}件 / {total:,}件 ({st_coverage:.1f}%)")

        # 展示進入コース
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN exhibition_course IS NOT NULL THEN 1 ELSE 0 END) as with_data
            FROM race_details rd
            JOIN races r ON rd.race_id = r.id
            WHERE r.race_date >= ? AND r.race_date <= ?
        """, (start_date, end_date))
        total, with_data = cursor.fetchone()
        exh_course_coverage = (with_data / total * 100) if total > 0 else 0
        print(f"  展示進入コース: {with_data:,}件 / {total:,}件 ({exh_course_coverage:.1f}%)")

        # チルト
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN tilt_angle IS NOT NULL THEN 1 ELSE 0 END) as with_data
            FROM race_details rd
            JOIN races r ON rd.race_id = r.id
            WHERE r.race_date >= ? AND r.race_date <= ?
        """, (start_date, end_date))
        total, with_data = cursor.fetchone()
        tilt_coverage = (with_data / total * 100) if total > 0 else 0
        print(f"  チルト: {with_data:,}件 / {total:,}件 ({tilt_coverage:.1f}%)")

        # 調整重量
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN adjusted_weight IS NOT NULL THEN 1 ELSE 0 END) as with_data
            FROM race_details rd
            JOIN races r ON rd.race_id = r.id
            WHERE r.race_date >= ? AND r.race_date <= ?
        """, (start_date, end_date))
        total, with_data = cursor.fetchone()
        weight_coverage = (with_data / total * 100) if total > 0 else 0
        print(f"  調整重量: {with_data:,}件 / {total:,}件 ({weight_coverage:.1f}%)")

        # 4. オッズ情報（trifecta_odds）
        print(f"\n[4] オッズ情報（三連単）")
        print("-" * 100)

        cursor.execute("""
            SELECT COUNT(DISTINCT o.race_id) as races_with_odds
            FROM trifecta_odds o
            JOIN races r ON o.race_id = r.id
            WHERE r.race_date >= ? AND r.race_date <= ?
        """, (start_date, end_date))
        races_with_odds = cursor.fetchone()[0]
        odds_coverage = (races_with_odds / total_races * 100) if total_races > 0 else 0
        print(f"  三連単オッズあるレース: {races_with_odds:,}レース / {total_races:,}レース ({odds_coverage:.1f}%)")

        # オッズの総件数
        cursor.execute("""
            SELECT COUNT(*) as total_odds
            FROM trifecta_odds o
            JOIN races r ON o.race_id = r.id
            WHERE r.race_date >= ? AND r.race_date <= ?
        """, (start_date, end_date))
        total_odds = cursor.fetchone()[0]
        expected_odds = races_with_odds * 120  # 6P3 = 120通り
        if expected_odds > 0:
            odds_completeness = (total_odds / expected_odds * 100)
            print(f"  三連単オッズ件数: {total_odds:,}件 / 期待値: {expected_odds:,}件 ({odds_completeness:.1f}%)")
        else:
            print(f"  三連単オッズ件数: {total_odds:,}件")

        # 5. 結果情報（actual_courseを着順として使用）
        print(f"\n[5] 結果情報")
        print("-" * 100)

        cursor.execute("""
            SELECT
                COUNT(DISTINCT rd.race_id) as races_with_results
            FROM race_details rd
            JOIN races r ON rd.race_id = r.id
            WHERE r.race_date >= ? AND r.race_date <= ?
            AND rd.actual_course IS NOT NULL
        """, (start_date, end_date))
        races_with_results = cursor.fetchone()[0]
        results_coverage = (races_with_results / total_races * 100) if total_races > 0 else 0
        print(f"  結果あるレース: {races_with_results:,}レース / {total_races:,}レース ({results_coverage:.1f}%)")

        # 6. 払戻情報（payouts）
        print(f"\n[6] 払戻情報")
        print("-" * 100)

        cursor.execute("""
            SELECT COUNT(DISTINCT p.race_id) as races_with_payout
            FROM payouts p
            JOIN races r ON p.race_id = r.id
            WHERE r.race_date >= ? AND r.race_date <= ?
            AND p.bet_type = 'trifecta'
        """, (start_date, end_date))
        races_with_payout = cursor.fetchone()[0]
        payout_coverage = (races_with_payout / total_races * 100) if total_races > 0 else 0
        print(f"  三連単払戻あるレース: {races_with_payout:,}レース / {total_races:,}レース ({payout_coverage:.1f}%)")

        # 7. 気象情報
        print(f"\n[7] 気象情報")
        print("-" * 100)

        cursor.execute("""
            SELECT COUNT(*) as total_weather
            FROM weather
            WHERE weather_date >= ? AND weather_date <= ?
        """, (start_date, end_date))
        total_weather = cursor.fetchone()[0]
        print(f"  気象データ件数: {total_weather:,}件")

        # 風速・風向
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN wind_speed IS NOT NULL THEN 1 ELSE 0 END) as with_speed,
                SUM(CASE WHEN wind_direction IS NOT NULL THEN 1 ELSE 0 END) as with_dir
            FROM weather
            WHERE weather_date >= ? AND weather_date <= ?
        """, (start_date, end_date))
        total, with_speed, with_dir = cursor.fetchone()
        if total > 0:
            wind_speed_coverage = (with_speed / total * 100)
            wind_dir_coverage = (with_dir / total * 100)
            print(f"  風速: {with_speed:,}件 / {total:,}件 ({wind_speed_coverage:.1f}%)")
            print(f"  風向: {with_dir:,}件 / {total:,}件 ({wind_dir_coverage:.1f}%)")
        else:
            wind_speed_coverage = 0.0
            wind_dir_coverage = 0.0

        weather_coverage = wind_speed_coverage  # サマリー用

        # 8. サマリー
        print(f"\n[8] データ充足率サマリー")
        print("-" * 100)

        summary = [
            ("レース基本情報", 100.0),
            ("選手エントリー", coverage),
            ("展示タイム", exh_coverage),
            ("ST", st_coverage),
            ("展示進入コース", exh_course_coverage),
            ("チルト", tilt_coverage),
            ("調整重量", weight_coverage),
            ("オッズ情報", odds_coverage),
            ("結果情報", results_coverage),
            ("払戻情報", payout_coverage),
            ("気象情報", weather_coverage),
        ]

        print(f"  {'項目':<20} {'充足率':<10} {'状態'}")
        print(f"  {'-' * 42}")
        for item, rate in summary:
            if rate >= 95:
                status = "[OK]  "
            elif rate >= 80:
                status = "[WARN]"
            else:
                status = "[!!]  "
            print(f"  {item:<20} {rate:>6.1f}%    {status}")

        # 9. 不足データの詳細（80%未満）
        low_coverage_items = [(item, rate) for item, rate in summary if rate < 80]

        if low_coverage_items:
            print(f"\n[9] 不足データの詳細（充足率80%未満）")
            print("-" * 100)
            for item, rate in low_coverage_items:
                print(f"  {item}: {rate:.1f}%")

    conn.close()

    print(f"\n{'=' * 100}")
    print("レポート終了")
    print(f"{'=' * 100}\n")


if __name__ == '__main__':
    check_data_sufficiency()
