"""
展示タイム詳細分析スクリプト

展示タイムの影響を多角的・複合的に分析:
1. ランク別×コース別の勝率
2. ランク別×級別の勝率
3. ランク別×会場別の勝率
4. ランク差（1位と2位の差）の影響
5. 展示タイム絶対値の影響
6. 展示タイム×ST×進入の三重複合条件
7. 月別・グレード別の展示タイム信頼性
8. モーター成績との相関
"""
import os
import sys
import sqlite3
from datetime import datetime
from collections import defaultdict
import json

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)


def analyze_exhibition_by_course(cursor, start_date: str, end_date: str):
    """展示タイムランク × コース別の勝率分析"""
    print("\n" + "=" * 100)
    print("【1】展示タイムランク × コース別の勝率分析")
    print("=" * 100)

    cursor.execute("""
        WITH exh_ranked AS (
            SELECT
                rd.race_id,
                rd.pit_number,
                rd.actual_course,
                res.rank as finish_rank,
                ROW_NUMBER() OVER (
                    PARTITION BY rd.race_id
                    ORDER BY rd.exhibition_time ASC
                ) as exh_rank
            FROM race_details rd
            JOIN races r ON rd.race_id = r.id
            LEFT JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number
            WHERE r.race_date >= ? AND r.race_date <= ?
            AND rd.exhibition_time IS NOT NULL
            AND rd.actual_course IS NOT NULL
            AND res.rank IS NOT NULL
        )
        SELECT
            exh_rank,
            actual_course,
            COUNT(*) as total,
            SUM(CASE WHEN finish_rank = '1' THEN 1 ELSE 0 END) as first_count
        FROM exh_ranked
        GROUP BY exh_rank, actual_course
        ORDER BY exh_rank, actual_course
    """, (start_date, end_date))

    data = cursor.fetchall()

    print("\n展示ランク × コース別の1着率:")
    print("-" * 100)
    print(f"  展示ランク  1コース  2コース  3コース  4コース  5コース  6コース")
    print("-" * 100)

    # データをマトリックス形式に整形
    matrix = defaultdict(dict)
    for exh_rank, course, total, first in data:
        rate = (first / total * 100) if total > 0 else 0
        matrix[exh_rank][course] = {'total': total, 'first': first, 'rate': rate}

    for exh_rank in range(1, 7):
        row = f"  {exh_rank}位      "
        for course in range(1, 7):
            stat = matrix[exh_rank].get(course, {'rate': 0})
            row += f"{stat['rate']:>6.1f}%  "
        print(row)

    return matrix


def analyze_exhibition_by_racer_rank(cursor, start_date: str, end_date: str):
    """展示タイムランク × 級別の勝率分析"""
    print("\n" + "=" * 100)
    print("【2】展示タイムランク × 級別の勝率分析")
    print("=" * 100)

    cursor.execute("""
        WITH exh_ranked AS (
            SELECT
                rd.race_id,
                rd.pit_number,
                e.racer_rank,
                res.rank as finish_rank,
                ROW_NUMBER() OVER (
                    PARTITION BY rd.race_id
                    ORDER BY rd.exhibition_time ASC
                ) as exh_rank
            FROM race_details rd
            JOIN races r ON rd.race_id = r.id
            JOIN entries e ON rd.race_id = e.race_id AND rd.pit_number = e.pit_number
            LEFT JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number
            WHERE r.race_date >= ? AND r.race_date <= ?
            AND rd.exhibition_time IS NOT NULL
            AND e.racer_rank IS NOT NULL
            AND res.rank IS NOT NULL
        )
        SELECT
            exh_rank,
            racer_rank,
            COUNT(*) as total,
            SUM(CASE WHEN finish_rank = '1' THEN 1 ELSE 0 END) as first_count
        FROM exh_ranked
        GROUP BY exh_rank, racer_rank
        HAVING total >= 30
        ORDER BY exh_rank, racer_rank
    """, (start_date, end_date))

    data = cursor.fetchall()

    print("\n展示ランク × 級別の1着率:")
    print("-" * 100)
    print(f"  展示ランク    A1級      A2級      B1級      B2級")
    print("-" * 100)

    # データをマトリックス形式に整形
    matrix = defaultdict(dict)
    for exh_rank, racer_rank, total, first in data:
        rate = (first / total * 100) if total > 0 else 0
        matrix[exh_rank][racer_rank] = {'total': total, 'first': first, 'rate': rate}

    for exh_rank in range(1, 7):
        row = f"  {exh_rank}位      "
        for racer_rank in ['A1', 'A2', 'B1', 'B2']:
            stat = matrix[exh_rank].get(racer_rank, {'rate': 0})
            if stat['rate'] > 0:
                row += f"{stat['rate']:>6.1f}%  "
            else:
                row += "   -    "
        print(row)

    return matrix


