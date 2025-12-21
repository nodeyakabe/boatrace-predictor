# -*- coding: utf-8 -*-
"""
フィーチャーフラグ年度別有効性検証（2022-2025年）

各フィーチャーフラグのON/OFF時の予測精度を年度別に比較
"""

import sys
import sqlite3
from pathlib import Path
from datetime import datetime

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

def main():
    db_path = ROOT_DIR / 'data' / 'boatrace.db'
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    print("=" * 70)
    print("Feature Flag Year-by-Year Validation (2022-2025)")
    print("=" * 70)
    print(f"Run time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # 年度別の基本精度を確認
    print("### 1. Year-by-Year Prediction Accuracy Summary")
    print("-" * 60)

    # resultsからランク別のpit_numberを取得
    cur.execute('''
        WITH actual_ranks AS (
            SELECT
                race_id,
                MAX(CASE WHEN rank = '1' THEN pit_number END) as actual_1st,
                MAX(CASE WHEN rank = '2' THEN pit_number END) as actual_2nd,
                MAX(CASE WHEN rank = '3' THEN pit_number END) as actual_3rd
            FROM results
            WHERE is_invalid = 0
            GROUP BY race_id
        ),
        predicted_ranks AS (
            SELECT
                race_id,
                MAX(CASE WHEN rank_prediction = 1 THEN pit_number END) as pred_1st,
                MAX(CASE WHEN rank_prediction = 2 THEN pit_number END) as pred_2nd,
                MAX(CASE WHEN rank_prediction = 3 THEN pit_number END) as pred_3rd
            FROM race_predictions
            WHERE prediction_type = 'advance'
            GROUP BY race_id
        )
        SELECT
            substr(r.race_date, 1, 4) as year,
            COUNT(DISTINCT r.id) as total_races,
            SUM(CASE WHEN pr.pred_1st = ar.actual_1st THEN 1 ELSE 0 END) as hit_1st,
            SUM(CASE WHEN pr.pred_1st = ar.actual_1st
                      AND pr.pred_2nd = ar.actual_2nd THEN 1 ELSE 0 END) as hit_2nd,
            SUM(CASE WHEN pr.pred_1st = ar.actual_1st
                      AND pr.pred_2nd = ar.actual_2nd
                      AND pr.pred_3rd = ar.actual_3rd THEN 1 ELSE 0 END) as hit_3rd
        FROM races r
        JOIN predicted_ranks pr ON r.id = pr.race_id
        JOIN actual_ranks ar ON r.id = ar.race_id
        WHERE r.race_date >= '2022-01-01' AND r.race_date <= '2025-12-31'
        GROUP BY substr(r.race_date, 1, 4)
        ORDER BY year
    ''')

    print(f"{'Year':<6} {'Races':>8} {'1st%':>8} {'1-2%':>8} {'1-2-3%':>8}")
    print("-" * 60)

    for row in cur.fetchall():
        year, total, hit1, hit2, hit3 = row
        if total and total > 0:
            pct1 = (hit1 / total * 100) if hit1 else 0
            pct2 = (hit2 / total * 100) if hit2 else 0
            pct3 = (hit3 / total * 100) if hit3 else 0
            print(f"{year:<6} {total:>8} {pct1:>7.1f}% {pct2:>7.1f}% {pct3:>7.1f}%")
        else:
            print(f"{year:<6} {'N/A':>8} {'N/A':>8} {'N/A':>8} {'N/A':>8}")

    print()

    # 信頼度別の年度別分析
    print("### 2. Confidence x Year 3-連単Hit Rate Matrix")
    print("-" * 70)

    cur.execute('''
        WITH actual_ranks AS (
            SELECT
                race_id,
                MAX(CASE WHEN rank = '1' THEN pit_number END) as actual_1st,
                MAX(CASE WHEN rank = '2' THEN pit_number END) as actual_2nd,
                MAX(CASE WHEN rank = '3' THEN pit_number END) as actual_3rd
            FROM results
            WHERE is_invalid = 0
            GROUP BY race_id
        ),
        predicted_ranks AS (
            SELECT
                race_id,
                MAX(CASE WHEN rank_prediction = 1 THEN pit_number END) as pred_1st,
                MAX(CASE WHEN rank_prediction = 2 THEN pit_number END) as pred_2nd,
                MAX(CASE WHEN rank_prediction = 3 THEN pit_number END) as pred_3rd,
                MAX(CASE WHEN rank_prediction = 1 THEN confidence END) as confidence
            FROM race_predictions
            WHERE prediction_type = 'advance'
            GROUP BY race_id
        )
        SELECT
            substr(r.race_date, 1, 4) as year,
            pr.confidence,
            COUNT(*) as cnt,
            SUM(CASE WHEN pr.pred_1st = ar.actual_1st
                      AND pr.pred_2nd = ar.actual_2nd
                      AND pr.pred_3rd = ar.actual_3rd THEN 1 ELSE 0 END) as hits
        FROM races r
        JOIN predicted_ranks pr ON r.id = pr.race_id
        JOIN actual_ranks ar ON r.id = ar.race_id
        WHERE r.race_date >= '2022-01-01' AND r.race_date <= '2025-12-31'
          AND pr.confidence IN ('A', 'B', 'C', 'D')
        GROUP BY substr(r.race_date, 1, 4), pr.confidence
        ORDER BY year, pr.confidence
    ''')

    results = cur.fetchall()

    # 年度×信頼度のマトリックス作成
    data = {}
    for year, conf, cnt, hits in results:
        if year not in data:
            data[year] = {}
        data[year][conf] = {'cnt': cnt, 'hits': hits, 'rate': (hits/cnt*100) if cnt > 0 else 0}

    print(f"{'Year':<6} ", end="")
    for conf in ['A', 'B', 'C', 'D']:
        print(f"{conf:>15}", end="")
    print()
    print("-" * 70)

    for year in sorted(data.keys()):
        print(f"{year:<6} ", end="")
        for conf in ['A', 'B', 'C', 'D']:
            if conf in data[year]:
                rate = data[year][conf]['rate']
                cnt = data[year][conf]['cnt']
                print(f"{rate:>5.1f}%({cnt:>5})", end="")
            else:
                print(f"{'N/A':>15}", end="")
        print()

    print()

    # 予測データのapplied_rulesからフィーチャー使用状況を分析
    print("### 3. Feature Flag Usage (applied_rules analysis)")
    print("-" * 80)

    cur.execute('''
        SELECT
            substr(r.race_date, 1, 4) as year,
            COUNT(*) as total,
            SUM(CASE WHEN rp.applied_rules LIKE '%pattern%' THEN 1 ELSE 0 END) as pattern,
            SUM(CASE WHEN rp.applied_rules LIKE '%negative%' THEN 1 ELSE 0 END) as negative,
            SUM(CASE WHEN rp.applied_rules LIKE '%entry%' THEN 1 ELSE 0 END) as entry_pred,
            SUM(CASE WHEN rp.applied_rules LIKE '%hierarchical%' THEN 1 ELSE 0 END) as hierarchical,
            SUM(CASE WHEN rp.applied_rules LIKE '%lightgbm%' THEN 1 ELSE 0 END) as lightgbm,
            SUM(CASE WHEN rp.applied_rules LIKE '%pairwise%' THEN 1 ELSE 0 END) as pairwise,
            SUM(CASE WHEN rp.applied_rules IS NULL OR rp.applied_rules = '' THEN 1 ELSE 0 END) as empty
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'advance'
        WHERE r.race_date >= '2022-01-01' AND r.race_date <= '2025-12-31'
        GROUP BY substr(r.race_date, 1, 4)
        ORDER BY year
    ''')

    print(f"{'Year':<6} {'Total':>10} {'Pattern':>8} {'Neg':>6} {'Entry':>6} {'Hier':>6} {'LGBM':>6} {'Pair':>6} {'Empty':>8}")
    print("-" * 80)

    for row in cur.fetchall():
        year, total, pattern, negative, entry, hier, lgbm, pairwise, empty = row
        print(f"{year:<6} {total:>10} {pattern:>8} {negative:>6} {entry:>6} {hier:>6} {lgbm:>6} {pairwise:>6} {empty:>8}")

    print()

    # 1コース勝率の年度別分析
    print("### 4. Course 1 Win Rate by Year")
    print("-" * 50)

    cur.execute('''
        SELECT
            substr(r.race_date, 1, 4) as year,
            COUNT(*) as total,
            SUM(CASE WHEN res.rank = '1' AND res.pit_number = 1 THEN 1 ELSE 0 END) as c1_wins
        FROM races r
        JOIN results res ON r.id = res.race_id
        WHERE r.race_date >= '2022-01-01' AND r.race_date <= '2025-12-31'
          AND res.is_invalid = 0
        GROUP BY substr(r.race_date, 1, 4)
        ORDER BY year
    ''')

    print(f"{'Year':<6} {'Total':>8} {'C1 Wins':>8} {'Rate':>8}")
    print("-" * 50)

    for row in cur.fetchall():
        year, total, wins = row
        # totalはresults数、レース数で割る必要あり
        pass

    # より正確な1コース勝率
    cur.execute('''
        WITH race_results AS (
            SELECT
                race_id,
                MAX(CASE WHEN rank = '1' THEN pit_number END) as winner
            FROM results
            WHERE is_invalid = 0
            GROUP BY race_id
        )
        SELECT
            substr(r.race_date, 1, 4) as year,
            COUNT(*) as total,
            SUM(CASE WHEN rr.winner = 1 THEN 1 ELSE 0 END) as c1_wins
        FROM races r
        JOIN race_results rr ON r.id = rr.race_id
        WHERE r.race_date >= '2022-01-01' AND r.race_date <= '2025-12-31'
        GROUP BY substr(r.race_date, 1, 4)
        ORDER BY year
    ''')

    print(f"{'Year':<6} {'Races':>8} {'C1 Wins':>8} {'Rate':>8}")
    print("-" * 50)

    for row in cur.fetchall():
        year, total, wins = row
        rate = wins / total * 100 if total > 0 else 0
        print(f"{year:<6} {total:>8} {wins:>8} {rate:>7.1f}%")

    print()

    # 年度別の信頼度分布
    print("### 5. Confidence Distribution by Year")
    print("-" * 60)

    cur.execute('''
        SELECT
            substr(r.race_date, 1, 4) as year,
            rp.confidence,
            COUNT(DISTINCT rp.race_id) as races
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id
        WHERE rp.prediction_type = 'advance'
          AND rp.rank_prediction = 1
          AND r.race_date >= '2022-01-01' AND r.race_date <= '2025-12-31'
        GROUP BY substr(r.race_date, 1, 4), rp.confidence
        ORDER BY year, rp.confidence
    ''')

    results = cur.fetchall()
    dist = {}
    for year, conf, races in results:
        if year not in dist:
            dist[year] = {}
        dist[year][conf] = races

    print(f"{'Year':<6} ", end="")
    for conf in ['A', 'B', 'C', 'D', 'E']:
        print(f"{conf:>10}", end="")
    print()
    print("-" * 60)

    for year in sorted(dist.keys()):
        print(f"{year:<6} ", end="")
        for conf in ['A', 'B', 'C', 'D', 'E']:
            cnt = dist[year].get(conf, 0)
            print(f"{cnt:>10}", end="")
        print()

    print()
    print("=" * 70)
    print("Verification Complete")
    print("=" * 70)

    conn.close()

if __name__ == '__main__':
    main()
