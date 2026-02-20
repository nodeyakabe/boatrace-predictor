"""
直前情報スコアリング詳細検証スクリプト

各直前情報要素の影響度を多角的に分析し、
現在のスコアリング方式の最適化案を検討する
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


def analyze_exhibition_time_impact(cursor, start_date: str, end_date: str):
    """展示タイムの影響度分析

    - ランク別（1位/2位/3位/4位/5位/6位）の勝率・2着率・3着率
    - 会場別の展示タイム信頼性
    - 潮位との相関
    """
    print("\n" + "=" * 100)
    print("【1】展示タイムの影響度分析")
    print("=" * 100)

    results = {}

    # 1-1. 展示タイムランク別の着順分析
    print("\n[1-1] 展示タイムランク別の着順分析")
    print("-" * 100)

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
        )
        SELECT
            exh_rank,
            COUNT(*) as total,
            SUM(CASE WHEN finish_rank = '1' THEN 1 ELSE 0 END) as first_count,
            SUM(CASE WHEN finish_rank = '2' THEN 1 ELSE 0 END) as second_count,
            SUM(CASE WHEN finish_rank = '3' THEN 1 ELSE 0 END) as third_count,
            SUM(CASE WHEN finish_rank IN ('1', '2', '3') THEN 1 ELSE 0 END) as top3_count
        FROM exh_ranked
        WHERE finish_rank IS NOT NULL
        GROUP BY exh_rank
        ORDER BY exh_rank
    """, (start_date, end_date))

    exh_rank_data = cursor.fetchall()

    print(f"  展示ランク  総数      1着      2着      3着    連対内   3連対内")
    print("-" * 100)

    exh_rank_stats = {}
    for rank, total, first, second, third, top3 in exh_rank_data:
        first_rate = (first / total * 100) if total > 0 else 0
        second_rate = (second / total * 100) if total > 0 else 0
        third_rate = (third / total * 100) if total > 0 else 0
        top2_rate = ((first + second) / total * 100) if total > 0 else 0
        top3_rate = (top3 / total * 100) if total > 0 else 0

        print(f"  {rank}位    {total:>6}  {first:>5}({first_rate:5.1f}%)  {second:>5}({second_rate:5.1f}%)  {third:>5}({third_rate:5.1f}%)  {top2_rate:>5.1f}%    {top3_rate:>5.1f}%")

        exh_rank_stats[rank] = {
            'total': total,
            'first_rate': first_rate,
            'second_rate': second_rate,
            'third_rate': third_rate,
            'top2_rate': top2_rate,
            'top3_rate': top3_rate
        }

    results['exhibition_rank'] = exh_rank_stats

    # 1-2. 会場別の展示タイム信頼性
    print("\n[1-2] 会場別の展示タイム信頼性（展示1位の1着率TOP10/BOTTOM10）")
    print("-" * 100)

    cursor.execute("""
        WITH exh_ranked AS (
            SELECT
                r.venue_code,
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
        )
        SELECT
            venue_code,
            COUNT(*) as total,
            SUM(CASE WHEN finish_rank = '1' THEN 1 ELSE 0 END) as first_count
        FROM exh_ranked
        WHERE exh_rank = 1 AND finish_rank IS NOT NULL
        GROUP BY venue_code
        HAVING total >= 100
        ORDER BY CAST(first_count AS REAL) / total DESC
    """, (start_date, end_date))

    venue_exh_data = cursor.fetchall()

    print("  【TOP10 - 展示タイムが信頼できる会場】")
    print(f"  会場    レース数  展示1位→1着  的中率")
    print("-" * 100)

    venue_stats = {}
    for venue, total, first in venue_exh_data[:10]:
        rate = (first / total * 100) if total > 0 else 0
        print(f"  {venue:>4}    {total:>6}    {first:>6}     {rate:>5.1f}%")
        venue_stats[venue] = {'total': total, 'first_rate': rate, 'category': 'high_trust'}

    print("\n  【BOTTOM10 - 展示タイムが信頼しにくい会場】")
    print(f"  会場    レース数  展示1位→1着  的中率")
    print("-" * 100)

    for venue, total, first in venue_exh_data[-10:]:
        rate = (first / total * 100) if total > 0 else 0
        print(f"  {venue:>4}    {total:>6}    {first:>6}     {rate:>5.1f}%")
        if venue not in venue_stats:
            venue_stats[venue] = {'total': total, 'first_rate': rate, 'category': 'low_trust'}

    results['venue_exhibition'] = venue_stats

    # 1-3. 潮位との相関（tide_statusがある場合）
    print("\n[1-3] 潮位との相関分析")
    print("-" * 100)

    cursor.execute("""
        SELECT COUNT(*) as cnt
        FROM races r
        JOIN tide t ON r.venue_code = t.venue_code
            AND DATE(r.race_date) = DATE(t.tide_date)
        WHERE r.race_date >= ? AND r.race_date <= ?
        LIMIT 1
    """, (start_date, end_date))

    tide_count = cursor.fetchone()[0]

    if tide_count > 0:
        # 潮位データがあれば分析（2段階クエリで対応）
        cursor.execute("""
            WITH exh_ranked AS (
                SELECT
                    rd.race_id,
                    rd.pit_number,
                    t.tide_level,
                    res.rank as finish_rank,
                    ROW_NUMBER() OVER (
                        PARTITION BY rd.race_id
                        ORDER BY rd.exhibition_time ASC
                    ) as exh_rank
                FROM race_details rd
                JOIN races r ON rd.race_id = r.id
                JOIN tide t ON r.venue_code = t.venue_code
                    AND DATE(r.race_date) = DATE(t.tide_date)
                LEFT JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number
                WHERE r.race_date >= ? AND r.race_date <= ?
                AND rd.exhibition_time IS NOT NULL
            )
            SELECT
                CASE
                    WHEN tide_level >= 200 THEN 'high'
                    WHEN tide_level >= 100 THEN 'mid'
                    ELSE 'low'
                END as tide_category,
                COUNT(*) as total,
                SUM(CASE WHEN finish_rank = '1' THEN 1 ELSE 0 END) as first_count
            FROM exh_ranked
            WHERE finish_rank IS NOT NULL AND exh_rank = 1
            GROUP BY tide_category
        """, (start_date, end_date))

        tide_data = cursor.fetchall()

        print(f"  潮位レベル  レース数  展示1位→1着  的中率")
        print("-" * 100)

        tide_stats = {}
        for tide_cat, total, first in tide_data:
            rate = (first / total * 100) if total > 0 else 0
            print(f"  {tide_cat:>10}  {total:>6}    {first:>6}     {rate:>5.1f}%")
            tide_stats[tide_cat] = {'total': total, 'first_rate': rate}

        results['tide_exhibition'] = tide_stats
    else:
        print("  [INFO] 潮位データが不足しているため、分析をスキップします")
        results['tide_exhibition'] = {}

    return results