def analyze_exhibition_gap(cursor, start_date: str, end_date: str):
    """展示タイム差（1位と2位の差）の影響分析"""
    print("\n" + "=" * 100)
    print("【3】展示タイム差（1位と2位の差）の影響分析")
    print("=" * 100)

    cursor.execute("""
        WITH exh_ranked AS (
            SELECT
                rd.race_id,
                rd.pit_number,
                rd.exhibition_time,
                res.rank as finish_rank,
                ROW_NUMBER() OVER (
                    PARTITION BY rd.race_id
                    ORDER BY rd.exhibition_time ASC
                ) as exh_rank
            FROM race_details rd
            JOIN races r ON rd.race_id = r.id
            LEFT JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number
            WHERE r.race_date >= ? AND r.race_date <= ?
            AND rd.exhibition_time IS NOT NULL
            AND res.rank IS NOT NULL
        ),
        exh_gap AS (
            SELECT
                e1.race_id,
                e1.pit_number,
                e1.finish_rank,
                e2.exhibition_time - e1.exhibition_time as time_gap
            FROM exh_ranked e1
            JOIN exh_ranked e2 ON e1.race_id = e2.race_id AND e2.exh_rank = 2
            WHERE e1.exh_rank = 1
        )
        SELECT
            CASE
                WHEN time_gap < 0.1 THEN '0.0-0.1秒差'
                WHEN time_gap < 0.2 THEN '0.1-0.2秒差'
                WHEN time_gap < 0.3 THEN '0.2-0.3秒差'
                ELSE '0.3秒以上'
            END as gap_category,
            COUNT(*) as total,
            SUM(CASE WHEN finish_rank = '1' THEN 1 ELSE 0 END) as first_count
        FROM exh_gap
        GROUP BY gap_category
        ORDER BY gap_category
    """, (start_date, end_date))

    data = cursor.fetchall()

    print("\n展示1位と2位の差による1位の勝率:")
    print("-" * 100)
    print(f"  タイム差      レース数    1着    勝率")
    print("-" * 100)

    gap_stats = {}
    for gap_cat, total, first in data:
        rate = (first / total * 100) if total > 0 else 0
        print(f"  {gap_cat:>12}  {total:>6}    {first:>4}   {rate:>5.1f}%")
        gap_stats[gap_cat] = {'total': total, 'first': first, 'rate': rate}

    return gap_stats


def analyze_exhibition_absolute_time(cursor, start_date: str, end_date: str):
    """展示タイム絶対値の影響分析"""
    print("\n" + "=" * 100)
    print("【4】展示タイム絶対値の影響分析")
    print("=" * 100)

    cursor.execute("""
        SELECT
            CASE
                WHEN exhibition_time < 6.70 THEN '6.70秒未満'
                WHEN exhibition_time < 6.80 THEN '6.70-6.80秒'
                WHEN exhibition_time < 6.90 THEN '6.80-6.90秒'
                WHEN exhibition_time < 7.00 THEN '6.90-7.00秒'
                ELSE '7.00秒以上'
            END as time_range,
            COUNT(*) as total,
            SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as first_count
        FROM race_details rd
        JOIN races r ON rd.race_id = r.id
        LEFT JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number
        WHERE r.race_date >= ? AND r.race_date <= ?
        AND rd.exhibition_time IS NOT NULL
        AND res.rank IS NOT NULL
        GROUP BY time_range
        ORDER BY time_range
    """, (start_date, end_date))

    data = cursor.fetchall()

    print("\n展示タイム絶対値別の1着率:")
    print("-" * 100)
    print(f"  展示タイム      総数    1着    勝率")
    print("-" * 100)

    time_stats = {}
    for time_range, total, first in data:
        rate = (first / total * 100) if total > 0 else 0
        print(f"  {time_range:>14}  {total:>6}  {first:>4}   {rate:>5.1f}%")
        time_stats[time_range] = {'total': total, 'first': first, 'rate': rate}

    return time_stats


