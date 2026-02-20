# -*- coding: utf-8 -*-
"""
B×50-100条件の追加分析

- 年度別安定性
- 赤字会場除外後のROI
- 高1着的中率会場に限定した場合のROI
- 最終的な改善提案
"""

import sqlite3
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from config.settings import DATABASE_PATH


def get_db_connection():
    """データベース接続を取得"""
    return sqlite3.connect(DATABASE_PATH)


def analyze_yearly_stability():
    """年度別の安定性を分析"""
    print("=" * 80)
    print("【追加分析1】年度別ROI安定性（B×50-100）")
    print("=" * 80)

    conn = get_db_connection()
    cursor = conn.cursor()

    years = ['2020', '2021', '2022', '2023', '2024', '2025']

    print(f"\n■ 年度別ROI（B×50-100、パターンH）")
    print("-" * 70)
    print(f"  {'年度':6s} {'件数':>6s} {'的中':>4s} {'投資額':>10s} {'回収額':>12s} {'ROI':>8s} {'収支':>12s}")
    print("-" * 70)

    total_races = 0
    total_hits = 0
    total_investment = 0
    total_return = 0

    for year in years:
        query = f"""
        SELECT
            COUNT(*) as total_races,
            SUM(CASE WHEN r1.pit_number = p1.pit_number
                      AND r2.pit_number = p2.pit_number
                      AND r3.pit_number = p3.pit_number THEN 1 ELSE 0 END) as trifecta_hit,
            SUM(CASE WHEN r1.pit_number = p1.pit_number
                      AND r2.pit_number = p2.pit_number
                      AND r3.pit_number = p3.pit_number THEN t.odds * 200 ELSE 0 END) +
            SUM(CASE WHEN r1.pit_number = p1.pit_number
                      AND r2.pit_number = p3.pit_number
                      AND r3.pit_number = p2.pit_number THEN COALESCE(t2.odds, 0) * 100 ELSE 0 END) +
            SUM(CASE WHEN r1.pit_number = p2.pit_number
                      AND r2.pit_number = p1.pit_number
                      AND r3.pit_number = p3.pit_number THEN COALESCE(t3.odds, 0) * 100 ELSE 0 END) as total_return
        FROM races ra
        JOIN race_predictions p1 ON ra.id = p1.race_id
            AND p1.prediction_type = 'before'
            AND p1.rank_prediction = 1
            AND p1.confidence = 'B'
        JOIN race_predictions p2 ON ra.id = p2.race_id
            AND p2.prediction_type = 'before'
            AND p2.rank_prediction = 2
        JOIN race_predictions p3 ON ra.id = p3.race_id
            AND p3.prediction_type = 'before'
            AND p3.rank_prediction = 3
        JOIN results r1 ON ra.id = r1.race_id AND r1.rank = '1'
        JOIN results r2 ON ra.id = r2.race_id AND r2.rank = '2'
        JOIN results r3 ON ra.id = r3.race_id AND r3.rank = '3'
        JOIN trifecta_odds t ON ra.id = t.race_id
            AND t.combination = printf('%d-%d-%d', p1.pit_number, p2.pit_number, p3.pit_number)
        LEFT JOIN trifecta_odds t2 ON ra.id = t2.race_id
            AND t2.combination = printf('%d-%d-%d', p1.pit_number, p3.pit_number, p2.pit_number)
        LEFT JOIN trifecta_odds t3 ON ra.id = t3.race_id
            AND t3.combination = printf('%d-%d-%d', p2.pit_number, p1.pit_number, p3.pit_number)
        WHERE ra.race_date LIKE '{year}%'
            AND t.odds >= 50 AND t.odds < 100
        """
        cursor.execute(query)
        result = cursor.fetchone()

        races = result[0]
        hits = result[1] or 0
        ret = result[2] or 0
        inv = races * 400
        roi = 100.0 * ret / inv if inv > 0 else 0
        profit = ret - inv

        if races > 0:
            print(f"  {year:6s} {races:5,}件 {hits:4,}件 {inv:9,}円 {ret:11,.0f}円 {roi:7.1f}% {profit:+11,.0f}円")

            total_races += races
            total_hits += hits
            total_investment += inv
            total_return += ret

    print("-" * 70)
    total_roi = 100.0 * total_return / total_investment if total_investment > 0 else 0
    total_profit = total_return - total_investment
    print(f"  {'合計':6s} {total_races:5,}件 {total_hits:4,}件 {total_investment:9,}円 {total_return:11,.0f}円 {total_roi:7.1f}% {total_profit:+11,.0f}円")

    conn.close()


