#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
A-1: A×A2失敗原因の深掘り調査

仮説:
- A2級選手はモーター依存度が高く、Motor40%+でオッズが下がる
- 会場フィルターとの相性が悪い
- オッズ帯（10-100）が広すぎる

調査内容:
1. A×A2×Motor40%+のオッズ分布
2. A×A2×Motor40%+の会場別ROI
3. A×A2×Motor40%+ × 狭いオッズ帯でのROI
"""
import sqlite3
import sys
import io
import os

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH


def analyze_odds_distribution(cursor):
    """A×A2×Motor40%+のオッズ分布を分析"""
    print("=" * 70)
    print(" 1. A×A2×Motor40%+ オッズ分布分析")
    print("=" * 70)

    # motor_second_rate >= 40.0 をモーター条件として使用
    query = '''
    WITH race_base AS (
        SELECT
            r.id as race_id,
            rp1.pit_number as p1,
            rp2.pit_number as p2,
            rp3.pit_number as p3
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
        JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        WHERE rp.rank_prediction = 1
        AND rp.confidence = 'A'
        AND e1.racer_rank = 'A2'
        AND e1.motor_second_rate >= 40.0
        AND r.race_date >= '2020-01-01'
        AND r.race_date <= '2025-12-31'
    ),
    race_bets AS (
        SELECT rb.*, printf('%d-%d-%d', rb.p1, rb.p2, rb.p3) as combination FROM race_base rb
    ),
    race_with_odds AS (
        SELECT rb.*, COALESCE(t.odds, 0) as odds
        FROM race_bets rb
        LEFT JOIN trifecta_odds t ON rb.race_id = t.race_id AND t.combination = rb.combination
    )
    SELECT
        CASE
            WHEN odds < 10 THEN '0-10'
            WHEN odds < 20 THEN '10-20'
            WHEN odds < 30 THEN '20-30'
            WHEN odds < 40 THEN '30-40'
            WHEN odds < 50 THEN '40-50'
            WHEN odds < 60 THEN '50-60'
            WHEN odds < 80 THEN '60-80'
            WHEN odds < 100 THEN '80-100'
            ELSE '100+'
        END as odds_range,
        COUNT(*) as count
    FROM race_with_odds
    GROUP BY 1
    ORDER BY MIN(odds)
    '''

    cursor.execute(query)
    results = cursor.fetchall()

    print(f"\n{'オッズ帯':<12} {'件数':>8}")
    print("-" * 25)
    total = 0
    for odds_range, count in results:
        print(f"{odds_range:<12} {count:>8}")
        total += count
    print("-" * 25)
    print(f"{'合計':<12} {total:>8}")


def analyze_by_venue(cursor):
    """A×A2×Motor40%+の会場別ROI分析"""
    print("\n" + "=" * 70)
    print(" 2. A×A2×Motor40%+ 会場別ROI分析")
    print("=" * 70)

    # 会場コード名マッピング
    venue_names = {
        '01': '桐生', '02': '戸田', '03': '江戸川', '04': '平和島', '05': '多摩川',
        '06': '浜名湖', '07': '蒲郡', '08': '常滑', '09': '津', '10': '三国',
        '11': 'びわこ', '12': '住之江', '13': '尼崎', '14': '鳴門', '15': '丸亀',
        '16': '児島', '17': '宮島', '18': '徳山', '19': '下関', '20': '若松',
        '21': '芦屋', '22': '福岡', '23': '唐津', '24': '大村'
    }

    query = '''
    WITH race_base AS (
        SELECT
            r.id as race_id,
            r.venue_code,
            rp1.pit_number as p1,
            rp2.pit_number as p2,
            rp3.pit_number as p3
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
        JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        WHERE rp.rank_prediction = 1
        AND rp.confidence = 'A'
        AND e1.racer_rank = 'A2'
        AND e1.motor_second_rate >= 40.0
        AND r.race_date >= '2020-01-01'
        AND r.race_date <= '2025-12-31'
    ),
    race_bets AS (
        SELECT rb.*, printf('%d-%d-%d', rb.p1, rb.p2, rb.p3) as combination FROM race_base rb
    ),
    race_with_odds AS (
        SELECT rb.*, COALESCE(t.odds, 0) as odds
        FROM race_bets rb
        LEFT JOIN trifecta_odds t ON rb.race_id = t.race_id AND t.combination = rb.combination
    ),
    race_with_payout AS (
        SELECT ro.*, COALESCE(p.amount, 0) as payout
        FROM race_with_odds ro
        LEFT JOIN payouts p ON ro.race_id = p.race_id AND p.bet_type = 'trifecta' AND p.combination = ro.combination
    )
    SELECT
        venue_code,
        COUNT(*) as total,
        SUM(CASE WHEN payout > 0 THEN 1 ELSE 0 END) as hits,
        SUM(payout) as payout,
        AVG(odds) as avg_odds
    FROM race_with_payout
    WHERE odds >= 10 AND odds < 100
    GROUP BY venue_code
    HAVING COUNT(*) >= 5
    ORDER BY (SUM(payout) * 1.0 / (COUNT(*) * 100)) DESC
    '''

    cursor.execute(query)
    results = cursor.fetchall()

    print(f"\n{'会場':<8} {'件数':>6} {'的中':>4} {'平均オッズ':>8} {'ROI':>8} {'収支':>10}")
    print("-" * 55)

    for venue_code, total, hits, payout, avg_odds in results:
        venue_name = venue_names.get(venue_code, venue_code)
        cost = total * 100
        roi = (payout / cost) * 100 if cost > 0 else 0
        profit = payout - cost
        status = "★" if roi >= 150 else ("◎" if roi >= 100 else " ")
        print(f"{venue_name:<8} {total:>6} {hits:>4} {avg_odds:>7.1f}x {roi:>7.1f}% {profit:>+10,.0f} {status}")


def analyze_by_odds_range(cursor):
    """A×A2×Motor40%+ × オッズ帯別ROI分析"""
    print("\n" + "=" * 70)
    print(" 3. A×A2×Motor40%+ オッズ帯別ROI分析")
    print("=" * 70)

    odds_ranges = [
        (10, 20), (20, 30), (30, 40), (40, 50), (50, 60),
        (60, 80), (80, 100), (10, 30), (20, 50), (30, 60)
    ]

    print(f"\n{'オッズ帯':<12} {'件数':>6} {'的中':>4} {'平均オッズ':>8} {'ROI':>8} {'収支':>10}")
    print("-" * 60)

    for odds_min, odds_max in odds_ranges:
        query = f'''
        WITH race_base AS (
            SELECT
                r.id as race_id,
                rp1.pit_number as p1,
                rp2.pit_number as p2,
                rp3.pit_number as p3
            FROM races r
            JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
            JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
            JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
            JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
            JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
            WHERE rp.rank_prediction = 1
            AND rp.confidence = 'A'
            AND e1.racer_rank = 'A2'
            AND e1.motor_second_rate >= 40.0
            AND r.race_date >= '2020-01-01'
            AND r.race_date <= '2025-12-31'
        ),
        race_bets AS (
            SELECT rb.*, printf('%d-%d-%d', rb.p1, rb.p2, rb.p3) as combination FROM race_base rb
        ),
        race_with_odds AS (
            SELECT rb.*, COALESCE(t.odds, 0) as odds
            FROM race_bets rb
            LEFT JOIN trifecta_odds t ON rb.race_id = t.race_id AND t.combination = rb.combination
        ),
        race_with_payout AS (
            SELECT ro.*, COALESCE(p.amount, 0) as payout
            FROM race_with_odds ro
            LEFT JOIN payouts p ON ro.race_id = p.race_id AND p.bet_type = 'trifecta' AND p.combination = ro.combination
        )
        SELECT COUNT(*), SUM(CASE WHEN payout > 0 THEN 1 ELSE 0 END), SUM(payout), AVG(odds)
        FROM race_with_payout
        WHERE odds >= {odds_min} AND odds < {odds_max}
        '''

        cursor.execute(query)
        result = cursor.fetchone()
        total, hits, payout, avg_odds = result if result else (0, 0, 0, 0)
        total = total or 0
        hits = hits or 0
        payout = payout or 0
        avg_odds = avg_odds or 0

        cost = total * 100
        roi = (payout / cost) * 100 if cost > 0 else 0
        profit = payout - cost
        status = "★" if roi >= 150 else ("◎" if roi >= 100 else " ")
        print(f"{odds_min:>3}-{odds_max:<3}倍     {total:>6} {hits:>4} {avg_odds:>7.1f}x {roi:>7.1f}% {profit:>+10,.0f} {status}")


def analyze_without_motor(cursor):
    """モーター条件なしのA×A2の結果（比較用）"""
    print("\n" + "=" * 70)
    print(" 4. A×A2（モーター条件なし）との比較")
    print("=" * 70)

    # モーター条件なし
    query_no_motor = '''
    WITH race_base AS (
        SELECT
            r.id as race_id,
            rp1.pit_number as p1,
            rp2.pit_number as p2,
            rp3.pit_number as p3
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
        JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        WHERE rp.rank_prediction = 1
        AND rp.confidence = 'A'
        AND e1.racer_rank = 'A2'
        AND r.race_date >= '2020-01-01'
        AND r.race_date <= '2025-12-31'
    ),
    race_bets AS (
        SELECT rb.*, printf('%d-%d-%d', rb.p1, rb.p2, rb.p3) as combination FROM race_base rb
    ),
    race_with_odds AS (
        SELECT rb.*, COALESCE(t.odds, 0) as odds
        FROM race_bets rb
        LEFT JOIN trifecta_odds t ON rb.race_id = t.race_id AND t.combination = rb.combination
    ),
    race_with_payout AS (
        SELECT ro.*, COALESCE(p.amount, 0) as payout
        FROM race_with_odds ro
        LEFT JOIN payouts p ON ro.race_id = p.race_id AND p.bet_type = 'trifecta' AND p.combination = ro.combination
    )
    SELECT COUNT(*), SUM(CASE WHEN payout > 0 THEN 1 ELSE 0 END), SUM(payout), AVG(odds)
    FROM race_with_payout
    WHERE odds >= 10 AND odds < 100
    '''

    cursor.execute(query_no_motor)
    result = cursor.fetchone()
    total, hits, payout, avg_odds = result if result else (0, 0, 0, 0)
    total = total or 0
    hits = hits or 0
    payout = payout or 0
    avg_odds = avg_odds or 0
    cost = total * 100
    roi_no_motor = (payout / cost) * 100 if cost > 0 else 0
    profit_no_motor = payout - cost

    print(f"\n{'条件':<25} {'件数':>6} {'的中':>4} {'平均オッズ':>8} {'ROI':>8} {'収支':>10}")
    print("-" * 70)
    print(f"{'A×A2（モーター条件なし）':<25} {total:>6} {hits:>4} {avg_odds:>7.1f}x {roi_no_motor:>7.1f}% {profit_no_motor:>+10,.0f}")

    # モーター条件あり
    query_with_motor = '''
    WITH race_base AS (
        SELECT
            r.id as race_id,
            rp1.pit_number as p1,
            rp2.pit_number as p2,
            rp3.pit_number as p3
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
        JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        WHERE rp.rank_prediction = 1
        AND rp.confidence = 'A'
        AND e1.racer_rank = 'A2'
        AND e1.motor_second_rate >= 40.0
        AND r.race_date >= '2020-01-01'
        AND r.race_date <= '2025-12-31'
    ),
    race_bets AS (
        SELECT rb.*, printf('%d-%d-%d', rb.p1, rb.p2, rb.p3) as combination FROM race_base rb
    ),
    race_with_odds AS (
        SELECT rb.*, COALESCE(t.odds, 0) as odds
        FROM race_bets rb
        LEFT JOIN trifecta_odds t ON rb.race_id = t.race_id AND t.combination = rb.combination
    ),
    race_with_payout AS (
        SELECT ro.*, COALESCE(p.amount, 0) as payout
        FROM race_with_odds ro
        LEFT JOIN payouts p ON ro.race_id = p.race_id AND p.bet_type = 'trifecta' AND p.combination = ro.combination
    )
    SELECT COUNT(*), SUM(CASE WHEN payout > 0 THEN 1 ELSE 0 END), SUM(payout), AVG(odds)
    FROM race_with_payout
    WHERE odds >= 10 AND odds < 100
    '''

    cursor.execute(query_with_motor)
    result = cursor.fetchone()
    total, hits, payout, avg_odds = result if result else (0, 0, 0, 0)
    total = total or 0
    hits = hits or 0
    payout = payout or 0
    avg_odds = avg_odds or 0
    cost = total * 100
    roi_with_motor = (payout / cost) * 100 if cost > 0 else 0
    profit_with_motor = payout - cost

    print(f"{'A×A2×Motor40%+':<25} {total:>6} {hits:>4} {avg_odds:>7.1f}x {roi_with_motor:>7.1f}% {profit_with_motor:>+10,.0f}")

    print()
    print(f"モーター条件追加による変化: ROI {roi_with_motor - roi_no_motor:+.1f}pt, 収支 {profit_with_motor - profit_no_motor:+,.0f}円")


def analyze_yearly_trend(cursor):
    """A×A2×Motor40%+の年度別推移"""
    print("\n" + "=" * 70)
    print(" 5. A×A2×Motor40%+ 年度別推移")
    print("=" * 70)

    print(f"\n{'年度':>6} {'件数':>6} {'的中':>4} {'ROI':>8} {'収支':>10} {'判定':<6}")
    print("-" * 50)

    for year in [2020, 2021, 2022, 2023, 2024, 2025]:
        query = f'''
        WITH race_base AS (
            SELECT
                r.id as race_id,
                rp1.pit_number as p1,
                rp2.pit_number as p2,
                rp3.pit_number as p3
            FROM races r
            JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
            JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
            JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
            JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
            JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
            WHERE rp.rank_prediction = 1
            AND rp.confidence = 'A'
            AND e1.racer_rank = 'A2'
            AND e1.motor_second_rate >= 40.0
            AND r.race_date >= '{year}-01-01'
            AND r.race_date <= '{year}-12-31'
        ),
        race_bets AS (
            SELECT rb.*, printf('%d-%d-%d', rb.p1, rb.p2, rb.p3) as combination FROM race_base rb
        ),
        race_with_odds AS (
            SELECT rb.*, COALESCE(t.odds, 0) as odds
            FROM race_bets rb
            LEFT JOIN trifecta_odds t ON rb.race_id = t.race_id AND t.combination = rb.combination
        ),
        race_with_payout AS (
            SELECT ro.*, COALESCE(p.amount, 0) as payout
            FROM race_with_odds ro
            LEFT JOIN payouts p ON ro.race_id = p.race_id AND p.bet_type = 'trifecta' AND p.combination = ro.combination
        )
        SELECT COUNT(*), SUM(CASE WHEN payout > 0 THEN 1 ELSE 0 END), SUM(payout)
        FROM race_with_payout
        WHERE odds >= 10 AND odds < 100
        '''

        cursor.execute(query)
        result = cursor.fetchone()
        total, hits, payout = result if result else (0, 0, 0)
        total = total or 0
        hits = hits or 0
        payout = payout or 0

        cost = total * 100
        roi = (payout / cost) * 100 if cost > 0 else 0
        profit = payout - cost
        status = "✅黒字" if roi >= 100 else "❌赤字"
        print(f"{year:>6} {total:>6} {hits:>4} {roi:>7.1f}% {profit:>+10,.0f} {status}")


def main():
    print("=" * 70)
    print(" A-1: A×A2失敗原因の深掘り調査")
    print("=" * 70)
    print()
    print("仮説:")
    print("  1. A2級選手はモーター依存度が高く、Motor40%+でオッズが下がる")
    print("  2. 会場フィルターとの相性が悪い")
    print("  3. オッズ帯（10-100）が広すぎる")
    print()

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 各分析を実行
    analyze_odds_distribution(cursor)
    analyze_by_venue(cursor)
    analyze_by_odds_range(cursor)
    analyze_without_motor(cursor)
    analyze_yearly_trend(cursor)

    # 結論
    print("\n" + "=" * 70)
    print(" 調査結論")
    print("=" * 70)
    print()
    print("上記データを確認して、A×A2条件の問題点と改善策を検討してください。")

    conn.close()


if __name__ == "__main__":
    main()
