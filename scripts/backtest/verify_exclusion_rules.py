#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
除外ルールの6年間検証

2025年で発見した除外ルールが過去年でも有効かを検証
オーバーフィッティングを避けるため、6年間で安定して効果があるルールのみ採用
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
conn = sqlite3.connect(DATABASE_PATH)
cursor = conn.cursor()

VENUE_NAMES = {
    1: '桐生', 2: '戸田', 3: '江戸川', 4: '平和島', 5: '多摩川', 6: '浜名湖',
    7: '蒲郡', 8: '常滑', 9: '津', 10: '三国', 11: '琵琶湖', 12: '住之江',
    13: '尼崎', 14: '鳴門', 15: '丸亀', 16: '児島', 17: '宮島', 18: '徳山',
    19: '下関', 20: '若松', 21: '芦屋', 22: '福岡', 23: '唐津', 24: '大村'
}

# 2025年分析で発見した主要な除外ルール候補
EXCLUSION_CANDIDATES = [
    # D×30-60 の除外ルール（大きな改善効果）
    {'condition': 'D×30-60', 'type': 'venue', 'value': 5, 'name': '多摩川'},  # +7,600円
    {'condition': 'D×30-60', 'type': 'odds', 'min': 30, 'max': 35, 'name': '30-35倍'},  # +7,380円
    {'condition': 'D×30-60', 'type': 'race', 'value': 9, 'name': '9R'},  # +4,500円
    {'condition': 'D×30-60', 'type': 'venue', 'value': 3, 'name': '江戸川'},  # +3,400円
    {'condition': 'D×30-60', 'type': 'venue', 'value': 10, 'name': '三国'},  # +2,600円

    # A×A1×10-12 の除外ルール
    {'condition': 'A×A1×10-12', 'type': 'race', 'value': 10, 'name': '10R'},  # +2,300円
    {'condition': 'A×A1×10-12', 'type': 'venue', 'value': 12, 'name': '住之江'},  # +1,700円

    # C×20-30×B1+会場 の除外ルール
    {'condition': 'C×20-30×B1+会場', 'type': 'venue', 'value': 18, 'name': '徳山'},  # +1,700円

    # B×50-100 の除外ルール
    {'condition': 'B×50-100', 'type': 'rank', 'value': 'A2', 'name': 'A2級'},  # +1,200円
]


def get_condition_config(cond_name):
    """条件設定を取得"""
    conditions = {
        'D×30-60': {'confidence': 'D', 'c1_rank': ['A1', 'A2', 'B1'], 'odds_min': 30, 'odds_max': 60, 'venue_filter': None, 'motor_min': None},
        'A×A1×10-12': {'confidence': 'A', 'c1_rank': ['A1'], 'odds_min': 10, 'odds_max': 12, 'venue_filter': None, 'motor_min': None},
        'C×20-30×B1+会場': {'confidence': 'C', 'c1_rank': ['B1'], 'odds_min': 20, 'odds_max': 30, 'venue_filter': [23, 18, 5, 4, 9, 15, 8, 24, 20, 17], 'motor_min': None},
        'B×50-100': {'confidence': 'B', 'c1_rank': ['A1', 'A2', 'B1'], 'odds_min': 50, 'odds_max': 100, 'venue_filter': None, 'motor_min': None},
    }
    return conditions.get(cond_name)