def analyze_excluding_bad_venues():
    """赤字会場を除外した場合のROI"""
    print("\n" + "=" * 80)
    print("【追加分析2】赤字会場除外後のROI")
    print("=" * 80)

    conn = get_db_connection()
    cursor = conn.cursor()

    # 赤字会場: 芦屋, 三国, 鳴門, 徳山, 若松
    bad_venues = ['21', '10', '14', '18', '20']  # venue_code

    # 赤字会場除外後のROI
    print(f"\n■ 赤字会場（芦屋, 三国, 鳴門, 徳山, 若松）除外後")
    print("-" * 70)

    query = f"""
    SELECT
        COUNT(*) as total_races,
        SUM(CASE WHEN r1.pit_number = p1.pit_number
                  AND r2.pit_number = p2.pit_number
                  AND r3.pit_number = p3.pit_number THEN 1 ELSE 0 END) as trifecta_hit,
        SUM(CASE WHEN r1.pit_number = p1.pit_number
                  AND r2.pit_number = p2.pit_number
                  AND r3.pit_number = p3.pit_number THEN t.odds * 200 ELSE 0 END) +
        SUM(CASE WHEN r1.pit_number = p1.pit_number
                  AND r2.pit_number = p3.pit_number
                  AND r3.pit_number = p2.pit_number THEN COALESCE(t2.odds, 0) * 100 ELSE 0 END) +
        SUM(CASE WHEN r1.pit_number = p2.pit_number
                  AND r2.pit_number = p1.pit_number
                  AND r3.pit_number = p3.pit_number THEN COALESCE(t3.odds, 0) * 100 ELSE 0 END) as total_return
    FROM races ra
    JOIN race_predictions p1 ON ra.id = p1.race_id
        AND p1.prediction_type = 'before'
        AND p1.rank_prediction = 1
        AND p1.confidence = 'B'
    JOIN race_predictions p2 ON ra.id = p2.race_id
        AND p2.prediction_type = 'before'
        AND p2.rank_prediction = 2
    JOIN race_predictions p3 ON ra.id = p3.race_id
        AND p3.prediction_type = 'before'
        AND p3.rank_prediction = 3
    JOIN results r1 ON ra.id = r1.race_id AND r1.rank = '1'
    JOIN results r2 ON ra.id = r2.race_id AND r2.rank = '2'
    JOIN results r3 ON ra.id = r3.race_id AND r3.rank = '3'
    JOIN trifecta_odds t ON ra.id = t.race_id
        AND t.combination = printf('%d-%d-%d', p1.pit_number, p2.pit_number, p3.pit_number)
    LEFT JOIN trifecta_odds t2 ON ra.id = t2.race_id
        AND t2.combination = printf('%d-%d-%d', p1.pit_number, p3.pit_number, p2.pit_number)
    LEFT JOIN trifecta_odds t3 ON ra.id = t3.race_id
        AND t3.combination = printf('%d-%d-%d', p2.pit_number, p1.pit_number, p3.pit_number)
    WHERE ra.race_date BETWEEN '2020-01-01' AND '2025-12-31'
        AND t.odds >= 50 AND t.odds < 100
        AND ra.venue_code NOT IN ('21', '10', '14', '18', '20')
    """
    cursor.execute(query)
    result = cursor.fetchone()

    races = result[0]
    hits = result[1] or 0
    ret = result[2] or 0
    inv = races * 400
    roi = 100.0 * ret / inv if inv > 0 else 0
    profit = ret - inv

    print(f"  除外後: {races:,}件, 的中 {hits}件, ROI {roi:.1f}%, 収支 {profit:+,.0f}円")

    # 全体（参考）
    query = """
    SELECT
        COUNT(*) as total_races,
        SUM(CASE WHEN r1.pit_number = p1.pit_number
                  AND r2.pit_number = p2.pit_number
                  AND r3.pit_number = p3.pit_number THEN 1 ELSE 0 END) as trifecta_hit,
        SUM(CASE WHEN r1.pit_number = p1.pit_number
                  AND r2.pit_number = p2.pit_number
                  AND r3.pit_number = p3.pit_number THEN t.odds * 200 ELSE 0 END) +
        SUM(CASE WHEN r1.pit_number = p1.pit_number
                  AND r2.pit_number = p3.pit_number
                  AND r3.pit_number = p2.pit_number THEN COALESCE(t2.odds, 0) * 100 ELSE 0 END) +
        SUM(CASE WHEN r1.pit_number = p2.pit_number
                  AND r2.pit_number = p1.pit_number
                  AND r3.pit_number = p3.pit_number THEN COALESCE(t3.odds, 0) * 100 ELSE 0 END) as total_return
    FROM races ra
    JOIN race_predictions p1 ON ra.id = p1.race_id
        AND p1.prediction_type = 'before'
        AND p1.rank_prediction = 1
        AND p1.confidence = 'B'
    JOIN race_predictions p2 ON ra.id = p2.race_id
        AND p2.prediction_type = 'before'
        AND p2.rank_prediction = 2
    JOIN race_predictions p3 ON ra.id = p3.race_id
        AND p3.prediction_type = 'before'
        AND p3.rank_prediction = 3
    JOIN results r1 ON ra.id = r1.race_id AND r1.rank = '1'
    JOIN results r2 ON ra.id = r2.race_id AND r2.rank = '2'
    JOIN results r3 ON ra.id = r3.race_id AND r3.rank = '3'
    JOIN trifecta_odds t ON ra.id = t.race_id
        AND t.combination = printf('%d-%d-%d', p1.pit_number, p2.pit_number, p3.pit_number)
    LEFT JOIN trifecta_odds t2 ON ra.id = t2.race_id
        AND t2.combination = printf('%d-%d-%d', p1.pit_number, p3.pit_number, p2.pit_number)
    LEFT JOIN trifecta_odds t3 ON ra.id = t3.race_id
        AND t3.combination = printf('%d-%d-%d', p2.pit_number, p1.pit_number, p3.pit_number)
    WHERE ra.race_date BETWEEN '2020-01-01' AND '2025-12-31'
        AND t.odds >= 50 AND t.odds < 100
    """
    cursor.execute(query)
    result = cursor.fetchone()

    races_all = result[0]
    hits_all = result[1] or 0
    ret_all = result[2] or 0
    inv_all = races_all * 400
    roi_all = 100.0 * ret_all / inv_all if inv_all > 0 else 0

    print(f"  全体（参考）: {races_all:,}件, 的中 {hits_all}件, ROI {roi_all:.1f}%")

    # 年度別の安定性（赤字会場除外後）
    print(f"\n■ 年度別ROI（赤字会場除外後）")
    print("-" * 70)

    years = ['2020', '2021', '2022', '2023', '2024', '2025']
    black_count = 0

    for year in years:
        query = f"""
        SELECT
            COUNT(*) as total_races,
            SUM(CASE WHEN r1.pit_number = p1.pit_number
                      AND r2.pit_number = p2.pit_number
                      AND r3.pit_number = p3.pit_number THEN t.odds * 200 ELSE 0 END) +
            SUM(CASE WHEN r1.pit_number = p1.pit_number
                      AND r2.pit_number = p3.pit_number
                      AND r3.pit_number = p2.pit_number THEN COALESCE(t2.odds, 0) * 100 ELSE 0 END) +
            SUM(CASE WHEN r1.pit_number = p2.pit_number
                      AND r2.pit_number = p1.pit_number
                      AND r3.pit_number = p3.pit_number THEN COALESCE(t3.odds, 0) * 100 ELSE 0 END) as total_return
        FROM races ra
        JOIN race_predictions p1 ON ra.id = p1.race_id
            AND p1.prediction_type = 'before'
            AND p1.rank_prediction = 1
            AND p1.confidence = 'B'
        JOIN race_predictions p2 ON ra.id = p2.race_id
            AND p2.prediction_type = 'before'
            AND p2.rank_prediction = 2
        JOIN race_predictions p3 ON ra.id = p3.race_id
            AND p3.prediction_type = 'before'
            AND p3.rank_prediction = 3
        JOIN results r1 ON ra.id = r1.race_id AND r1.rank = '1'
        JOIN results r2 ON ra.id = r2.race_id AND r2.rank = '2'
        JOIN results r3 ON ra.id = r3.race_id AND r3.rank = '3'
        JOIN trifecta_odds t ON ra.id = t.race_id
            AND t.combination = printf('%d-%d-%d', p1.pit_number, p2.pit_number, p3.pit_number)
        LEFT JOIN trifecta_odds t2 ON ra.id = t2.race_id
            AND t2.combination = printf('%d-%d-%d', p1.pit_number, p3.pit_number, p2.pit_number)
        LEFT JOIN trifecta_odds t3 ON ra.id = t3.race_id
            AND t3.combination = printf('%d-%d-%d', p2.pit_number, p1.pit_number, p3.pit_number)
        WHERE ra.race_date LIKE '{year}%'
            AND t.odds >= 50 AND t.odds < 100
            AND ra.venue_code NOT IN ('21', '10', '14', '18', '20')
        """
        cursor.execute(query)
        result = cursor.fetchone()

        races = result[0]
        ret = result[1] or 0
        inv = races * 400
        roi = 100.0 * ret / inv if inv > 0 else 0
        profit = ret - inv
        status = "○黒字" if roi >= 100 else "×赤字"
        if roi >= 100:
            black_count += 1

        if races > 0:
            print(f"  {year}: {races:3,}件, ROI {roi:6.1f}%, 収支 {profit:+9,.0f}円 {status}")

    print(f"\n  黒字年数: {black_count}/6年")

    conn.close()