def analyze_st_impact(cursor, start_date: str, end_date: str):
    """STの影響度分析

    - ST範囲別（0.10以下/0.11-0.15/0.16-0.20/0.20超）の勝率
    - フライング・出遅れの影響
    - 前走STとの相関
    """
    print("\n" + "=" * 100)
    print("【2】ST（スタートタイミング）の影響度分析")
    print("=" * 100)

    results = {}

    # 2-1. ST範囲別の着順分析
    print("\n[2-1] ST範囲別の着順分析")
    print("-" * 100)

    cursor.execute("""
        SELECT
            CASE
                WHEN st_time <= 0.10 THEN '0.10以下'
                WHEN st_time <= 0.15 THEN '0.11-0.15'
                WHEN st_time <= 0.20 THEN '0.16-0.20'
                ELSE '0.20超'
            END as st_range,
            COUNT(*) as total,
            SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as first_count,
            SUM(CASE WHEN res.rank = '2' THEN 1 ELSE 0 END) as second_count,
            SUM(CASE WHEN res.rank = '3' THEN 1 ELSE 0 END) as third_count
        FROM race_details rd
        JOIN races r ON rd.race_id = r.id
        LEFT JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number
        WHERE r.race_date >= ? AND r.race_date <= ?
        AND rd.st_time IS NOT NULL
        AND res.rank IS NOT NULL
        GROUP BY st_range
        ORDER BY
            CASE st_range
                WHEN '0.10以下' THEN 1
                WHEN '0.11-0.15' THEN 2
                WHEN '0.16-0.20' THEN 3
                ELSE 4
            END
    """, (start_date, end_date))

    st_range_data = cursor.fetchall()

    print(f"  ST範囲      総数      1着      2着      3着    連対内")
    print("-" * 100)

    st_stats = {}
    for st_range, total, first, second, third in st_range_data:
        first_rate = (first / total * 100) if total > 0 else 0
        second_rate = (second / total * 100) if total > 0 else 0
        third_rate = (third / total * 100) if total > 0 else 0
        top2_rate = ((first + second) / total * 100) if total > 0 else 0

        print(f"  {st_range:>10}  {total:>6}  {first:>5}({first_rate:5.1f}%)  {second:>5}({second_rate:5.1f}%)  {third:>5}({third_rate:5.1f}%)  {top2_rate:>5.1f}%")

        st_stats[st_range] = {
            'total': total,
            'first_rate': first_rate,
            'second_rate': second_rate,
            'third_rate': third_rate,
            'top2_rate': top2_rate
        }

    results['st_range'] = st_stats

    # 2-2. フライング・出遅れ（ST < 0 / ST > 1.0）の影響
    print("\n[2-2] フライング・出遅れの影響")
    print("-" * 100)

    cursor.execute("""
        SELECT
            CASE
                WHEN st_time < 0 THEN 'フライング'
                WHEN st_time > 1.0 THEN '出遅れ'
                ELSE '正常'
            END as st_status,
            COUNT(*) as total,
            SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as first_count,
            SUM(CASE WHEN res.rank IN ('1', '2', '3') THEN 1 ELSE 0 END) as top3_count
        FROM race_details rd
        JOIN races r ON rd.race_id = r.id
        LEFT JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number
        WHERE r.race_date >= ? AND r.race_date <= ?
        AND rd.st_time IS NOT NULL
        AND res.rank IS NOT NULL
        GROUP BY st_status
    """, (start_date, end_date))

    st_status_data = cursor.fetchall()

    print(f"  ST状態        総数      1着    3連対内")
    print("-" * 100)

    st_status_stats = {}
    for st_status, total, first, top3 in st_status_data:
        first_rate = (first / total * 100) if total > 0 else 0
        top3_rate = (top3 / total * 100) if total > 0 else 0

        print(f"  {st_status:>12}  {total:>6}  {first:>5}({first_rate:5.1f}%)  {top3:>5}({top3_rate:5.1f}%)")

        st_status_stats[st_status] = {
            'total': total,
            'first_rate': first_rate,
            'top3_rate': top3_rate
        }

    results['st_status'] = st_status_stats

    # 2-3. 前走STとの相関
    print("\n[2-3] 前走STとの相関（前走ST良好 vs 不良）")
    print("-" * 100)

    cursor.execute("""
        SELECT
            CASE
                WHEN prev_race_st IS NULL THEN '前走データなし'
                WHEN prev_race_st <= 0.15 THEN '前走ST良好'
                ELSE '前走ST不良'
            END as prev_st_status,
            COUNT(*) as total,
            SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as first_count
        FROM race_details rd
        JOIN races r ON rd.race_id = r.id
        LEFT JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number
        WHERE r.race_date >= ? AND r.race_date <= ?
        AND rd.st_time IS NOT NULL
        AND res.rank IS NOT NULL
        GROUP BY prev_st_status
    """, (start_date, end_date))

    prev_st_data = cursor.fetchall()

    print(f"  前走ST状態          総数      1着      的中率")
    print("-" * 100)

    prev_st_stats = {}
    for prev_st_status, total, first in prev_st_data:
        first_rate = (first / total * 100) if total > 0 else 0

        print(f"  {prev_st_status:>18}  {total:>6}  {first:>5}    {first_rate:>5.1f}%")

        prev_st_stats[prev_st_status] = {
            'total': total,
            'first_rate': first_rate
        }

    results['prev_st'] = prev_st_stats

    return results


