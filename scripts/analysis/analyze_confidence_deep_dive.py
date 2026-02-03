# -*- coding: utf-8 -*-
"""
信頼度分析の深掘り検証

発見1: A×50倍+ の年度別安定性
発見2: B×A1の改善可能性
発見4: 的中vs不的中の特徴差の意味
発見5: 高ROI条件の実用性
"""

import sqlite3
import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH


def analyze_a_high_odds_yearly():
    """発見1: A×50倍+ の年度別安定性検証"""
    print("=" * 70)
    print("【発見1検証】A×50倍+ 年度別安定性")
    print("=" * 70)
    print("全体: 427件, ROI 203.0% → 採用候補")
    print()

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 年度別検証
    query = """
    WITH prediction_combos AS (
        SELECT
            rp1.race_id,
            rp1.confidence,
            CAST(rp1.pit_number AS TEXT) || '-' ||
            CAST(rp2.pit_number AS TEXT) || '-' ||
            CAST(rp3.pit_number AS TEXT) as pred_combo
        FROM race_predictions rp1
        JOIN race_predictions rp2 ON rp1.race_id = rp2.race_id
            AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON rp1.race_id = rp3.race_id
            AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN races rc ON rp1.race_id = rc.id
        WHERE rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
          AND rp1.confidence = 'A'
          AND rc.race_date BETWEEN '2020-01-01' AND '2025-12-31'
    ),
    actual_combos AS (
        SELECT
            race_id,
            CAST(MAX(CASE WHEN rank = '1' THEN pit_number END) AS TEXT) || '-' ||
            CAST(MAX(CASE WHEN rank = '2' THEN pit_number END) AS TEXT) || '-' ||
            CAST(MAX(CASE WHEN rank = '3' THEN pit_number END) AS TEXT) as actual_combo
        FROM results
        WHERE rank IN ('1', '2', '3')
        GROUP BY race_id
    )
    SELECT
        strftime('%Y', rc.race_date) as year,
        COUNT(*) as total,
        SUM(CASE WHEN pc.pred_combo = ac.actual_combo THEN 1 ELSE 0 END) as hits,
        ROUND(100.0 * SUM(CASE WHEN pc.pred_combo = ac.actual_combo THEN 1 ELSE 0 END) / COUNT(*), 2) as hit_rate,
        ROUND(AVG(t.odds), 1) as avg_odds,
        SUM(t.odds * 100) as potential_return,
        COUNT(*) * 100 as investment,
        SUM(CASE WHEN pc.pred_combo = ac.actual_combo THEN t.odds * 100 ELSE 0 END) as actual_return
    FROM prediction_combos pc
    JOIN races rc ON pc.race_id = rc.id
    JOIN trifecta_odds t ON pc.race_id = t.race_id AND t.combination = pc.pred_combo
    JOIN actual_combos ac ON pc.race_id = ac.race_id
    WHERE t.odds >= 50 AND t.odds < 100
    GROUP BY year
    ORDER BY year
    """

    cursor.execute(query)
    rows = cursor.fetchall()

    print(f"{'年度':<6} {'件数':>6} {'的中':>4} {'的中率':>7} {'平均オッズ':>9} {'投資':>10} {'払戻':>12} {'収支':>12} {'ROI':>8} {'判定'}")
    print("-" * 100)

    total_investment = 0
    total_return = 0
    black_years = 0

    for row in rows:
        year, total, hits, hit_rate, avg_odds, _, investment, actual_return = row
        actual_return = actual_return or 0
        profit = actual_return - investment
        roi = actual_return / investment * 100 if investment > 0 else 0
        status = "○黒字" if profit > 0 else "×赤字"
        if profit > 0:
            black_years += 1

        total_investment += investment
        total_return += actual_return

        print(f"{year:<6} {total:>6} {hits:>4} {hit_rate:>6.2f}% {avg_odds:>9.1f} {investment:>10,} {actual_return:>12,.0f} {profit:>+12,.0f} {roi:>7.1f}% {status}")

    print("-" * 100)
    total_profit = total_return - total_investment
    total_roi = total_return / total_investment * 100 if total_investment > 0 else 0
    print(f"{'合計':<6} {'-':>6} {'-':>4} {'-':>7} {'-':>9} {total_investment:>10,} {total_return:>12,.0f} {total_profit:>+12,.0f} {total_roi:>7.1f}%")
    print(f"\n黒字年数: {black_years}/6年 → 採用基準{'○達成' if black_years >= 4 else '×未達'}")

    # 100倍以上も確認
    print("\n" + "-" * 70)
    print("【参考】A×100倍+ （サンプル少）")

    query2 = """
    WITH prediction_combos AS (
        SELECT
            rp1.race_id,
            rp1.confidence,
            CAST(rp1.pit_number AS TEXT) || '-' ||
            CAST(rp2.pit_number AS TEXT) || '-' ||
            CAST(rp3.pit_number AS TEXT) as pred_combo
        FROM race_predictions rp1
        JOIN race_predictions rp2 ON rp1.race_id = rp2.race_id
            AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON rp1.race_id = rp3.race_id
            AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN races rc ON rp1.race_id = rc.id
        WHERE rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
          AND rp1.confidence = 'A'
          AND rc.race_date BETWEEN '2020-01-01' AND '2025-12-31'
    ),
    actual_combos AS (
        SELECT
            race_id,
            CAST(MAX(CASE WHEN rank = '1' THEN pit_number END) AS TEXT) || '-' ||
            CAST(MAX(CASE WHEN rank = '2' THEN pit_number END) AS TEXT) || '-' ||
            CAST(MAX(CASE WHEN rank = '3' THEN pit_number END) AS TEXT) as actual_combo
        FROM results
        WHERE rank IN ('1', '2', '3')
        GROUP BY race_id
    )
    SELECT
        strftime('%Y', rc.race_date) as year,
        COUNT(*) as total,
        SUM(CASE WHEN pc.pred_combo = ac.actual_combo THEN 1 ELSE 0 END) as hits,
        SUM(CASE WHEN pc.pred_combo = ac.actual_combo THEN t.odds * 100 ELSE 0 END) - COUNT(*) * 100 as profit
    FROM prediction_combos pc
    JOIN races rc ON pc.race_id = rc.id
    JOIN trifecta_odds t ON pc.race_id = t.race_id AND t.combination = pc.pred_combo
    JOIN actual_combos ac ON pc.race_id = ac.race_id
    WHERE t.odds >= 100
    GROUP BY year
    ORDER BY year
    """

    cursor.execute(query2)
    rows2 = cursor.fetchall()

    for row in rows2:
        year, total, hits, profit = row
        profit = profit or 0
        status = "○" if profit > 0 else "×"
        print(f"  {year}: {total}件, 的中{hits}, 収支{profit:+,.0f}円 {status}")

    conn.close()


