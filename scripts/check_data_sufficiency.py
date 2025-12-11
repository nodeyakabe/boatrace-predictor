"""
データ充足状況確認スクリプト

2024年・2025年の2年間のデータ充足状況を詳細に調査:
- レース基本情報
- 選手詳細情報
- 直前情報（展示タイム、ST、進入コースなど）
- オッズ情報
- 結果情報
- 払戻情報
"""
import os
import sys
from datetime import datetime, date
import sqlite3
from collections import defaultdict

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)


def check_data_sufficiency():
    """データ充足状況を確認"""
    db_path = os.path.join(PROJECT_ROOT, 'data/boatrace.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("=" * 100)
    print("データ充足状況確認レポート")
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
        print(f"\n[1] レース基本情報（racesテーブル）")
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

        # 会場別レース数（TOP10）
        cursor.execute("""
            SELECT
                venue_code,
                COUNT(*) as race_count
            FROM races
            WHERE race_date >= ? AND race_date <= ?
            GROUP BY venue_code
            ORDER BY race_count DESC
            LIMIT 10
        """, (start_date, end_date))
        venue_races = cursor.fetchall()
        print(f"\n  会場別レース数（TOP10）:")
        for venue, count in venue_races:
            print(f"    {venue}: {count:,}レース")

        # 2. 選手詳細情報（race_details）
        print(f"\n[2] 選手詳細情報（race_detailsテーブル）")
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

        # 級別データの充足率
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN racer_rank IS NOT NULL THEN 1 ELSE 0 END) as with_rank
            FROM race_details rd
            JOIN races r ON rd.race_id = r.id
            WHERE r.race_date >= ? AND r.race_date <= ?
        """, (start_date, end_date))
        total, with_rank = cursor.fetchone()
        rank_coverage = (with_rank / total * 100) if total > 0 else 0
        print(f"  級別データ: {with_rank:,}件 / {total:,}件 ({rank_coverage:.1f}%)")

        # 勝率データの充足率
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN win_rate IS NOT NULL THEN 1 ELSE 0 END) as with_winrate
            FROM race_details rd
            JOIN races r ON rd.race_id = r.id
            WHERE r.race_date >= ? AND r.race_date <= ?
        """, (start_date, end_date))
        total, with_winrate = cursor.fetchone()
        winrate_coverage = (with_winrate / total * 100) if total > 0 else 0
        print(f"  勝率データ: {with_winrate:,}件 / {total:,}件 ({winrate_coverage:.1f}%)")

        # 3. 直前情報
        print(f"\n[3] 直前情報（race_details）")
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

        # ST
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN start_timing IS NOT NULL THEN 1 ELSE 0 END) as with_data
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
                SUM(CASE WHEN tilt IS NOT NULL THEN 1 ELSE 0 END) as with_data
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

        # 4. オッズ情報
        print(f"\n[4] オッズ情報（oddsテーブル）")
        print("-" * 100)

        # 三連単オッズ
        cursor.execute("""
            SELECT COUNT(DISTINCT race_id) as races_with_odds
            FROM odds o
            JOIN races r ON o.race_id = r.id
            WHERE r.race_date >= ? AND r.race_date <= ?
        """, (start_date, end_date))
        races_with_odds = cursor.fetchone()[0]
        odds_coverage = (races_with_odds / total_races * 100) if total_races > 0 else 0
        print(f"  オッズあるレース: {races_with_odds:,}レース / {total_races:,}レース ({odds_coverage:.1f}%)")

        # 三連単オッズの総件数
        cursor.execute("""
            SELECT COUNT(*) as total_odds
            FROM odds o
            JOIN races r ON o.race_id = r.id
            WHERE r.race_date >= ? AND r.race_date <= ?
        """, (start_date, end_date))
        total_odds = cursor.fetchone()[0]
        expected_odds = races_with_odds * 120  # 6艇のうち3艇を選ぶ順列 = 6P3 = 120
        odds_completeness = (total_odds / expected_odds * 100) if expected_odds > 0 else 0
        print(f"  三連単オッズ件数: {total_odds:,}件 / 期待値: {expected_odds:,}件 ({odds_completeness:.1f}%)")

        # 5. 結果情報
        print(f"\n[5] 結果情報（race_detailsテーブル）")
        print("-" * 100)

        cursor.execute("""
            SELECT
                COUNT(DISTINCT rd.race_id) as races_with_results
            FROM race_details rd
            JOIN races r ON rd.race_id = r.id
            WHERE r.race_date >= ? AND r.race_date <= ?
            AND rd.finish_position IS NOT NULL
        """, (start_date, end_date))
        races_with_results = cursor.fetchone()[0]
        results_coverage = (races_with_results / total_races * 100) if total_races > 0 else 0
        print(f"  結果あるレース: {races_with_results:,}レース / {total_races:,}レース ({results_coverage:.1f}%)")

        # 6. 払戻情報
        print(f"\n[6] 払戻情報（payoutsテーブル）")
        print("-" * 100)

        # 三連単払戻
        cursor.execute("""
            SELECT COUNT(DISTINCT race_id) as races_with_payout
            FROM payouts p
            JOIN races r ON p.race_id = r.id
            WHERE r.race_date >= ? AND r.race_date <= ?
            AND p.bet_type = '3連単'
        """, (start_date, end_date))
        races_with_payout = cursor.fetchone()[0]
        payout_coverage = (races_with_payout / total_races * 100) if total_races > 0 else 0
        print(f"  三連単払戻あるレース: {races_with_payout:,}レース / {total_races:,}レース ({payout_coverage:.1f}%)")

        # 7. 気象情報
        print(f"\n[7] 気象情報（weatherテーブル）")
        print("-" * 100)

        cursor.execute("""
            SELECT COUNT(DISTINCT race_id) as races_with_weather
            FROM weather w
            JOIN races r ON w.race_id = r.id
            WHERE r.race_date >= ? AND r.race_date <= ?
        """, (start_date, end_date))
        races_with_weather = cursor.fetchone()[0]
        weather_coverage = (races_with_weather / total_races * 100) if total_races > 0 else 0
        print(f"  気象データあるレース: {races_with_weather:,}レース / {total_races:,}レース ({weather_coverage:.1f}%)")

        # 風速・風向
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN wind_speed IS NOT NULL THEN 1 ELSE 0 END) as with_speed,
                SUM(CASE WHEN wind_direction IS NOT NULL THEN 1 ELSE 0 END) as with_dir
            FROM weather w
            JOIN races r ON w.race_id = r.id
            WHERE r.race_date >= ? AND r.race_date <= ?
        """, (start_date, end_date))
        total, with_speed, with_dir = cursor.fetchone()
        wind_speed_coverage = (with_speed / total * 100) if total > 0 else 0
        wind_dir_coverage = (with_dir / total * 100) if total > 0 else 0
        print(f"  風速: {with_speed:,}件 / {total:,}件 ({wind_speed_coverage:.1f}%)")
        print(f"  風向: {with_dir:,}件 / {total:,}件 ({wind_dir_coverage:.1f}%)")

        # 8. データ充足率サマリー
        print(f"\n[8] データ充足率サマリー")
        print("-" * 100)

        summary = [
            ("レース基本情報", 100.0),
            ("選手詳細情報", coverage),
            ("級別データ", rank_coverage),
            ("勝率データ", winrate_coverage),
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
        print(f"  {'-' * 40}")
        for item, rate in summary:
            status = "OK" if rate >= 95 else "WARN" if rate >= 80 else "CRITICAL"
            status_mark = "[OK]" if rate >= 95 else "[WARN]" if rate >= 80 else "[!!]"
            print(f"  {item:<20} {rate:>6.1f}%   {status_mark}")

        # 9. 不足データの詳細分析（80%未満のもの）
        print(f"\n[9] 不足データの詳細分析（充足率80%未満の項目）")
        print("-" * 100)

        low_coverage_items = [(item, rate) for item, rate in summary if rate < 80]

        if low_coverage_items:
            for item, rate in low_coverage_items:
                print(f"\n  ** {item}（充足率: {rate:.1f}%）**")

                if item == "展示タイム":
                    # 月別の展示タイム充足率
                    cursor.execute("""
                        SELECT
                            strftime('%m', r.race_date) as month,
                            COUNT(*) as total,
                            SUM(CASE WHEN exhibition_time IS NOT NULL THEN 1 ELSE 0 END) as with_data
                        FROM race_details rd
                        JOIN races r ON rd.race_id = r.id
                        WHERE r.race_date >= ? AND r.race_date <= ?
                        GROUP BY month
                        ORDER BY month
                    """, (start_date, end_date))
                    monthly_data = cursor.fetchall()
                    print(f"    月別充足率:")
                    for month, total, with_data in monthly_data:
                        month_coverage = (with_data / total * 100) if total > 0 else 0
                        print(f"      {month}月: {month_coverage:6.1f}% ({with_data:,}/{total:,})")

                elif item == "ST":
                    # 月別のST充足率
                    cursor.execute("""
                        SELECT
                            strftime('%m', r.race_date) as month,
                            COUNT(*) as total,
                            SUM(CASE WHEN start_timing IS NOT NULL THEN 1 ELSE 0 END) as with_data
                        FROM race_details rd
                        JOIN races r ON rd.race_id = r.id
                        WHERE r.race_date >= ? AND r.race_date <= ?
                        GROUP BY month
                        ORDER BY month
                    """, (start_date, end_date))
                    monthly_data = cursor.fetchall()
                    print(f"    月別充足率:")
                    for month, total, with_data in monthly_data:
                        month_coverage = (with_data / total * 100) if total > 0 else 0
                        print(f"      {month}月: {month_coverage:6.1f}% ({with_data:,}/{total:,})")

        else:
            print(f"  すべてのデータ項目が80%以上の充足率を維持しています。")

    conn.close()

    print(f"\n{'=' * 100}")
    print("レポート終了")
    print(f"{'=' * 100}")


if __name__ == '__main__':
    check_data_sufficiency()