def analyze_high_hit_rate_venues():
    """1着的中率が高い会場に限定した場合のROI"""
    print("\n" + "=" * 80)
    print("【追加分析3】高1着的中率会場に限定した場合のROI")
    print("=" * 80)

    conn = get_db_connection()
    cursor = conn.cursor()

    # 1着的中率50%以上の会場: 尼崎, 下関, 大村, 宮島, 常滑, 芦屋, 丸亀
    # venue_code: 13, 19, 24, 17, 08, 21, 15
    # ただし芦屋はROIが低いので除外
    good_venues = ['13', '19', '24', '17', '08', '15']

    print(f"\n■ 1着的中率50%以上の会場（尼崎, 下関, 大村, 宮島, 常滑, 丸亀）に限定")
    print("-" * 70)

    query = f"""
    SELECT
        COUNT(*) as total_races,
        SUM(CASE WHEN r1.pit_number = p1.pit_number THEN 1 ELSE 0 END) as first_hit,
        SUM(CASE WHEN r1.pit_number = p1.pit_number
                  AND r2.pit_number = p2.pit_number
                  AND r3.pit_number = p3.pit_number THEN 1 ELSE 0 END) as trifecta_hit,
        SUM(CASE WHEN r1.pit_number = p1.pit_number
                  AND r2.pit_number = p2.pit_number
                  AND r3.pit_number = p3.pit_number THEN t.odds * 200 ELSE 0 END) +
        SUM(CASE WHEN r1.pit_number = p1.pit_number
                  AND r2.pit_number = p3.pit_number
                  AND r3.pit_number = p2.pit_number THEN COALESCE(t2.odds, 0) * 100 ELSE 0 END) +
        SUM(CASE WHEN r1.pit_number = p2.pit_number
                  AND r2.pit_number = p1.pit_number
                  AND r3.pit_number = p3.pit_number THEN COALESCE(t3.odds, 0) * 100 ELSE 0 END) as total_return
    FROM races ra
    JOIN race_predictions p1 ON ra.id = p1.race_id
        AND p1.prediction_type = 'before'
        AND p1.rank_prediction = 1
        AND p1.confidence = 'B'
    JOIN race_predictions p2 ON ra.id = p2.race_id
        AND p2.prediction_type = 'before'
        AND p2.rank_prediction = 2
    JOIN race_predictions p3 ON ra.id = p3.race_id
        AND p3.prediction_type = 'before'
        AND p3.rank_prediction = 3
    JOIN results r1 ON ra.id = r1.race_id AND r1.rank = '1'
    JOIN results r2 ON ra.id = r2.race_id AND r2.rank = '2'
    JOIN results r3 ON ra.id = r3.race_id AND r3.rank = '3'
    JOIN trifecta_odds t ON ra.id = t.race_id
        AND t.combination = printf('%d-%d-%d', p1.pit_number, p2.pit_number, p3.pit_number)
    LEFT JOIN trifecta_odds t2 ON ra.id = t2.race_id
        AND t2.combination = printf('%d-%d-%d', p1.pit_number, p3.pit_number, p2.pit_number)
    LEFT JOIN trifecta_odds t3 ON ra.id = t3.race_id
        AND t3.combination = printf('%d-%d-%d', p2.pit_number, p1.pit_number, p3.pit_number)
    WHERE ra.race_date BETWEEN '2020-01-01' AND '2025-12-31'
        AND t.odds >= 50 AND t.odds < 100
        AND ra.venue_code IN ('13', '19', '24', '17', '08', '15')
    """
    cursor.execute(query)
    result = cursor.fetchone()

    races = result[0]
    first_hit = result[1] or 0
    trifecta_hit = result[2] or 0
    ret = result[3] or 0
    inv = races * 400
    roi = 100.0 * ret / inv if inv > 0 else 0
    first_rate = 100.0 * first_hit / races if races > 0 else 0
    profit = ret - inv

    print(f"  件数: {races:,}件")
    print(f"  1着的中率: {first_rate:.1f}%")
    print(f"  三連単的中: {trifecta_hit}件")
    print(f"  ROI: {roi:.1f}%")
    print(f"  収支: {profit:+,.0f}円")

    conn.close()