def analyze_triple_condition(cursor, start_date: str, end_date: str):
    """展示タイム × ST × 進入の三重複合条件分析"""
    print("\n" + "=" * 100)
    print("【5】展示タイム × ST × 進入の三重複合条件分析")
    print("=" * 100)

    cursor.execute("""
        WITH exh_ranked AS (
            SELECT
                rd.race_id,
                rd.pit_number,
                rd.st_time,
                rd.actual_course,
                res.rank as finish_rank,
                ROW_NUMBER() OVER (
                    PARTITION BY rd.race_id
                    ORDER BY rd.exhibition_time ASC
                ) as exh_rank
            FROM race_details rd
            JOIN races r ON rd.race_id = r.id
            LEFT JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number
            WHERE r.race_date >= ? AND r.race_date <= ?
            AND rd.exhibition_time IS NOT NULL
            AND rd.st_time IS NOT NULL
            AND rd.actual_course IS NOT NULL
            AND res.rank IS NOT NULL
        )
        SELECT
            CASE WHEN exh_rank <= 2 THEN '展示TOP2' ELSE '展示3位以下' END as exh_status,
            CASE WHEN st_time <= 0.15 THEN 'ST良好' ELSE 'ST普通' END as st_status,
            CASE WHEN actual_course <= 2 THEN 'イン' ELSE 'アウト' END as course_status,
            COUNT(*) as total,
            SUM(CASE WHEN finish_rank = '1' THEN 1 ELSE 0 END) as first_count
        FROM exh_ranked
        GROUP BY exh_status, st_status, course_status
        ORDER BY exh_status, st_status, course_status
    """, (start_date, end_date))

    data = cursor.fetchall()

    print("\n展示 × ST × 進入の三重複合条件別1着率:")
    print("-" * 100)
    print(f"  展示状態    ST状態    進入    総数    1着    勝率")
    print("-" * 100)

    triple_stats = {}
    for exh_status, st_status, course_status, total, first in data:
        rate = (first / total * 100) if total > 0 else 0
        key = f"{exh_status}_{st_status}_{course_status}"
        print(f"  {exh_status:>10}  {st_status:>8}  {course_status:>4}  {total:>6}  {first:>4}  {rate:>5.1f}%")
        triple_stats[key] = {'total': total, 'first': first, 'rate': rate}

    return triple_stats


def analyze_exhibition_by_month(cursor, start_date: str, end_date: str):
    """月別の展示タイム信頼性分析"""
    print("\n" + "=" * 100)
    print("【6】月別の展示タイム信頼性分析")
    print("=" * 100)

    cursor.execute("""
        WITH exh_ranked AS (
            SELECT
                strftime('%m', r.race_date) as month,
                rd.race_id,
                rd.pit_number,
                res.rank as finish_rank,
                ROW_NUMBER() OVER (
                    PARTITION BY rd.race_id
                    ORDER BY rd.exhibition_time ASC
                ) as exh_rank
            FROM race_details rd
            JOIN races r ON rd.race_id = r.id
            LEFT JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number
            WHERE r.race_date >= ? AND r.race_date <= ?
            AND rd.exhibition_time IS NOT NULL
            AND res.rank IS NOT NULL
        )
        SELECT
            month,
            COUNT(*) as total,
            SUM(CASE WHEN finish_rank = '1' THEN 1 ELSE 0 END) as first_count
        FROM exh_ranked
        WHERE exh_rank = 1
        GROUP BY month
        ORDER BY month
    """, (start_date, end_date))

    data = cursor.fetchall()

    print("\n月別の展示1位→1着率:")
    print("-" * 100)
    print(f"  月    総数    1着    的中率")
    print("-" * 100)

    month_stats = {}
    for month, total, first in data:
        rate = (first / total * 100) if total > 0 else 0
        print(f"  {month}月  {total:>6}  {first:>4}   {rate:>5.1f}%")
        month_stats[month] = {'total': total, 'first': first, 'rate': rate}

    return month_stats