def analyze_course_impact(cursor, start_date: str, end_date: str):
    """進入コースの影響度分析

    - 枠なり進入 vs 枠番変更の勝率差
    - 会場別の進入変動率
    - インコース取りの成功率
    """
    print("\n" + "=" * 100)
    print("【3】進入コースの影響度分析")
    print("=" * 100)

    results = {}

    # 3-1. 枠なり vs 枠番変更
    print("\n[3-1] 枠なり進入 vs 枠番変更の勝率差")
    print("-" * 100)

    cursor.execute("""
        SELECT
            CASE
                WHEN rd.actual_course = rd.pit_number THEN '枠なり'
                ELSE '枠番変更'
            END as course_status,
            COUNT(*) as total,
            SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as first_count,
            SUM(CASE WHEN res.rank IN ('1', '2', '3') THEN 1 ELSE 0 END) as top3_count
        FROM race_details rd
        JOIN races r ON rd.race_id = r.id
        LEFT JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number
        WHERE r.race_date >= ? AND r.race_date <= ?
        AND rd.actual_course IS NOT NULL
        AND res.rank IS NOT NULL
        GROUP BY course_status
    """, (start_date, end_date))

    course_status_data = cursor.fetchall()

    print(f"  進入状態      総数      1着    3連対内")
    print("-" * 100)

    course_stats = {}
    for course_status, total, first, top3 in course_status_data:
        first_rate = (first / total * 100) if total > 0 else 0
        top3_rate = (top3 / total * 100) if total > 0 else 0

        print(f"  {course_status:>10}  {total:>6}  {first:>5}({first_rate:5.1f}%)  {top3:>5}({top3_rate:5.1f}%)")

        course_stats[course_status] = {
            'total': total,
            'first_rate': first_rate,
            'top3_rate': top3_rate
        }

    results['course_change'] = course_stats

    # 3-2. 会場別の進入変動率
    print("\n[3-2] 会場別の進入変動率（TOP10/BOTTOM10）")
    print("-" * 100)

    cursor.execute("""
        SELECT
            r.venue_code,
            COUNT(*) as total,
            SUM(CASE WHEN rd.actual_course != rd.pit_number THEN 1 ELSE 0 END) as changed
        FROM race_details rd
        JOIN races r ON rd.race_id = r.id
        WHERE r.race_date >= ? AND r.race_date <= ?
        AND rd.actual_course IS NOT NULL
        GROUP BY r.venue_code
        HAVING total >= 100
        ORDER BY CAST(changed AS REAL) / total DESC
    """, (start_date, end_date))

    venue_course_data = cursor.fetchall()

    print("  【TOP10 - 進入変更が多い会場】")
    print(f"  会場    総数    進入変更  変更率")
    print("-" * 100)

    venue_course_stats = {}
    for venue, total, changed in venue_course_data[:10]:
        change_rate = (changed / total * 100) if total > 0 else 0
        print(f"  {venue:>4}  {total:>6}  {changed:>6}    {change_rate:>5.1f}%")
        venue_course_stats[venue] = {'total': total, 'change_rate': change_rate, 'category': 'high_change'}

    print("\n  【BOTTOM10 - 進入変更が少ない会場（枠なり傾向）】")
    print(f"  会場    総数    進入変更  変更率")
    print("-" * 100)

    for venue, total, changed in venue_course_data[-10:]:
        change_rate = (changed / total * 100) if total > 0 else 0
        print(f"  {venue:>4}  {total:>6}  {changed:>6}    {change_rate:>5.1f}%")
        if venue not in venue_course_stats:
            venue_course_stats[venue] = {'total': total, 'change_rate': change_rate, 'category': 'low_change'}

    results['venue_course_change'] = venue_course_stats

    # 3-3. インコース取り（外枠→1-2コース）の成功率
    print("\n[3-3] インコース取り（外枠→1-2コース）の成功率")
    print("-" * 100)

    cursor.execute("""
        SELECT
            rd.pit_number as pit,
            rd.actual_course as course,
            COUNT(*) as total,
            SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as first_count
        FROM race_details rd
        JOIN races r ON rd.race_id = r.id
        LEFT JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number
        WHERE r.race_date >= ? AND r.race_date <= ?
        AND rd.actual_course IN (1, 2)
        AND rd.pit_number > rd.actual_course
        AND res.rank IS NOT NULL
        GROUP BY pit, course
        ORDER BY pit, course
    """, (start_date, end_date))

    inner_take_data = cursor.fetchall()

    print(f"  枠番→コース    総数    1着    勝率")
    print("-" * 100)

    inner_take_stats = {}
    for pit, course, total, first in inner_take_data:
        first_rate = (first / total * 100) if total > 0 else 0
        key = f"{pit}→{course}"
        print(f"  {key:>10}  {total:>6}  {first:>4}   {first_rate:>5.1f}%")

        inner_take_stats[key] = {
            'total': total,
            'first_rate': first_rate
        }

    results['inner_course_take'] = inner_take_stats

    return results