def analyze_odds_distribution():
    """B×50-100でのオッズ分布と1着的中率の関係"""
    print("\n" + "=" * 80)
    print("【追加分析4】オッズ細分化による分析")
    print("=" * 80)

    conn = get_db_connection()
    cursor = conn.cursor()

    print(f"\n■ オッズ細分化（B×50-100内）")
    print("-" * 70)

    odds_ranges = [
        (50, 60, "50-60倍"),
        (60, 70, "60-70倍"),
        (70, 80, "70-80倍"),
        (80, 90, "80-90倍"),
        (90, 100, "90-100倍")
    ]

    for min_odds, max_odds, label in odds_ranges:
        query = f"""
        SELECT
            COUNT(*) as total_races,
            SUM(CASE WHEN r1.pit_number = p1.pit_number THEN 1 ELSE 0 END) as first_hit,
            SUM(CASE WHEN r1.pit_number = p1.pit_number
                      AND r2.pit_number = p2.pit_number
                      AND r3.pit_number = p3.pit_number THEN t.odds * 200 ELSE 0 END) +
            SUM(CASE WHEN r1.pit_number = p1.pit_number
                      AND r2.pit_number = p3.pit_number
                      AND r3.pit_number = p2.pit_number THEN COALESCE(t2.odds, 0) * 100 ELSE 0 END) +
            SUM(CASE WHEN r1.pit_number = p2.pit_number
                      AND r2.pit_number = p1.pit_number
                      AND r3.pit_number = p3.pit_number THEN COALESCE(t3.odds, 0) * 100 ELSE 0 END) as total_return
        FROM races ra
        JOIN race_predictions p1 ON ra.id = p1.race_id
            AND p1.prediction_type = 'before'
            AND p1.rank_prediction = 1
            AND p1.confidence = 'B'
        JOIN race_predictions p2 ON ra.id = p2.race_id
            AND p2.prediction_type = 'before'
            AND p2.rank_prediction = 2
        JOIN race_predictions p3 ON ra.id = p3.race_id
            AND p3.prediction_type = 'before'
            AND p3.rank_prediction = 3
        JOIN results r1 ON ra.id = r1.race_id AND r1.rank = '1'
        JOIN results r2 ON ra.id = r2.race_id AND r2.rank = '2'
        JOIN results r3 ON ra.id = r3.race_id AND r3.rank = '3'
        JOIN trifecta_odds t ON ra.id = t.race_id
            AND t.combination = printf('%d-%d-%d', p1.pit_number, p2.pit_number, p3.pit_number)
        LEFT JOIN trifecta_odds t2 ON ra.id = t2.race_id
            AND t2.combination = printf('%d-%d-%d', p1.pit_number, p3.pit_number, p2.pit_number)
        LEFT JOIN trifecta_odds t3 ON ra.id = t3.race_id
            AND t3.combination = printf('%d-%d-%d', p2.pit_number, p1.pit_number, p3.pit_number)
        WHERE ra.race_date BETWEEN '2020-01-01' AND '2025-12-31'
            AND t.odds >= {min_odds} AND t.odds < {max_odds}
        """
        cursor.execute(query)
        result = cursor.fetchone()

        races = result[0]
        first_hit = result[1] or 0
        ret = result[2] or 0
        inv = races * 400
        roi = 100.0 * ret / inv if inv > 0 else 0
        first_rate = 100.0 * first_hit / races if races > 0 else 0
        profit = ret - inv

        if races > 0:
            print(f"  {label:10s}: {races:4,}件, 1着的中 {first_rate:5.1f}%, ROI {roi:6.1f}%, 収支 {profit:+9,.0f}円")

    conn.close()