def analyze_b_a1_improvement():
    """発見2: B×A1の改善可能性"""
    print("\n" + "=" * 70)
    print("【発見2検証】B×A1 改善可能性探索")
    print("=" * 70)
    print("現状: B×A1 ROI 97.7%（惜しい赤字）")
    print("目標: 追加フィルターでROI 100%+に改善")
    print()

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # オッズ帯別で分解
    print("【オッズ帯別】")
    query = """
    WITH prediction_combos AS (
        SELECT
            rp1.race_id,
            rp1.confidence,
            CAST(rp1.pit_number AS TEXT) || '-' ||
            CAST(rp2.pit_number AS TEXT) || '-' ||
            CAST(rp3.pit_number AS TEXT) as pred_combo
        FROM race_predictions rp1
        JOIN race_predictions rp2 ON rp1.race_id = rp2.race_id
            AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON rp1.race_id = rp3.race_id
            AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN races rc ON rp1.race_id = rc.id
        JOIN entries e1 ON rp1.race_id = e1.race_id AND e1.pit_number = 1
        WHERE rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
          AND rp1.confidence = 'B'
          AND e1.racer_rank = 'A1'
          AND rc.race_date BETWEEN '2020-01-01' AND '2025-12-31'
    ),
    actual_combos AS (
        SELECT
            race_id,
            CAST(MAX(CASE WHEN rank = '1' THEN pit_number END) AS TEXT) || '-' ||
            CAST(MAX(CASE WHEN rank = '2' THEN pit_number END) AS TEXT) || '-' ||
            CAST(MAX(CASE WHEN rank = '3' THEN pit_number END) AS TEXT) as actual_combo
        FROM results
        WHERE rank IN ('1', '2', '3')
        GROUP BY race_id
    )
    SELECT
        CASE
            WHEN t.odds < 10 THEN '01: <10倍'
            WHEN t.odds < 15 THEN '02: 10-15倍'
            WHEN t.odds < 20 THEN '03: 15-20倍'
            WHEN t.odds < 30 THEN '04: 20-30倍'
            WHEN t.odds < 50 THEN '05: 30-50倍'
            ELSE '06: 50倍+'
        END as odds_band,
        COUNT(*) as total,
        SUM(CASE WHEN pc.pred_combo = ac.actual_combo THEN 1 ELSE 0 END) as hits,
        ROUND(AVG(t.odds), 1) as avg_odds,
        SUM(CASE WHEN pc.pred_combo = ac.actual_combo THEN t.odds * 100 ELSE 0 END) as returns,
        COUNT(*) * 100 as investment
    FROM prediction_combos pc
    JOIN trifecta_odds t ON pc.race_id = t.race_id AND t.combination = pc.pred_combo
    JOIN actual_combos ac ON pc.race_id = ac.race_id
    GROUP BY odds_band
    ORDER BY odds_band
    """

    cursor.execute(query)
    rows = cursor.fetchall()

    print(f"{'オッズ帯':<12} {'件数':>6} {'的中':>4} {'平均オッズ':>9} {'ROI':>8} {'収支':>12}")
    print("-" * 60)

    for row in rows:
        odds_band, total, hits, avg_odds, returns, investment = row
        returns = returns or 0
        roi = returns / investment * 100 if investment > 0 else 0
        profit = returns - investment
        mark = "★" if roi >= 100 else " "
        print(f"{odds_band:<12} {total:>6} {hits:>4} {avg_odds:>9.1f} {roi:>7.1f}%{mark} {profit:>+12,.0f}")

    # 会場別で分解
    print("\n【会場別（上位10）】")
    query2 = """
    WITH prediction_combos AS (
        SELECT
            rp1.race_id,
            rp1.confidence,
            CAST(rp1.pit_number AS TEXT) || '-' ||
            CAST(rp2.pit_number AS TEXT) || '-' ||
            CAST(rp3.pit_number AS TEXT) as pred_combo
        FROM race_predictions rp1
        JOIN race_predictions rp2 ON rp1.race_id = rp2.race_id
            AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON rp1.race_id = rp3.race_id
            AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN races rc ON rp1.race_id = rc.id
        JOIN entries e1 ON rp1.race_id = e1.race_id AND e1.pit_number = 1
        WHERE rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
          AND rp1.confidence = 'B'
          AND e1.racer_rank = 'A1'
          AND rc.race_date BETWEEN '2020-01-01' AND '2025-12-31'
    ),
    actual_combos AS (
        SELECT
            race_id,
            CAST(MAX(CASE WHEN rank = '1' THEN pit_number END) AS TEXT) || '-' ||
            CAST(MAX(CASE WHEN rank = '2' THEN pit_number END) AS TEXT) || '-' ||
            CAST(MAX(CASE WHEN rank = '3' THEN pit_number END) AS TEXT) as actual_combo
        FROM results
        WHERE rank IN ('1', '2', '3')
        GROUP BY race_id
    )
    SELECT
        rc.venue_code,
        COUNT(*) as total,
        SUM(CASE WHEN pc.pred_combo = ac.actual_combo THEN 1 ELSE 0 END) as hits,
        SUM(CASE WHEN pc.pred_combo = ac.actual_combo THEN t.odds * 100 ELSE 0 END) as returns,
        COUNT(*) * 100 as investment
    FROM prediction_combos pc
    JOIN races rc ON pc.race_id = rc.id
    JOIN trifecta_odds t ON pc.race_id = t.race_id AND t.combination = pc.pred_combo
    JOIN actual_combos ac ON pc.race_id = ac.race_id
    GROUP BY rc.venue_code
    HAVING COUNT(*) >= 30
    ORDER BY (SUM(CASE WHEN pc.pred_combo = ac.actual_combo THEN t.odds * 100 ELSE 0 END) * 1.0 / (COUNT(*) * 100)) DESC
    LIMIT 10
    """

    venue_names = {
        1: '桐生', 2: '戸田', 3: '江戸川', 4: '平和島', 5: '多摩川', 6: '浜名湖',
        7: '蒲郡', 8: '常滑', 9: '津', 10: '三国', 11: '琵琶湖', 12: '住之江',
        13: '尼崎', 14: '鳴門', 15: '丸亀', 16: '児島', 17: '宮島', 18: '徳山',
        19: '下関', 20: '若松', 21: '芦屋', 22: '福岡', 23: '唐津', 24: '大村'
    }

    cursor.execute(query2)
    rows2 = cursor.fetchall()

    print(f"{'会場':<10} {'件数':>6} {'的中':>4} {'ROI':>8} {'収支':>12}")
    print("-" * 50)

    black_venues = []
    for row in rows2:
        venue_code, total, hits, returns, investment = row
        returns = returns or 0
        roi = returns / investment * 100 if investment > 0 else 0
        profit = returns - investment
        venue_name = venue_names.get(venue_code, str(venue_code))
        mark = "★" if roi >= 100 else " "
        print(f"{venue_name:<10} {total:>6} {hits:>4} {roi:>7.1f}%{mark} {profit:>+12,.0f}")
        if roi >= 100:
            black_venues.append(venue_code)

    print(f"\n黒字会場: {black_venues}")

    # 黒字会場での年度別検証
    if black_venues:
        print("\n【黒字会場限定での年度別】")
        venues_str = ','.join(map(str, black_venues))
        query3 = f"""
        WITH prediction_combos AS (
            SELECT
                rp1.race_id,
                rp1.confidence,
                CAST(rp1.pit_number AS TEXT) || '-' ||
                CAST(rp2.pit_number AS TEXT) || '-' ||
                CAST(rp3.pit_number AS TEXT) as pred_combo
            FROM race_predictions rp1
            JOIN race_predictions rp2 ON rp1.race_id = rp2.race_id
                AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
            JOIN race_predictions rp3 ON rp1.race_id = rp3.race_id
                AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
            JOIN races rc ON rp1.race_id = rc.id
            JOIN entries e1 ON rp1.race_id = e1.race_id AND e1.pit_number = 1
            WHERE rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
              AND rp1.confidence = 'B'
              AND e1.racer_rank = 'A1'
              AND rc.venue_code IN ({venues_str})
              AND rc.race_date BETWEEN '2020-01-01' AND '2025-12-31'
        ),
        actual_combos AS (
            SELECT
                race_id,
                CAST(MAX(CASE WHEN rank = '1' THEN pit_number END) AS TEXT) || '-' ||
                CAST(MAX(CASE WHEN rank = '2' THEN pit_number END) AS TEXT) || '-' ||
                CAST(MAX(CASE WHEN rank = '3' THEN pit_number END) AS TEXT) as actual_combo
            FROM results
            WHERE rank IN ('1', '2', '3')
            GROUP BY race_id
        )
        SELECT
            strftime('%Y', rc.race_date) as year,
            COUNT(*) as total,
            SUM(CASE WHEN pc.pred_combo = ac.actual_combo THEN 1 ELSE 0 END) as hits,
            SUM(CASE WHEN pc.pred_combo = ac.actual_combo THEN t.odds * 100 ELSE 0 END) - COUNT(*) * 100 as profit
        FROM prediction_combos pc
        JOIN races rc ON pc.race_id = rc.id
        JOIN trifecta_odds t ON pc.race_id = t.race_id AND t.combination = pc.pred_combo
        JOIN actual_combos ac ON pc.race_id = ac.race_id
        GROUP BY year
        ORDER BY year
        """

        cursor.execute(query3)
        rows3 = cursor.fetchall()

        black_years = 0
        for row in rows3:
            year, total, hits, profit = row
            profit = profit or 0
            status = "○" if profit > 0 else "×"
            if profit > 0:
                black_years += 1
            print(f"  {year}: {total}件, 的中{hits}, 収支{profit:+,.0f}円 {status}")

        print(f"\n黒字年数: {black_years}/6年 → 採用基準{'○達成' if black_years >= 4 else '×未達'}")

    conn.close()