def analyze_tilt_wind_impact(cursor, start_date: str, end_date: str):
    """チルト・風の影響度分析

    - チルト角度（-0.5/0/+0.5/+1.0/+1.5）の勝率
    - 追い風・向かい風の影響（風速別）
    - コース別の風影響度
    """
    print("\n" + "=" * 100)
    print("【4】チルト・風の影響度分析")
    print("=" * 100)

    results = {}

    # 4-1. チルト角度別の勝率
    print("\n[4-1] チルト角度別の勝率")
    print("-" * 100)

    cursor.execute("""
        SELECT
            rd.tilt_angle,
            COUNT(*) as total,
            SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as first_count,
            SUM(CASE WHEN res.rank IN ('1', '2', '3') THEN 1 ELSE 0 END) as top3_count
        FROM race_details rd
        JOIN races r ON rd.race_id = r.id
        LEFT JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number
        WHERE r.race_date >= ? AND r.race_date <= ?
        AND rd.tilt_angle IS NOT NULL
        AND res.rank IS NOT NULL
        GROUP BY rd.tilt_angle
        HAVING total >= 100
        ORDER BY rd.tilt_angle
    """, (start_date, end_date))

    tilt_data = cursor.fetchall()

    print(f"  チルト    総数    1着   勝率   3連対内")
    print("-" * 100)

    tilt_stats = {}
    for tilt, total, first, top3 in tilt_data:
        first_rate = (first / total * 100) if total > 0 else 0
        top3_rate = (top3 / total * 100) if total > 0 else 0

        print(f"  {tilt:>6}  {total:>6}  {first:>4}  {first_rate:>5.1f}%  {top3:>5}({top3_rate:5.1f}%)")

        tilt_stats[str(tilt)] = {
            'total': total,
            'first_rate': first_rate,
            'top3_rate': top3_rate
        }

    results['tilt_angle'] = tilt_stats

    # 4-2. 風速別の影響
    print("\n[4-2] 風速別の影響（気象データがある場合）")
    print("-" * 100)

    cursor.execute("""
        SELECT COUNT(*) as cnt
        FROM races r
        JOIN weather w ON r.venue_code = w.venue_code
            AND DATE(r.race_date) = DATE(w.weather_date)
        WHERE r.race_date >= ? AND r.race_date <= ?
        LIMIT 1
    """, (start_date, end_date))

    weather_count = cursor.fetchone()[0]

    if weather_count > 0:
        cursor.execute("""
            WITH race_weather AS (
                SELECT
                    rd.race_id,
                    rd.pit_number,
                    rd.actual_course,
                    res.rank,
                    w.wind_speed
                FROM race_details rd
                JOIN races r ON rd.race_id = r.id
                JOIN weather w ON r.venue_code = w.venue_code
                    AND DATE(r.race_date) = DATE(w.weather_date)
                LEFT JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number
                WHERE r.race_date >= ? AND r.race_date <= ?
                AND w.wind_speed IS NOT NULL
                AND res.rank IS NOT NULL
            )
            SELECT
                CASE
                    WHEN wind_speed < 3 THEN '弱風(3m未満)'
                    WHEN wind_speed < 6 THEN '中風(3-6m)'
                    ELSE '強風(6m以上)'
                END as wind_category,
                COUNT(*) as total,
                SUM(CASE WHEN rank = '1' THEN 1 ELSE 0 END) as first_count
            FROM race_weather
            GROUP BY wind_category
        """, (start_date, end_date))

        wind_data = cursor.fetchall()

        print(f"  風速カテゴリ      総数    1着   勝率")
        print("-" * 100)

        wind_stats = {}
        for wind_cat, total, first in wind_data:
            first_rate = (first / total * 100) if total > 0 else 0

            print(f"  {wind_cat:>16}  {total:>6}  {first:>4}  {first_rate:>5.1f}%")

            wind_stats[wind_cat] = {
                'total': total,
                'first_rate': first_rate
            }

        results['wind_speed'] = wind_stats

        # 4-3. コース別の風影響度
        print("\n[4-3] コース別の風影響度（強風時の勝率変化）")
        print("-" * 100)

        cursor.execute("""
            WITH race_weather AS (
                SELECT
                    rd.race_id,
                    rd.pit_number,
                    rd.actual_course,
                    res.rank,
                    w.wind_speed
                FROM race_details rd
                JOIN races r ON rd.race_id = r.id
                JOIN weather w ON r.venue_code = w.venue_code
                    AND DATE(r.race_date) = DATE(w.weather_date)
                LEFT JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number
                WHERE r.race_date >= ? AND r.race_date <= ?
                AND w.wind_speed IS NOT NULL
                AND rd.actual_course IS NOT NULL
                AND res.rank IS NOT NULL
            )
            SELECT
                actual_course,
                CASE WHEN wind_speed >= 6 THEN '強風' ELSE '弱風' END as wind_status,
                COUNT(*) as total,
                SUM(CASE WHEN rank = '1' THEN 1 ELSE 0 END) as first_count
            FROM race_weather
            GROUP BY actual_course, wind_status
            ORDER BY actual_course, wind_status
        """, (start_date, end_date))

        course_wind_data = cursor.fetchall()

        print(f"  コース  風状態    総数    1着   勝率")
        print("-" * 100)

        course_wind_stats = {}
        for course, wind_status, total, first in course_wind_data:
            first_rate = (first / total * 100) if total > 0 else 0
            key = f"{course}_{wind_status}"

            print(f"  {course:>4}   {wind_status:>4}  {total:>6}  {first:>4}  {first_rate:>5.1f}%")

            course_wind_stats[key] = {
                'total': total,
                'first_rate': first_rate
            }

        results['course_wind'] = course_wind_stats
    else:
        print("  [INFO] 気象データが不足しているため、分析をスキップします")
        results['wind_speed'] = {}
        results['course_wind'] = {}

    return results