def analyze_exclusion_rule(rule, years=[2020, 2021, 2022, 2023, 2024, 2025]):
    """除外ルールの年別効果を分析"""
    cond = get_condition_config(rule['condition'])
    if not cond:
        return None

    results = []
    for year in years:
        c1_rank_str = "','".join(cond['c1_rank'])
        venue_clause = ""
        if cond.get('venue_filter'):
            venue_clause = f"AND r.venue_code IN ({','.join(map(str, cond['venue_filter']))})"
        motor_clause = ""
        if cond.get('motor_min'):
            motor_clause = f"AND e1.motor_second_rate >= {cond['motor_min']}"

        # 除外条件
        exclusion_clause = ""
        if rule['type'] == 'venue':
            exclusion_clause = f"AND r.venue_code = {rule['value']}"
        elif rule['type'] == 'race':
            exclusion_clause = f"AND r.race_number = {rule['value']}"
        elif rule['type'] == 'rank':
            exclusion_clause = f"AND e1.racer_rank = '{rule['value']}'"

        # ベース（除外なし）
        query_base = f'''
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
            AND rp.confidence = '{cond["confidence"]}'
            AND e1.racer_rank IN ('{c1_rank_str}')
            AND r.race_date >= '{year}-01-01'
            AND r.race_date < '{year}-12-01'
            {venue_clause}
            {motor_clause}
        ),
        race_bets AS (
            SELECT
                rb.*,
                COALESCE(
                    (SELECT o.odds FROM trifecta_odds o
                     WHERE o.race_id = rb.race_id
                     AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p3 AS TEXT)
                    ), 0
                ) as pred_odds,
                CASE
                    WHEN (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '1') = rb.p1
                     AND (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '2') = rb.p2
                     AND (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '3') = rb.p3
                    THEN COALESCE(
                        (SELECT o.odds FROM trifecta_odds o
                         WHERE o.race_id = rb.race_id
                         AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p3 AS TEXT)
                        ), 0
                    ) * 100
                    ELSE 0
                END as payout
            FROM race_base rb
        )
        SELECT COUNT(*) as bets, SUM(payout) as payout
        FROM race_bets
        WHERE pred_odds >= {cond['odds_min']} AND pred_odds < {cond['odds_max']}
        '''

        cursor.execute(query_base)
        base = cursor.fetchone()
        base_bets, base_payout = base
        if not base_bets:
            results.append({'year': year, 'improvement': 0, 'removed': 0})
            continue

        # 除外対象のみ
        query_excluded = f'''
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
            AND rp.confidence = '{cond["confidence"]}'
            AND e1.racer_rank IN ('{c1_rank_str}')
            AND r.race_date >= '{year}-01-01'
            AND r.race_date < '{year}-12-01'
            {venue_clause}
            {motor_clause}
            {exclusion_clause}
        ),
        race_bets AS (
            SELECT
                rb.*,
                COALESCE(
                    (SELECT o.odds FROM trifecta_odds o
                     WHERE o.race_id = rb.race_id
                     AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p3 AS TEXT)
                    ), 0
                ) as pred_odds,
                CASE
                    WHEN (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '1') = rb.p1
                     AND (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '2') = rb.p2
                     AND (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '3') = rb.p3
                    THEN COALESCE(
                        (SELECT o.odds FROM trifecta_odds o
                         WHERE o.race_id = rb.race_id
                         AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p3 AS TEXT)
                        ), 0
                    ) * 100
                    ELSE 0
                END as payout
            FROM race_base rb
        )
        SELECT COUNT(*) as bets, SUM(payout) as payout
        FROM race_bets
        WHERE pred_odds >= {cond['odds_min']} AND pred_odds < {cond['odds_max']}
        '''

        # オッズ帯の場合は特別処理
        if rule['type'] == 'odds':
            query_excluded = f'''
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
                AND rp.confidence = '{cond["confidence"]}'
                AND e1.racer_rank IN ('{c1_rank_str}')
                AND r.race_date >= '{year}-01-01'
                AND r.race_date < '{year}-12-01'
                {venue_clause}
                {motor_clause}
            ),
            race_bets AS (
                SELECT
                    rb.*,
                    COALESCE(
                        (SELECT o.odds FROM trifecta_odds o
                         WHERE o.race_id = rb.race_id
                         AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p3 AS TEXT)
                        ), 0
                    ) as pred_odds,
                    CASE
                        WHEN (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '1') = rb.p1
                         AND (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '2') = rb.p2
                         AND (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '3') = rb.p3
                        THEN COALESCE(
                            (SELECT o.odds FROM trifecta_odds o
                             WHERE o.race_id = rb.race_id
                             AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p3 AS TEXT)
                            ), 0
                        ) * 100
                        ELSE 0
                    END as payout
                FROM race_base rb
            )
            SELECT COUNT(*) as bets, SUM(payout) as payout
            FROM race_bets
            WHERE pred_odds >= {rule['min']} AND pred_odds < {rule['max']}
            '''

        cursor.execute(query_excluded)
        excluded = cursor.fetchone()
        excluded_bets, excluded_payout = excluded

        if excluded_bets:
            # 除外による改善額 = 除外部分のマイナス収支
            excluded_profit = excluded_payout - (excluded_bets * 100)
            improvement = -excluded_profit  # 赤字なら除外でプラス
            results.append({
                'year': year,
                'improvement': improvement,
                'removed': excluded_bets,
                'base_bets': base_bets,
            })
        else:
            results.append({'year': year, 'improvement': 0, 'removed': 0})

    return results


def main():
    print("=" * 100)
    print("除外ルールの6年間検証")
    print("=" * 100)
    print()

    valid_rules = []

    for rule in EXCLUSION_CANDIDATES:
        results = analyze_exclusion_rule(rule)
        if not results:
            continue

        # 年別結果を集計
        total_improvement = sum(r['improvement'] for r in results)
        positive_years = sum(1 for r in results if r['improvement'] > 0)
        total_removed = sum(r['removed'] for r in results)

        rule_name = f"{rule['condition']} - {rule['name']}除外"
        print(f"\n【{rule_name}】")
        print("-" * 80)

        for r in results:
            status = "+" if r['improvement'] > 0 else "-"
            print(f"  {r['year']}年: {status}{abs(r['improvement']):,.0f}円 ({r['removed']}件除外)")

        print(f"  ─────────────────────────────")
        print(f"  6年合計: {total_improvement:+,.0f}円 | 黒字年: {positive_years}/6年")

        # 採用基準: 6年合計で黒字 AND 4年以上黒字
        if total_improvement > 0 and positive_years >= 4:
            print(f"  → ★ 採用候補（安定性あり）")
            valid_rules.append({
                **rule,
                'total_improvement': total_improvement,
                'positive_years': positive_years,
                'total_removed': total_removed,
            })
        elif total_improvement > 0 and positive_years >= 3:
            print(f"  → △ 要検討（やや不安定）")
        else:
            print(f"  → × 不採用（不安定）")

    # 結果サマリー
    print("\n" + "=" * 100)
    print("【採用候補の除外ルール】")
    print("=" * 100)

    if valid_rules:
        print(f"\n{'条件':<25} {'除外対象':<15} {'6年改善':>12} {'安定性':>10}")
        print("-" * 70)
        for r in sorted(valid_rules, key=lambda x: x['total_improvement'], reverse=True):
            print(f"{r['condition']:<25} {r['name']:<15} {r['total_improvement']:>+12,.0f} {r['positive_years']}/6年")

        total = sum(r['total_improvement'] for r in valid_rules)
        print("-" * 70)
        print(f"{'累積改善額':<40} {total:>+12,.0f}円")
    else:
        print("\n安定性のある除外ルールは見つかりませんでした。")

    conn.close()


if __name__ == '__main__':
    main()