def explain_hit_vs_miss():
    """発見4: 的中vs不的中の特徴差の意味を解説"""
    print("\n" + "=" * 70)
    print("【発見4解説】的中vs不的中の特徴差の意味")
    print("=" * 70)

    print("""
■ 分析結果の意味

【信頼度A】
  ・的中時:   平均オッズ 9.4倍,  1C2連率 43.6%
  ・不的中時: 平均オッズ 14.6倍, 1C2連率 42.4%

【信頼度D】
  ・的中時:   平均オッズ 11.3倍, 1C2連率 41.3%
  ・不的中時: 平均オッズ 23.1倍, 1C2連率 32.6%

■ 解釈

1. オッズの差:
   - 的中時は「低オッズ」= 市場も本命と予想 = 順当な結果
   - 不的中時は「高オッズ」= 市場は穴を予想 = 荒れた結果
   → 「市場と予想が一致すると当たりやすい」は当然の結果

2. 1C2連率の差:
   - 的中時は1コース選手の2連率が高い = 実力者
   - 不的中時は2連率が低い = 力量不足
   → 「1コース選手の2連率」が的中の鍵

■ 実用的な示唆

【D条件で特に顕著】
  - 的中時と不的中時で1C2連率が8.7ptも違う（41.3% vs 32.6%）
  - D条件で「1C2連率40%以上」フィルターが有効かもしれない

■ 検証してみましょう
""")

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # D条件で1C2連率フィルターの効果検証
    print("【D条件 × 1C2連率フィルター効果】")

    query = """
    WITH prediction_combos AS (
        SELECT
            rp1.race_id,
            rp1.confidence,
            CAST(rp1.pit_number AS TEXT) || '-' ||
            CAST(rp2.pit_number AS TEXT) || '-' ||
            CAST(rp3.pit_number AS TEXT) as pred_combo
        FROM race_predictions rp1
        JOIN race_predictions rp2 ON rp1.race_id = rp2.race_id
            AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON rp1.race_id = rp3.race_id
            AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN races rc ON rp1.race_id = rc.id
        WHERE rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
          AND rp1.confidence = 'D'
          AND rc.race_date BETWEEN '2020-01-01' AND '2025-12-31'
    ),
    actual_combos AS (
        SELECT
            race_id,
            CAST(MAX(CASE WHEN rank = '1' THEN pit_number END) AS TEXT) || '-' ||
            CAST(MAX(CASE WHEN rank = '2' THEN pit_number END) AS TEXT) || '-' ||
            CAST(MAX(CASE WHEN rank = '3' THEN pit_number END) AS TEXT) as actual_combo
        FROM results
        WHERE rank IN ('1', '2', '3')
        GROUP BY race_id
    )
    SELECT
        CASE
            WHEN e1.second_rate >= 40 THEN '40%以上'
            WHEN e1.second_rate >= 30 THEN '30-40%'
            WHEN e1.second_rate >= 20 THEN '20-30%'
            ELSE '20%未満'
        END as rate_band,
        COUNT(*) as total,
        SUM(CASE WHEN pc.pred_combo = ac.actual_combo THEN 1 ELSE 0 END) as hits,
        ROUND(AVG(t.odds), 1) as avg_odds,
        SUM(CASE WHEN pc.pred_combo = ac.actual_combo THEN t.odds * 100 ELSE 0 END) as returns,
        COUNT(*) * 100 as investment
    FROM prediction_combos pc
    JOIN entries e1 ON pc.race_id = e1.race_id AND e1.pit_number = 1
    JOIN trifecta_odds t ON pc.race_id = t.race_id AND t.combination = pc.pred_combo
    JOIN actual_combos ac ON pc.race_id = ac.race_id
    GROUP BY rate_band
    ORDER BY rate_band DESC
    """

    cursor.execute(query)
    rows = cursor.fetchall()

    print(f"{'1C2連率帯':<10} {'件数':>6} {'的中':>4} {'平均オッズ':>9} {'ROI':>8} {'収支':>12}")
    print("-" * 55)

    for row in rows:
        rate_band, total, hits, avg_odds, returns, investment = row
        returns = returns or 0
        roi = returns / investment * 100 if investment > 0 else 0
        profit = returns - investment
        mark = "★" if roi >= 100 else " "
        print(f"{rate_band:<10} {total:>6} {hits:>4} {avg_odds:>9.1f} {roi:>7.1f}%{mark} {profit:>+12,.0f}")

    conn.close()