def analyze_compound_conditions(cursor, start_date: str, end_date: str):
    """複合条件での影響分析

    - 展示タイム × ST
    - 進入コース × 風
    - チルト × コース
    """
    print("\n" + "=" * 100)
    print("【5】複合条件での影響分析")
    print("=" * 100)

    results = {}

    # 5-1. 展示タイム × ST の複合効果
    print("\n[5-1] 展示タイム1位 × ST良好 の複合効果")
    print("-" * 100)

    cursor.execute("""
        WITH exh_ranked AS (
            SELECT
                rd.race_id,
                rd.pit_number,
                rd.st_time,
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
            AND res.rank IS NOT NULL
        )
        SELECT
            CASE WHEN exh_rank = 1 THEN '展示1位' ELSE '展示2位以下' END as exh_status,
            CASE WHEN st_time <= 0.15 THEN 'ST良好' ELSE 'ST普通' END as st_status,
            COUNT(*) as total,
            SUM(CASE WHEN finish_rank = '1' THEN 1 ELSE 0 END) as first_count
        FROM exh_ranked
        GROUP BY exh_status, st_status
        ORDER BY exh_status, st_status
    """, (start_date, end_date))

    compound_exh_st = cursor.fetchall()

    print(f"  展示状態      ST状態    総数    1着   勝率")
    print("-" * 100)

    exh_st_stats = {}
    for exh_status, st_status, total, first in compound_exh_st:
        first_rate = (first / total * 100) if total > 0 else 0
        key = f"{exh_status}_{st_status}"

        print(f"  {exh_status:>12}  {st_status:>8}  {total:>6}  {first:>4}  {first_rate:>5.1f}%")

        exh_st_stats[key] = {
            'total': total,
            'first_rate': first_rate
        }

    results['exhibition_st'] = exh_st_stats

    # 5-2. 進入コース × 風 の複合効果
    print("\n[5-2] 進入コース × 風速 の複合効果（気象データがある場合）")
    print("-" * 100)

    cursor.execute("""
        SELECT COUNT(*) as cnt
        FROM races r
        JOIN weather w ON r.venue_code = w.venue_code
            AND DATE(r.race_date) = DATE(w.weather_date)
        WHERE r.race_date >= ? AND r.race_date <= ?
        LIMIT 1
    """, (start_date, end_date))

    weather_count = cursor.fetchone()[0]

    if weather_count > 0:
        cursor.execute("""
            WITH race_weather AS (
                SELECT
                    rd.race_id,
                    rd.pit_number,
                    rd.actual_course,
                    res.rank,
                    w.wind_speed
                FROM race_details rd
                JOIN races r ON rd.race_id = r.id
                JOIN weather w ON r.venue_code = w.venue_code
                    AND DATE(r.race_date) = DATE(w.weather_date)
                LEFT JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number
                WHERE r.race_date >= ? AND r.race_date <= ?
                AND w.wind_speed IS NOT NULL
                AND rd.actual_course IN (1, 2, 3, 4, 5, 6)
                AND res.rank IS NOT NULL
            )
            SELECT
                actual_course,
                CASE
                    WHEN wind_speed < 3 THEN '弱風'
                    WHEN wind_speed < 6 THEN '中風'
                    ELSE '強風'
                END as wind_category,
                COUNT(*) as total,
                SUM(CASE WHEN rank = '1' THEN 1 ELSE 0 END) as first_count
            FROM race_weather
            GROUP BY actual_course, wind_category
            HAVING total >= 50
            ORDER BY actual_course, wind_category
        """, (start_date, end_date))

        course_wind_compound = cursor.fetchall()

        print(f"  コース  風カテゴリ    総数    1着   勝率")
        print("-" * 100)

        course_wind_compound_stats = {}
        for course, wind_cat, total, first in course_wind_compound:
            first_rate = (first / total * 100) if total > 0 else 0
            key = f"{course}_{wind_cat}"

            print(f"  {course:>4}   {wind_cat:>8}  {total:>6}  {first:>4}  {first_rate:>5.1f}%")

            course_wind_compound_stats[key] = {
                'total': total,
                'first_rate': first_rate
            }

        results['course_wind_compound'] = course_wind_compound_stats
    else:
        print("  [INFO] 気象データが不足しているため、分析をスキップします")
        results['course_wind_compound'] = {}

    # 5-3. チルト × コース の複合効果
    print("\n[5-3] チルト × コース の複合効果（イン vs アウト）")
    print("-" * 100)

    cursor.execute("""
        SELECT
            CASE WHEN rd.actual_course IN (1, 2) THEN 'イン' ELSE 'アウト' END as course_group,
            CASE
                WHEN rd.tilt_angle <= 0 THEN 'チルト低'
                WHEN rd.tilt_angle <= 1.0 THEN 'チルト中'
                ELSE 'チルト高'
            END as tilt_category,
            COUNT(*) as total,
            SUM(CASE WHEN res.rank = '1' THEN 1 ELSE 0 END) as first_count
        FROM race_details rd
        JOIN races r ON rd.race_id = r.id
        LEFT JOIN results res ON rd.race_id = res.race_id AND rd.pit_number = res.pit_number
        WHERE r.race_date >= ? AND r.race_date <= ?
        AND rd.actual_course IS NOT NULL
        AND rd.tilt_angle IS NOT NULL
        AND res.rank IS NOT NULL
        GROUP BY course_group, tilt_category
        ORDER BY course_group, tilt_category
    """, (start_date, end_date))

    tilt_course_compound = cursor.fetchall()

    print(f"  コース群  チルト      総数    1着   勝率")
    print("-" * 100)

    tilt_course_stats = {}
    for course_group, tilt_cat, total, first in tilt_course_compound:
        first_rate = (first / total * 100) if total > 0 else 0
        key = f"{course_group}_{tilt_cat}"

        print(f"  {course_group:>6}   {tilt_cat:>8}  {total:>6}  {first:>4}  {first_rate:>5.1f}%")

        tilt_course_stats[key] = {
            'total': total,
            'first_rate': first_rate
        }

    results['tilt_course'] = tilt_course_stats

    return results