def generate_final_recommendations():
    """最終的な改善提案"""
    print("\n" + "=" * 80)
    print("【最終改善提案】")
    print("=" * 80)

    print("""
■ 分析結果サマリー

1. B予想全体の1着的中率: 59.1%
   B×50-100の1着的中率: 41.8%
   → 高オッズ帯では1着的中率が約17pt低下

2. オッズ帯と1着的中率の関係:
   - 1-10倍: 70.4%
   - 10-20倍: 60.3%
   - 20-30倍: 54.4%
   - 30-50倍: 48.7%
   - 50-100倍: 41.8%
   → オッズが高いほど1着的中率は下がる（当然の傾向）

3. 予測1着コース別の1着的中率（B×50-100）:
   - 1コース予測: 50.1%
   - 2コース予測: 26.0%
   - 3コース予測: 22.6%
   - 4コース予測: 17.6%
   - 5コース予測: 30.8%
   - 6コース予測: 12.5%
   → 1コース予測以外は1着的中率が著しく低い

4. 1着的中率とROIは必ずしも連動しない:
   - 平和島: 1着的中率22.2%でも ROI 147.7%（黒字）
   - 芦屋: 1着的中率51.9%でも ROI 15.0%（赤字）
   → 高オッズ帯では「1着的中率」より「ROI」で判断すべき

■ 改善提案

【提案1】会場フィルター追加（推奨）
  除外会場: 芦屋(21), 三国(10), 鳴門(14), 徳山(18), 若松(20)
  理由: 6年間ROIが100%未満

【提案2】現状維持（非推奨）
  理由: 1着的中率が低くてもROIは123%と黒字のため、
        大幅な改善は不要という判断もあり得る

【提案3】オッズ帯を60-100倍に変更（検討中）
  50-60倍帯のROIを確認し、切り捨てた方が良いか検討

■ 重要な発見
  - B×50-100の1着的中率が低いのは「高オッズ帯の特性」
  - 高オッズ帯は「1着予測が外れやすい」が「当たると大きい」
  - ROI 123%は十分な黒字であり、1着的中率の低さは問題ではない
  - 改善するなら「赤字会場の除外」が効果的
""")


def main():
    """メイン関数"""
    print("=" * 80)
    print("B×50-100条件の追加分析")
    print("=" * 80)

    # 年度別安定性
    analyze_yearly_stability()

    # 赤字会場除外後のROI
    analyze_excluding_bad_venues()

    # 高1着的中率会場に限定
    analyze_high_hit_rate_venues()

    # オッズ細分化
    analyze_odds_distribution()

    # 最終改善提案
    generate_final_recommendations()


if __name__ == "__main__":
    main()