def analyze_high_roi_conditions():
    """発見5: 高ROI条件の実用性検証"""
    print("\n" + "=" * 70)
    print("【発見5検証】高ROI条件の実用性")
    print("=" * 70)
    print("TOP: A×A2×高オッズ×低勝率 → ROI 296.1%")
    print()

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # A×A2×高オッズの詳細
    print("【A×A2×50倍+ 年度別検証】")

    query = """
    WITH prediction_combos AS (
        SELECT
            rp1.race_id,
            rp1.confidence,
            CAST(rp1.pit_number AS TEXT) || '-' ||
            CAST(rp2.pit_number AS TEXT) || '-' ||
            CAST(rp3.pit_number AS TEXT) as pred_combo
        FROM race_predictions rp1
        JOIN race_predictions rp2 ON rp1.race_id = rp2.race_id
            AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON rp1.race_id = rp3.race_id
            AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN races rc ON rp1.race_id = rc.id
        JOIN entries e1 ON rp1.race_id = e1.race_id AND e1.pit_number = 1
        WHERE rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
          AND rp1.confidence = 'A'
          AND e1.racer_rank = 'A2'
          AND rc.race_date BETWEEN '2020-01-01' AND '2025-12-31'
    ),
    actual_combos AS (
        SELECT
            race_id,
            CAST(MAX(CASE WHEN rank = '1' THEN pit_number END) AS TEXT) || '-' ||
            CAST(MAX(CASE WHEN rank = '2' THEN pit_number END) AS TEXT) || '-' ||
            CAST(MAX(CASE WHEN rank = '3' THEN pit_number END) AS TEXT) as actual_combo
        FROM results
        WHERE rank IN ('1', '2', '3')
        GROUP BY race_id
    )
    SELECT
        strftime('%Y', rc.race_date) as year,
        COUNT(*) as total,
        SUM(CASE WHEN pc.pred_combo = ac.actual_combo THEN 1 ELSE 0 END) as hits,
        SUM(CASE WHEN pc.pred_combo = ac.actual_combo THEN t.odds * 100 ELSE 0 END) - COUNT(*) * 100 as profit,
        ROUND(100.0 * SUM(CASE WHEN pc.pred_combo = ac.actual_combo THEN t.odds * 100 ELSE 0 END) / (COUNT(*) * 100), 1) as roi
    FROM prediction_combos pc
    JOIN races rc ON pc.race_id = rc.id
    JOIN trifecta_odds t ON pc.race_id = t.race_id AND t.combination = pc.pred_combo
    JOIN actual_combos ac ON pc.race_id = ac.race_id
    WHERE t.odds >= 50
    GROUP BY year
    ORDER BY year
    """

    cursor.execute(query)
    rows = cursor.fetchall()

    black_years = 0
    total_profit = 0
    print(f"{'年度':<6} {'件数':>6} {'的中':>4} {'ROI':>8} {'収支':>12} {'判定'}")
    print("-" * 50)

    for row in rows:
        year, total, hits, profit, roi = row
        profit = profit or 0
        roi = roi or 0
        total_profit += profit
        status = "○黒字" if profit > 0 else "×赤字"
        if profit > 0:
            black_years += 1
        print(f"{year:<6} {total:>6} {hits:>4} {roi:>7.1f}% {profit:>+12,.0f} {status}")

    print("-" * 50)
    print(f"黒字年数: {black_years}/6年, 累計収支: {total_profit:+,.0f}円")
    print(f"\n→ 採用基準{'○達成' if black_years >= 4 else '×未達'}")

    # A×A1×高オッズも確認
    print("\n【A×A1×50倍+ 年度別検証】")

    query2 = """
    WITH prediction_combos AS (
        SELECT
            rp1.race_id,
            rp1.confidence,
            CAST(rp1.pit_number AS TEXT) || '-' ||
            CAST(rp2.pit_number AS TEXT) || '-' ||
            CAST(rp3.pit_number AS TEXT) as pred_combo
        FROM race_predictions rp1
        JOIN race_predictions rp2 ON rp1.race_id = rp2.race_id
            AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON rp1.race_id = rp3.race_id
            AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN races rc ON rp1.race_id = rc.id
        JOIN entries e1 ON rp1.race_id = e1.race_id AND e1.pit_number = 1
        WHERE rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
          AND rp1.confidence = 'A'
          AND e1.racer_rank = 'A1'
          AND rc.race_date BETWEEN '2020-01-01' AND '2025-12-31'
    ),
    actual_combos AS (
        SELECT
            race_id,
            CAST(MAX(CASE WHEN rank = '1' THEN pit_number END) AS TEXT) || '-' ||
            CAST(MAX(CASE WHEN rank = '2' THEN pit_number END) AS TEXT) || '-' ||
            CAST(MAX(CASE WHEN rank = '3' THEN pit_number END) AS TEXT) as actual_combo
        FROM results
        WHERE rank IN ('1', '2', '3')
        GROUP BY race_id
    )
    SELECT
        strftime('%Y', rc.race_date) as year,
        COUNT(*) as total,
        SUM(CASE WHEN pc.pred_combo = ac.actual_combo THEN 1 ELSE 0 END) as hits,
        SUM(CASE WHEN pc.pred_combo = ac.actual_combo THEN t.odds * 100 ELSE 0 END) - COUNT(*) * 100 as profit,
        ROUND(100.0 * SUM(CASE WHEN pc.pred_combo = ac.actual_combo THEN t.odds * 100 ELSE 0 END) / (COUNT(*) * 100), 1) as roi
    FROM prediction_combos pc
    JOIN races rc ON pc.race_id = rc.id
    JOIN trifecta_odds t ON pc.race_id = t.race_id AND t.combination = pc.pred_combo
    JOIN actual_combos ac ON pc.race_id = ac.race_id
    WHERE t.odds >= 50
    GROUP BY year
    ORDER BY year
    """

    cursor.execute(query2)
    rows2 = cursor.fetchall()

    black_years2 = 0
    total_profit2 = 0
    print(f"{'年度':<6} {'件数':>6} {'的中':>4} {'ROI':>8} {'収支':>12} {'判定'}")
    print("-" * 50)

    for row in rows2:
        year, total, hits, profit, roi = row
        profit = profit or 0
        roi = roi or 0
        total_profit2 += profit
        status = "○黒字" if profit > 0 else "×赤字"
        if profit > 0:
            black_years2 += 1
        print(f"{year:<6} {total:>6} {hits:>4} {roi:>7.1f}% {profit:>+12,.0f} {status}")

    print("-" * 50)
    print(f"黒字年数: {black_years2}/6年, 累計収支: {total_profit2:+,.0f}円")
    print(f"\n→ 採用基準{'○達成' if black_years2 >= 4 else '×未達'}")

    # A×(A1+A2)×50倍+合計
    print("\n【A×(A1+A2)×50倍+ 合算】")
    query3 = """
    WITH prediction_combos AS (
        SELECT
            rp1.race_id,
            rp1.confidence,
            CAST(rp1.pit_number AS TEXT) || '-' ||
            CAST(rp2.pit_number AS TEXT) || '-' ||
            CAST(rp3.pit_number AS TEXT) as pred_combo
        FROM race_predictions rp1
        JOIN race_predictions rp2 ON rp1.race_id = rp2.race_id
            AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON rp1.race_id = rp3.race_id
            AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN races rc ON rp1.race_id = rc.id
        JOIN entries e1 ON rp1.race_id = e1.race_id AND e1.pit_number = 1
        WHERE rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
          AND rp1.confidence = 'A'
          AND e1.racer_rank IN ('A1', 'A2')
          AND rc.race_date BETWEEN '2020-01-01' AND '2025-12-31'
    ),
    actual_combos AS (
        SELECT
            race_id,
            CAST(MAX(CASE WHEN rank = '1' THEN pit_number END) AS TEXT) || '-' ||
            CAST(MAX(CASE WHEN rank = '2' THEN pit_number END) AS TEXT) || '-' ||
            CAST(MAX(CASE WHEN rank = '3' THEN pit_number END) AS TEXT) as actual_combo
        FROM results
        WHERE rank IN ('1', '2', '3')
        GROUP BY race_id
    )
    SELECT
        strftime('%Y', rc.race_date) as year,
        COUNT(*) as total,
        SUM(CASE WHEN pc.pred_combo = ac.actual_combo THEN 1 ELSE 0 END) as hits,
        SUM(CASE WHEN pc.pred_combo = ac.actual_combo THEN t.odds * 100 ELSE 0 END) - COUNT(*) * 100 as profit,
        ROUND(100.0 * SUM(CASE WHEN pc.pred_combo = ac.actual_combo THEN t.odds * 100 ELSE 0 END) / (COUNT(*) * 100), 1) as roi
    FROM prediction_combos pc
    JOIN races rc ON pc.race_id = rc.id
    JOIN trifecta_odds t ON pc.race_id = t.race_id AND t.combination = pc.pred_combo
    JOIN actual_combos ac ON pc.race_id = ac.race_id
    WHERE t.odds >= 50 AND t.odds < 100
    GROUP BY year
    ORDER BY year
    """

    cursor.execute(query3)
    rows3 = cursor.fetchall()

    black_years3 = 0
    total_profit3 = 0
    total_count = 0
    print(f"{'年度':<6} {'件数':>6} {'的中':>4} {'ROI':>8} {'収支':>12} {'判定'}")
    print("-" * 50)

    for row in rows3:
        year, total, hits, profit, roi = row
        profit = profit or 0
        roi = roi or 0
        total_profit3 += profit
        total_count += total
        status = "○黒字" if profit > 0 else "×赤字"
        if profit > 0:
            black_years3 += 1
        print(f"{year:<6} {total:>6} {hits:>4} {roi:>7.1f}% {profit:>+12,.0f} {status}")

    print("-" * 50)
    print(f"黒字年数: {black_years3}/6年, 累計収支: {total_profit3:+,.0f}円, 総件数: {total_count}件")
    print(f"\n→ 採用基準{'○達成' if black_years3 >= 4 else '×未達'}")

    conn.close()


def main():
    print("信頼度分析 深掘り検証")
    print("=" * 70)

    analyze_a_high_odds_yearly()
    analyze_b_a1_improvement()
    explain_hit_vs_miss()
    analyze_high_roi_conditions()

    print("\n" + "=" * 70)
    print("検証完了")
    print("=" * 70)


if __name__ == "__main__":
    main()