def generate_optimization_suggestions(all_results: dict):
    """分析結果から最適化提案を生成"""
    print("\n" + "=" * 100)
    print("【6】スコアリング最適化提案")
    print("=" * 100)

    suggestions = []

    # 展示タイムの提案
    if 'exhibition' in all_results and 'exhibition_rank' in all_results['exhibition']:
        exh_rank_1 = all_results['exhibition']['exhibition_rank'].get(1, {})
        exh_rank_6 = all_results['exhibition']['exhibition_rank'].get(6, {})

        if exh_rank_1.get('first_rate', 0) > 30:
            suggestions.append({
                'category': '展示タイム',
                'finding': f"展示1位の1着率は{exh_rank_1.get('first_rate', 0):.1f}%と高い",
                'suggestion': '展示タイムのスコアウェイトを現在の25点から30点に引き上げ'
            })

    # STの提案
    if 'st' in all_results and 'st_range' in all_results['st']:
        st_best = all_results['st']['st_range'].get('0.10以下', {})
        st_worst = all_results['st']['st_range'].get('0.20超', {})

        if st_best.get('first_rate', 0) > st_worst.get('first_rate', 0) * 1.5:
            suggestions.append({
                'category': 'ST',
                'finding': f"ST0.10以下は{st_best.get('first_rate', 0):.1f}%、0.20超は{st_worst.get('first_rate', 0):.1f}%と大きな差",
                'suggestion': 'STのスコア配点を段階的に強化（良好+30点、不良-10点）'
            })

    # 進入コースの提案
    if 'course' in all_results and 'course_change' in all_results['course']:
        wakuwari = all_results['course']['course_change'].get('枠なり', {})
        changed = all_results['course']['course_change'].get('枠番変更', {})

        if wakuwari.get('first_rate', 0) != changed.get('first_rate', 0):
            diff = abs(wakuwari.get('first_rate', 0) - changed.get('first_rate', 0))
            suggestions.append({
                'category': '進入コース',
                'finding': f"枠なり{wakuwari.get('first_rate', 0):.1f}% vs 枠番変更{changed.get('first_rate', 0):.1f}%（差{diff:.1f}%）",
                'suggestion': '会場別の進入変動傾向をスコアに反映（大村/下関は進入予測重視）'
            })

    # 複合条件の提案
    if 'compound' in all_results and 'exhibition_st' in all_results['compound']:
        best_combo = all_results['compound']['exhibition_st'].get('展示1位_ST良好', {})

        if best_combo.get('first_rate', 0) > 40:
            suggestions.append({
                'category': '複合条件',
                'finding': f"展示1位×ST良好の組み合わせで{best_combo.get('first_rate', 0):.1f}%と非常に高い勝率",
                'suggestion': '複合条件ボーナス導入：展示TOP3 & ST良好 → +15点'
            })

    print("\n最適化提案サマリー:")
    print("-" * 100)

    for i, sug in enumerate(suggestions, 1):
        print(f"\n提案{i}: {sug['category']}")
        print(f"  発見: {sug['finding']}")
        print(f"  提案: {sug['suggestion']}")

    return suggestions