def analyze_exhibition_by_grade(cursor, start_date: str, end_date: str):
    """グレード別の展示タイム信頼性分析"""
    print("\n" + "=" * 100)
    print("【7】グレード別の展示タイム信頼性分析")
    print("=" * 100)

    cursor.execute("""
        WITH exh_ranked AS (
            SELECT
                r.race_grade,
                rd.race_id,
                rd.pit_number,
                res.rank as finish_rank,
                ROW_NUMBER() OVER (
                    PARTITION BY rd.race_id
                    ORDER BY rd.exhibition_time ASC
                ) as exh_rank
            FROM race_details rd
            JOIN races r ON rd.race_id = r.id
            LEFT JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number
            WHERE r.race_date >= ? AND r.race_date <= ?
            AND rd.exhibition_time IS NOT NULL
            AND res.rank IS NOT NULL
        )
        SELECT
            COALESCE(race_grade, '一般') as grade,
            COUNT(*) as total,
            SUM(CASE WHEN finish_rank = '1' THEN 1 ELSE 0 END) as first_count
        FROM exh_ranked
        WHERE exh_rank = 1
        GROUP BY grade
        HAVING total >= 50
        ORDER BY total DESC
    """, (start_date, end_date))

    data = cursor.fetchall()

    print("\nグレード別の展示1位→1着率:")
    print("-" * 100)
    print(f"  グレード    総数    1着    的中率")
    print("-" * 100)

    grade_stats = {}
    for grade, total, first in data:
        rate = (first / total * 100) if total > 0 else 0
        print(f"  {grade:>8}  {total:>6}  {first:>4}   {rate:>5.1f}%")
        grade_stats[grade] = {'total': total, 'first': first, 'rate': rate}

    return grade_stats


def analyze_exhibition_with_motor(cursor, start_date: str, end_date: str):
    """展示タイム × モーター2連率の複合分析"""
    print("\n" + "=" * 100)
    print("【8】展示タイム × モーター2連率の複合分析")
    print("=" * 100)

    cursor.execute("""
        WITH exh_ranked AS (
            SELECT
                rd.race_id,
                rd.pit_number,
                e.motor_second_rate,
                res.rank as finish_rank,
                ROW_NUMBER() OVER (
                    PARTITION BY rd.race_id
                    ORDER BY rd.exhibition_time ASC
                ) as exh_rank
            FROM race_details rd
            JOIN races r ON rd.race_id = r.id
            JOIN entries e ON rd.race_id = e.race_id AND rd.pit_number = e.pit_number
            LEFT JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number
            WHERE r.race_date >= ? AND r.race_date <= ?
            AND rd.exhibition_time IS NOT NULL
            AND e.motor_second_rate IS NOT NULL
            AND res.rank IS NOT NULL
        )
        SELECT
            CASE WHEN exh_rank <= 2 THEN '展示TOP2' ELSE '展示3位以下' END as exh_status,
            CASE
                WHEN motor_second_rate >= 40 THEN 'モーター良(40%以上)'
                WHEN motor_second_rate >= 30 THEN 'モーター普通(30-40%)'
                ELSE 'モーター悪(30%未満)'
            END as motor_status,
            COUNT(*) as total,
            SUM(CASE WHEN finish_rank = '1' THEN 1 ELSE 0 END) as first_count
        FROM exh_ranked
        GROUP BY exh_status, motor_status
        ORDER BY exh_status, motor_status
    """, (start_date, end_date))

    data = cursor.fetchall()

    print("\n展示 × モーター2連率の複合条件別1着率:")
    print("-" * 100)
    print(f"  展示状態        モーター状態          総数    1着    勝率")
    print("-" * 100)

    motor_stats = {}
    for exh_status, motor_status, total, first in data:
        rate = (first / total * 100) if total > 0 else 0
        key = f"{exh_status}_{motor_status}"
        print(f"  {exh_status:>12}  {motor_status:>24}  {total:>6}  {first:>4}  {rate:>5.1f}%")
        motor_stats[key] = {'total': total, 'first': first, 'rate': rate}

    return motor_stats


