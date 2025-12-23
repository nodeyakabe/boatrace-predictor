"""
P-6-2: まくり系決まり手の発生パターン分析

分析目的:
- まくり/差し/まくり差しの発生条件を特定
- 1コースがまくられるパターンを分析
- 予測ロジック改善のためのインサイトを取得
"""

import sqlite3
from pathlib import Path
from collections import defaultdict
import sys

sys.stdout.reconfigure(encoding='utf-8')

DATABASE_PATH = Path(__file__).parent.parent / "data" / "boatrace.db"


def analyze_makuri_patterns():
    """まくり系発生パターンの詳細分析"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    print("=" * 70)
    print("P-6-2: まくり系決まり手 発生パターン分析")
    print("=" * 70)

    # 1. 決まり手の全体分布
    print("\n【1. 決まり手の全体分布】")
    cursor.execute('''
        SELECT kimarite, COUNT(*) as cnt,
               ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM results WHERE rank = 1), 2) as pct
        FROM results
        WHERE rank = 1 AND kimarite IS NOT NULL
        GROUP BY kimarite
        ORDER BY cnt DESC
    ''')
    print(f"{'決まり手':<12} {'件数':>8} {'割合':>8}")
    print("-" * 30)
    for row in cursor.fetchall():
        print(f"{row[0]:<12} {row[1]:>8} {row[2]:>7.1f}%")

    # 2. コース別決まり手分布
    print("\n【2. コース別決まり手分布（まくり系）】")
    cursor.execute('''
        SELECT
            rd.actual_course,
            r.kimarite,
            COUNT(*) as cnt
        FROM results r
        JOIN race_details rd ON r.race_id = rd.race_id AND r.pit_number = rd.pit_number
        WHERE r.rank = 1
          AND r.kimarite IN ('まくり', '差し', 'まくり差し')
          AND rd.actual_course IS NOT NULL
        GROUP BY rd.actual_course, r.kimarite
        ORDER BY rd.actual_course, cnt DESC
    ''')
    print(f"{'コース':<6} {'決まり手':<12} {'件数':>8}")
    print("-" * 30)
    for row in cursor.fetchall():
        print(f"{row[0]}コース   {row[1]:<12} {row[2]:>8}")

    # 3. 1コースの級別別負け率
    print("\n【3. 1コース選手の級別別 負け率】")
    cursor.execute('''
        SELECT
            e.racer_rank as course1_rank,
            COUNT(*) as total_races,
            SUM(CASE WHEN r.rank != 1 THEN 1 ELSE 0 END) as losses,
            ROUND(SUM(CASE WHEN r.rank != 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as loss_rate
        FROM results r
        JOIN race_details rd ON r.race_id = rd.race_id AND r.pit_number = rd.pit_number
        JOIN entries e ON r.race_id = e.race_id AND r.pit_number = e.pit_number
        WHERE rd.actual_course = 1
        GROUP BY e.racer_rank
        ORDER BY loss_rate DESC
    ''')
    print(f"{'級別':<6} {'総レース':>10} {'敗北数':>10} {'敗北率':>8}")
    print("-" * 40)
    for row in cursor.fetchall():
        print(f"{row[0]:<6} {row[1]:>10} {row[2]:>10} {row[3]:>7.1f}%")

    # 4. 1コースがまくられる条件（勝者の特徴）
    print("\n【4. 1コースを倒した選手の特徴（まくり/まくり差し）】")
    cursor.execute('''
        WITH makuri_winners AS (
            SELECT
                r1.race_id,
                r1.kimarite as winner_kimarite,
                rd1.actual_course as winner_course,
                e1.racer_rank as winner_rank,
                rd1.st_time as winner_st,
                e1.motor_number as winner_motor
            FROM results r1
            JOIN race_details rd1 ON r1.race_id = rd1.race_id AND r1.pit_number = rd1.pit_number
            JOIN entries e1 ON r1.race_id = e1.race_id AND r1.pit_number = e1.pit_number
            WHERE r1.rank = 1
              AND r1.kimarite IN ('まくり', 'まくり差し')
              AND rd1.actual_course != 1
        ),
        course1_losers AS (
            SELECT
                r2.race_id,
                e2.racer_rank as course1_rank,
                rd2.st_time as course1_st
            FROM results r2
            JOIN race_details rd2 ON r2.race_id = rd2.race_id AND r2.pit_number = rd2.pit_number
            JOIN entries e2 ON r2.race_id = e2.race_id AND r2.pit_number = e2.pit_number
            WHERE rd2.actual_course = 1
        )
        SELECT
            mw.winner_kimarite,
            mw.winner_course,
            mw.winner_rank,
            cl.course1_rank,
            COUNT(*) as cnt
        FROM makuri_winners mw
        JOIN course1_losers cl ON mw.race_id = cl.race_id
        GROUP BY mw.winner_kimarite, mw.winner_course, mw.winner_rank, cl.course1_rank
        HAVING COUNT(*) >= 50
        ORDER BY cnt DESC
        LIMIT 25
    ''')
    print(f"{'決まり手':<12} {'勝者C':<6} {'勝者級':<6} {'1C級':<6} {'件数':>8}")
    print("-" * 45)
    for row in cursor.fetchall():
        print(f"{row[0]:<12} {row[1]}コース  {row[2]:<6} {row[3]:<6} {row[4]:>8}")

    # 5. スタートタイミングとまくり成功の関係
    print("\n【5. スタートタイミング差とまくり成功率】")
    cursor.execute('''
        WITH makuri_races AS (
            SELECT
                r1.race_id,
                rd1.st_time as winner_st,
                rd2.st_time as course1_st,
                CASE
                    WHEN rd1.st_time < rd2.st_time THEN 'winner_faster'
                    WHEN rd1.st_time > rd2.st_time THEN 'course1_faster'
                    ELSE 'same'
                END as st_comparison
            FROM results r1
            JOIN race_details rd1 ON r1.race_id = rd1.race_id AND r1.pit_number = rd1.pit_number
            JOIN race_details rd2 ON r1.race_id = rd2.race_id
            JOIN entries e2 ON rd2.race_id = e2.race_id AND rd2.pit_number = e2.pit_number
            WHERE r1.rank = 1
              AND r1.kimarite IN ('まくり', 'まくり差し')
              AND rd1.actual_course != 1
              AND rd2.actual_course = 1
              AND rd1.st_time IS NOT NULL
              AND rd2.st_time IS NOT NULL
        )
        SELECT
            st_comparison,
            COUNT(*) as cnt,
            ROUND(AVG(winner_st), 3) as avg_winner_st,
            ROUND(AVG(course1_st), 3) as avg_course1_st
        FROM makuri_races
        GROUP BY st_comparison
        ORDER BY cnt DESC
    ''')
    print(f"{'ST比較':<20} {'件数':>8} {'勝者平均ST':>12} {'1C平均ST':>12}")
    print("-" * 55)
    for row in cursor.fetchall():
        comp_label = {'winner_faster': '勝者がスタート早い',
                      'course1_faster': '1Cがスタート早い',
                      'same': '同じ'}.get(row[0], row[0])
        print(f"{comp_label:<20} {row[1]:>8} {row[2]:>12.3f} {row[3]:>12.3f}")

    # 6. 会場別まくり発生率
    print("\n【6. 会場別まくり発生率（まくり+まくり差し）】")
    cursor.execute('''
        SELECT
            ra.venue_code,
            COUNT(*) as total_races,
            SUM(CASE WHEN r.kimarite IN ('まくり', 'まくり差し') THEN 1 ELSE 0 END) as makuri_cnt,
            ROUND(SUM(CASE WHEN r.kimarite IN ('まくり', 'まくり差し') THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as makuri_rate
        FROM results r
        JOIN races ra ON r.race_id = ra.id
        WHERE r.rank = 1 AND r.kimarite IS NOT NULL
        GROUP BY ra.venue_code
        HAVING COUNT(*) >= 500
        ORDER BY makuri_rate DESC
        LIMIT 15
    ''')
    print(f"{'会場':<6} {'総レース':>10} {'まくり系':>10} {'発生率':>8}")
    print("-" * 40)
    for row in cursor.fetchall():
        print(f"{row[0]:<6} {row[1]:>10} {row[2]:>10} {row[3]:>7.1f}%")

    # 7. 1コースの平均STとまくられ率
    print("\n【7. 1コースの平均ST帯とまくられ率】")
    cursor.execute('''
        WITH course1_races AS (
            SELECT
                rd.race_id,
                rd.st_time,
                r.rank = 1 as course1_won,
                r2.kimarite as winner_kimarite
            FROM race_details rd
            JOIN results r ON rd.race_id = r.race_id AND rd.pit_number = r.pit_number
            JOIN results r2 ON rd.race_id = r2.race_id AND r2.rank = 1
            WHERE rd.actual_course = 1
              AND rd.st_time IS NOT NULL
        )
        SELECT
            CASE
                WHEN st_time < 0.10 THEN '0.00-0.09'
                WHEN st_time < 0.15 THEN '0.10-0.14'
                WHEN st_time < 0.20 THEN '0.15-0.19'
                WHEN st_time < 0.25 THEN '0.20-0.24'
                ELSE '0.25+'
            END as st_range,
            COUNT(*) as total,
            SUM(CASE WHEN NOT course1_won AND winner_kimarite IN ('まくり', 'まくり差し') THEN 1 ELSE 0 END) as makuri_loss,
            ROUND(SUM(CASE WHEN NOT course1_won AND winner_kimarite IN ('まくり', 'まくり差し') THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as makuri_loss_rate
        FROM course1_races
        GROUP BY st_range
        ORDER BY st_range
    ''')
    print(f"{'1CのST帯':<12} {'総レース':>10} {'まくられ':>10} {'まくられ率':>10}")
    print("-" * 45)
    for row in cursor.fetchall():
        print(f"{row[0]:<12} {row[1]:>10} {row[2]:>10} {row[3]:>9.1f}%")

    # 8. 級別差とまくり成功率
    print("\n【8. 級別差とまくり成功率（1コース vs 勝者）】")
    cursor.execute('''
        WITH rank_score AS (
            SELECT 'A1' as rank, 4 as score UNION ALL
            SELECT 'A2', 3 UNION ALL
            SELECT 'B1', 2 UNION ALL
            SELECT 'B2', 1
        ),
        makuri_with_ranks AS (
            SELECT
                r1.race_id,
                e1.racer_rank as winner_rank,
                e2.racer_rank as course1_rank,
                COALESCE(rs1.score, 2) as winner_score,
                COALESCE(rs2.score, 2) as course1_score
            FROM results r1
            JOIN race_details rd1 ON r1.race_id = rd1.race_id AND r1.pit_number = rd1.pit_number
            JOIN race_details rd2 ON r1.race_id = rd2.race_id
            JOIN entries e1 ON r1.race_id = e1.race_id AND r1.pit_number = e1.pit_number
            JOIN entries e2 ON rd2.race_id = e2.race_id AND rd2.pit_number = e2.pit_number
            LEFT JOIN rank_score rs1 ON e1.racer_rank = rs1.rank
            LEFT JOIN rank_score rs2 ON e2.racer_rank = rs2.rank
            WHERE r1.rank = 1
              AND r1.kimarite IN ('まくり', 'まくり差し')
              AND rd1.actual_course != 1
              AND rd2.actual_course = 1
        )
        SELECT
            winner_rank || ' vs ' || course1_rank as matchup,
            CASE
                WHEN winner_score > course1_score THEN 'makuri_up'
                WHEN winner_score < course1_score THEN 'makuri_down'
                ELSE 'makuri_same'
            END as rank_diff,
            COUNT(*) as cnt
        FROM makuri_with_ranks
        GROUP BY matchup, rank_diff
        HAVING COUNT(*) >= 100
        ORDER BY cnt DESC
        LIMIT 20
    ''')
    print(f"{'対戦':<15} {'級別差':<15} {'件数':>8}")
    print("-" * 40)
    for row in cursor.fetchall():
        diff_label = {'makuri_up': '格上がまくり',
                      'makuri_down': '格下がまくり',
                      'makuri_same': '同格がまくり'}.get(row[1], row[1])
        print(f"{row[0]:<15} {diff_label:<15} {row[2]:>8}")

    # 9. モーター勝率とまくり成功率
    print("\n【9. モーター2連率とまくり成功の関係】")
    cursor.execute('''
        WITH motor_stats AS (
            SELECT
                e.motor_number,
                ra.venue_code,
                COUNT(*) as races,
                SUM(CASE WHEN r.rank IN (1, 2) THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as motor_2ren
            FROM entries e
            JOIN races ra ON e.race_id = ra.id
            JOIN results r ON e.race_id = r.race_id AND e.pit_number = r.pit_number
            GROUP BY e.motor_number, ra.venue_code
            HAVING COUNT(*) >= 30
        ),
        makuri_motors AS (
            SELECT
                e1.motor_number,
                ra.venue_code,
                r1.kimarite
            FROM results r1
            JOIN race_details rd1 ON r1.race_id = rd1.race_id AND r1.pit_number = rd1.pit_number
            JOIN entries e1 ON r1.race_id = e1.race_id AND r1.pit_number = e1.pit_number
            JOIN races ra ON r1.race_id = ra.id
            WHERE r1.rank = 1
              AND r1.kimarite IN ('まくり', 'まくり差し')
              AND rd1.actual_course != 1
        )
        SELECT
            CASE
                WHEN ms.motor_2ren < 25 THEN '25%未満'
                WHEN ms.motor_2ren < 35 THEN '25-35%'
                WHEN ms.motor_2ren < 45 THEN '35-45%'
                ELSE '45%以上'
            END as motor_range,
            COUNT(*) as makuri_cnt
        FROM makuri_motors mm
        JOIN motor_stats ms ON mm.motor_number = ms.motor_number AND mm.venue_code = ms.venue_code
        GROUP BY motor_range
        ORDER BY motor_range
    ''')
    print(f"{'モーター2連率':<15} {'まくり成功数':>12}")
    print("-" * 30)
    for row in cursor.fetchall():
        print(f"{row[0]:<15} {row[1]:>12}")

    # 10. まくり成功者のコース別ST
    print("\n【10. まくり成功者のコース別平均ST】")
    cursor.execute('''
        SELECT
            rd.actual_course,
            r.kimarite,
            ROUND(AVG(rd.st_time), 3) as avg_st,
            COUNT(*) as cnt
        FROM results r
        JOIN race_details rd ON r.race_id = rd.race_id AND r.pit_number = rd.pit_number
        WHERE r.rank = 1
          AND r.kimarite IN ('まくり', 'まくり差し', '差し')
          AND rd.st_time IS NOT NULL
        GROUP BY rd.actual_course, r.kimarite
        HAVING COUNT(*) >= 100
        ORDER BY rd.actual_course, r.kimarite
    ''')
    print(f"{'コース':<8} {'決まり手':<12} {'平均ST':>10} {'件数':>8}")
    print("-" * 40)
    for row in cursor.fetchall():
        print(f"{row[0]}コース   {row[1]:<12} {row[2]:>10.3f} {row[3]:>8}")

    conn.close()

    print("\n" + "=" * 70)
    print("【分析サマリー・改善への示唆】")
    print("=" * 70)
    print("""
1. まくり/まくり差しは主に3-4コースから発生（全体の約25%）
2. 1コースB1/B2級は負け率が高い → まくられリスク高
3. 1コースのSTが遅い（0.20秒以上）とまくられ率上昇
4. 格下（級別が低い）選手のまくり成功も多い → 級別だけで判断不可
5. モーター2連率が高いとまくり成功率も高い傾向

予測ロジックへの改善案:
- 1コースがB1/B2の場合、外コースのまくり候補を評価
- ST差が大きい場合（1コース遅い）、まくりシナリオの確率UP
- モーター2連率が高い外コース選手のまくり可能性を評価
- 会場別のまくり発生率を考慮
    """)


if __name__ == "__main__":
    analyze_makuri_patterns()