def main():
    """メイン処理"""
    db_path = os.path.join(PROJECT_ROOT, 'data/boatrace.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("=" * 100)
    print("直前情報スコアリング詳細検証")
    print(f"実行時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 100)

    # 分析対象期間: 2025年全期間
    start_date = '2025-01-01'
    end_date = '2025-12-31'

    print(f"\n分析対象期間: {start_date} ～ {end_date}")

    all_results = {}

    try:
        # 1. 展示タイムの影響度分析
        all_results['exhibition'] = analyze_exhibition_time_impact(cursor, start_date, end_date)

        # 2. STの影響度分析
        all_results['st'] = analyze_st_impact(cursor, start_date, end_date)

        # 3. 進入コースの影響度分析
        all_results['course'] = analyze_course_impact(cursor, start_date, end_date)

        # 4. チルト・風の影響度分析
        all_results['tilt_wind'] = analyze_tilt_wind_impact(cursor, start_date, end_date)

        # 5. 複合条件での影響分析
        all_results['compound'] = analyze_compound_conditions(cursor, start_date, end_date)

        # 6. 最適化提案の生成
        suggestions = generate_optimization_suggestions(all_results)

        # 結果をJSONファイルに保存
        output_file = os.path.join(PROJECT_ROOT, 'docs/beforeinfo_analysis_results.json')
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump({
                'analysis_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'period': {'start': start_date, 'end': end_date},
                'results': all_results,
                'suggestions': suggestions
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