def analyze_exhibition_venue_detail(cursor, start_date: str, end_date: str):
    """会場別の詳細分析（展示1位の勝率 + イン率）"""
    print("\n" + "=" * 100)
    print("【9】会場別の詳細分析（展示1位の勝率 + 1コース勝率）")
    print("=" * 100)

    cursor.execute("""
        WITH exh_first AS (
            SELECT
                r.venue_code,
                rd.race_id,
                rd.pit_number,
                rd.actual_course,
                res.rank as finish_rank,
                ROW_NUMBER() OVER (
                    PARTITION BY rd.race_id
                    ORDER BY rd.exhibition_time ASC
                ) as exh_rank
            FROM race_details rd
            JOIN races r ON rd.race_id = r.id
            LEFT JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number
            WHERE r.race_date >= ? AND r.race_date <= ?
            AND rd.exhibition_time IS NOT NULL
            AND rd.actual_course IS NOT NULL
            AND res.rank IS NOT NULL
        ),
        venue_stats AS (
            SELECT
                venue_code,
                COUNT(DISTINCT CASE WHEN exh_rank = 1 THEN race_id END) as exh1_races,
                SUM(CASE WHEN exh_rank = 1 AND finish_rank = '1' THEN 1 ELSE 0 END) as exh1_first,
                COUNT(DISTINCT CASE WHEN actual_course = 1 THEN race_id END) as course1_races,
                SUM(CASE WHEN actual_course = 1 AND finish_rank = '1' THEN 1 ELSE 0 END) as course1_first
            FROM exh_first
            GROUP BY venue_code
        )
        SELECT
            venue_code,
            exh1_races,
            exh1_first,
            course1_races,
            course1_first
        FROM venue_stats
        WHERE exh1_races >= 100
        ORDER BY CAST(exh1_first AS REAL) / exh1_races DESC
    """, (start_date, end_date))

    data = cursor.fetchall()

    print("\n会場別の展示1位勝率 vs 1コース勝率:")
    print("-" * 100)
    print(f"  会場  展示1位→1着  展示率  1コース→1着  1コース率  差分")
    print("-" * 100)

    venue_detail = {}
    for venue, exh1_races, exh1_first, course1_races, course1_first in data:
        exh_rate = (exh1_first / exh1_races * 100) if exh1_races > 0 else 0
        course_rate = (course1_first / course1_races * 100) if course1_races > 0 else 0
        diff = exh_rate - course_rate

        print(f"  {venue:>4}  {exh1_first:>5}/{exh1_races:<5}  {exh_rate:>5.1f}%  {course1_first:>5}/{course1_races:<5}  {course_rate:>6.1f}%  {diff:>+5.1f}%")
        venue_detail[venue] = {
            'exh_rate': exh_rate,
            'course_rate': course_rate,
            'diff': diff
        }

    return venue_detail


def main():
    """メイン処理"""
    db_path = os.path.join(PROJECT_ROOT, 'data/boatrace.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("=" * 100)
    print("展示タイム詳細分析")
    print(f"実行時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 100)

    # 分析対象期間: 2025年全期間
    start_date = '2025-01-01'
    end_date = '2025-12-31'

    print(f"\n分析対象期間: {start_date} ～ {end_date}")

    all_results = {}

    try:
        # 1. 展示ランク × コース別
        all_results['exhibition_course'] = analyze_exhibition_by_course(cursor, start_date, end_date)

        # 2. 展示ランク × 級別
        all_results['exhibition_racer_rank'] = analyze_exhibition_by_racer_rank(cursor, start_date, end_date)

        # 3. 展示タイム差の影響
        all_results['exhibition_gap'] = analyze_exhibition_gap(cursor, start_date, end_date)

        # 4. 展示タイム絶対値の影響
        all_results['exhibition_absolute'] = analyze_exhibition_absolute_time(cursor, start_date, end_date)

        # 5. 三重複合条件
        all_results['triple_condition'] = analyze_triple_condition(cursor, start_date, end_date)

        # 6. 月別の信頼性
        all_results['exhibition_month'] = analyze_exhibition_by_month(cursor, start_date, end_date)

        # 7. グレード別の信頼性
        all_results['exhibition_grade'] = analyze_exhibition_by_grade(cursor, start_date, end_date)

        # 8. モーターとの複合
        all_results['exhibition_motor'] = analyze_exhibition_with_motor(cursor, start_date, end_date)

        # 9. 会場別詳細
        all_results['venue_detail'] = analyze_exhibition_venue_detail(cursor, start_date, end_date)

        # 結果をJSONファイルに保存
        output_file = os.path.join(PROJECT_ROOT, 'docs/exhibition_detailed_results.json')
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump({
                'analysis_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'period': {'start': start_date, 'end': end_date},
                'results': all_results
            }, f, ensure_ascii=False, indent=2)

        print(f"\n\n分析結果をJSONファイルに保存しました: {output_file}")

    except Exception as e:
        print(f"\n[ERROR] 分析中にエラーが発生しました: {e}")
        import traceback
        traceback.print_exc()

    finally:
        conn.close()

    print("\n" + "=" * 100)
    print("分析完了")
    print("=" * 100)


if __name__ == '__main__':
    main()
